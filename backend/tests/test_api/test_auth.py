"""Tests for /api/v1/auth/* with DPoP and nonce."""

from app.auth.jwt import decode_access_token, decode_refresh_token
from tests.conftest import do_auth_request

REGISTER = "/api/v1/auth/register/client"
LOGIN_CLIENT = "/api/v1/auth/login/client"
LOGIN_EMPLOYEE = "/api/v1/auth/login/employee"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


def _client_body(email="alice@test.io", password="secret1"):
    return {"email": email, "password": password}


async def _register(http, email="alice@test.io", password="secret1"):
    return await http.post(REGISTER, json={
        "email": email,
        "password": password,
        "full_name": "Alice",
        "phone": "+79990000001",
    })


# --- register ---------------------------------------------------------


async def test_register_client_returns_201(http):
    r = await _register(http)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@test.io"
    assert body["is_active"] is True
    assert "password_hash" not in body


async def test_register_does_not_require_dpop(http):
    """Registration issues nothing secret, so no proof is needed."""
    r = await _register(http)
    assert r.status_code == 201


async def test_register_duplicate_email_conflicts(http):
    await _register(http)
    r = await _register(http)
    assert r.status_code == 409


# --- login: DPoP enforcement -----------------------------------------


async def test_login_without_dpop_returns_401(http):
    await _register(http)
    r = await http.post(LOGIN_CLIENT, json=_client_body())
    assert r.status_code == 401
    assert "DPoP" in (r.headers.get("WWW-Authenticate") or "")


async def test_login_dpop_without_nonce_returns_challenge(http, make_dpop_proof):
    await _register(http)
    r = await do_auth_request(
        http, "POST", LOGIN_CLIENT, make_dpop_proof,
        body=_client_body(), max_attempts=1,
    )
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").startswith("DPoP")
    assert "use_dpop_nonce" in r.headers["WWW-Authenticate"]
    assert r.headers.get("DPoP-Nonce")


async def test_login_with_nonce_returns_pair(http, make_dpop_proof):
    await _register(http)
    r = await do_auth_request(
        http, "POST", LOGIN_CLIENT, make_dpop_proof, body=_client_body(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "DPoP"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_returns_dpop_bound_refresh_but_bearer_access(
    http, make_dpop_proof, dpop_keypair,
):
    _, _, thumbprint = dpop_keypair
    await _register(http)
    r = await do_auth_request(
        http, "POST", LOGIN_CLIENT, make_dpop_proof, body=_client_body(),
    )
    body = r.json()

    refresh_claims = decode_refresh_token(body["refresh_token"])
    assert refresh_claims["cnf"] == {"jkt": thumbprint}

    access_claims = decode_access_token(body["access_token"])
    assert "cnf" not in access_claims


async def test_login_wrong_password_still_401(http, make_dpop_proof):
    await _register(http)
    r = await do_auth_request(
        http, "POST", LOGIN_CLIENT, make_dpop_proof,
        body=_client_body(password="wrong"),
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials"


async def test_login_employee_with_dpop(
    http, make_dpop_proof, session,
):
    from app.schemas import EmployeeCreate
    from app.services import create_employee

    await create_employee(session, EmployeeCreate(
        email="emp@test.io", password="secret1",
        full_name="E", phone="+7", role="ADMIN",
    ))
    r = await do_auth_request(
        http, "POST", LOGIN_EMPLOYEE, make_dpop_proof,
        body=_client_body(email="emp@test.io"),
    )
    assert r.status_code == 200
    assert r.json()["token_type"] == "DPoP"


# --- refresh ----------------------------------------------------------


async def _login(http, make_dpop_proof) -> dict:
    await _register(http)
    r = await do_auth_request(
        http, "POST", LOGIN_CLIENT, make_dpop_proof, body=_client_body(),
    )
    assert r.status_code == 200
    return r.json()


async def test_refresh_rotates_with_dpop(http, make_dpop_proof):
    tokens = await _login(http, make_dpop_proof)

    r = await do_auth_request(
        http, "POST", REFRESH, make_dpop_proof,
        body={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["refresh_token"] != tokens["refresh_token"]


async def test_refresh_with_wrong_key_returns_401(
    http, make_dpop_proof, dpop_keypair,
):
    """A different key cannot exchange the refresh token."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from tests.conftest import _b64url, _public_jwk
    import jwt
    import time
    import uuid

    tokens = await _login(http, make_dpop_proof)

    other_key = ec.generate_private_key(ec.SECP256R1())
    other_jwk = _public_jwk(other_key)

    def other_proof(*, htm, htu, nonce=None):
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": other_jwk}
        payload = {
            "jti": str(uuid.uuid4()),
            "htm": htm,
            "htu": htu,
            "iat": int(time.time()),
        }
        if nonce:
            payload["nonce"] = nonce
        return jwt.encode(payload, other_key, algorithm="ES256", headers=header)

    r = await do_auth_request(
        http, "POST", REFRESH, other_proof,
        body={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 401


async def test_refresh_reuse_rejected(http, make_dpop_proof):
    tokens = await _login(http, make_dpop_proof)
    await do_auth_request(
        http, "POST", REFRESH, make_dpop_proof,
        body={"refresh_token": tokens["refresh_token"]},
    )
    r = await do_auth_request(
        http, "POST", REFRESH, make_dpop_proof,
        body={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 401


# --- logout -----------------------------------------------------------


async def test_logout_with_dpop_returns_204(http, make_dpop_proof):
    tokens = await _login(http, make_dpop_proof)
    r = await do_auth_request(
        http, "POST", LOGOUT, make_dpop_proof,
        body={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 204


async def test_logout_then_refresh_returns_401(http, make_dpop_proof):
    tokens = await _login(http, make_dpop_proof)
    await do_auth_request(
        http, "POST", LOGOUT, make_dpop_proof,
        body={"refresh_token": tokens["refresh_token"]},
    )
    r = await do_auth_request(
        http, "POST", REFRESH, make_dpop_proof,
        body={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 401