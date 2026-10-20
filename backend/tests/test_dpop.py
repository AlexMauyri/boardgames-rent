import time
import uuid

import jwt
import json
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.auth.dpop import (
    InvalidJwkError,
    compute_jwk_thumbprint,
    parse_jwk_from_header,
    DpopExpired,
    DpopInvalidProof,
    DpopJktMismatch,
    DpopReplay,
    verify_dpop_proof,
)


# --- fixtures ---------------------------------------------------------


def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _public_jwk(private_key) -> dict:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(numbers.x.to_bytes(32, "big")),
        "y": _b64url(numbers.y.to_bytes(32, "big")),
    }


@pytest.fixture
def keypair():
    """Return (private_key, public_jwk) for ES256 testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, _public_jwk(private_key)


def _sign(
    private_key,
    jwk: dict,
    *,
    htm: str = "POST",
    htu: str = "https://host/api/v1/auth/login/client",
    iat: int | None = None,
    jti: str | None = None,
    typ: str = "dpop+jwt",
    alg: str = "ES256",
    extra_claims: dict | None = None,
) -> str:
    """Build and sign a DPoP proof with the given claims."""
    header = {"typ": typ, "alg": alg, "jwk": jwk}
    payload = {
        "jti": jti if jti is not None else str(uuid.uuid4()),
        "htm": htm,
        "htu": htu,
        "iat": iat if iat is not None else int(time.time()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, private_key, algorithm="ES256", headers=header)


# --- verify_dpop_proof: happy path ------------------------------------


async def test_verify_returns_thumbprint_on_valid_proof(
    redis_client, keypair,
):
    private_key, jwk = keypair
    expected_jkt = compute_jwk_thumbprint(jwk)
    proof = _sign(private_key, jwk)

    result = await verify_dpop_proof(
        proof,
        expected_htm="POST",
        expected_htu="https://host/api/v1/auth/login/client",
        expected_jkt=None,
        redis_client=redis_client,
    )

    assert result == expected_jkt


async def test_verify_with_matching_expected_jkt(
    redis_client, keypair,
):
    private_key, jwk = keypair
    expected_jkt = compute_jwk_thumbprint(jwk)
    proof = _sign(private_key, jwk)

    result = await verify_dpop_proof(
        proof,
        expected_htm="POST",
        expected_htu="https://host/api/v1/auth/login/client",
        expected_jkt=expected_jkt,
        redis_client=redis_client,
    )

    assert result == expected_jkt


# --- header checks ----------------------------------------------------


async def test_wrong_typ_rejected(redis_client, keypair):
    private_key, jwk = keypair
    proof = _sign(private_key, jwk, typ="JWT")
    with pytest.raises(DpopInvalidProof, match="typ"):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )


async def test_wrong_alg_rejected(redis_client, keypair):
    """Server must reject the alg before checking the signature."""
    _, jwk = keypair
    header = {"typ": "dpop+jwt", "alg": "RS256", "jwk": jwk}
    payload = {
        "jti": str(uuid.uuid4()),
        "htm": "POST",
        "htu": "https://host/x",
        "iat": int(time.time()),
    }
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    bogus_sig = _b64url(b"\x00" * 64)
    proof = f"{header_b64}.{payload_b64}.{bogus_sig}"

    with pytest.raises(DpopInvalidProof, match="alg"):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )



async def test_malformed_jwt_rejected(redis_client):
    with pytest.raises(DpopInvalidProof, match="malformed"):
        await verify_dpop_proof(
            "not-a-jwt",
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )


# --- claim checks -----------------------------------------------------


async def test_wrong_htm_rejected(redis_client, keypair):
    private_key, jwk = keypair
    proof = _sign(private_key, jwk, htm="GET")
    with pytest.raises(DpopInvalidProof, match="htm"):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )


async def test_wrong_htu_rejected(redis_client, keypair):
    private_key, jwk = keypair
    proof = _sign(private_key, jwk, htu="https://host/other")
    with pytest.raises(DpopInvalidProof, match="htu"):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )


async def test_expired_iat_rejected(redis_client, keypair):
    private_key, jwk = keypair
    proof = _sign(
        private_key, jwk,
        htu="https://host/x",
        iat=int(time.time()) - 61,
    )
    with pytest.raises(DpopExpired):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )


async def test_future_iat_rejected(redis_client, keypair):
    private_key, jwk = keypair
    proof = _sign(
        private_key, jwk,
        htu="https://host/x",
        iat=int(time.time()) + 61,
    )
    with pytest.raises(DpopExpired):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )


async def test_missing_jti_rejected(redis_client, keypair):
    private_key, jwk = keypair
    header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": jwk}
    payload = {"htm": "POST", "htu": "https://host/x", "iat": int(time.time())}
    proof = jwt.encode(payload, private_key, algorithm="ES256", headers=header)
    with pytest.raises(DpopInvalidProof, match="jti"):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/x",
            expected_jkt=None,
            redis_client=redis_client,
        )


# --- signature and jkt ------------------------------------------------


async def test_broken_signature_rejected(redis_client, keypair):
    """A token whose signature was tampered with must not pass."""
    private_key, jwk = keypair
    proof = _sign(private_key, jwk)
    header_b64, payload_b64, signature_b64 = proof.split(".")
    tampered = f"{header_b64}.{payload_b64}.{signature_b64[:-2]}XX"
    with pytest.raises(DpopInvalidProof, match="signature"):
        await verify_dpop_proof(
            tampered,
            expected_htm="POST",
            expected_htu="https://host/api/v1/auth/login/client",
            expected_jkt=None,
            redis_client=redis_client,
        )


async def test_jkt_mismatch_rejected(redis_client, keypair):
    private_key, jwk = keypair
    proof = _sign(private_key, jwk)
    with pytest.raises(DpopJktMismatch):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/api/v1/auth/login/client",
            expected_jkt="some-other-thumbprint",
            redis_client=redis_client,
        )


# --- replay -----------------------------------------------------------


async def test_replay_rejected(redis_client, keypair):
    private_key, jwk = keypair
    proof = _sign(private_key, jwk)

    await verify_dpop_proof(
        proof,
        expected_htm="POST",
        expected_htu="https://host/api/v1/auth/login/client",
        expected_jkt=None,
        redis_client=redis_client,
    )

    with pytest.raises(DpopReplay):
        await verify_dpop_proof(
            proof,
            expected_htm="POST",
            expected_htu="https://host/api/v1/auth/login/client",
            expected_jkt=None,
            redis_client=redis_client,
        )


async def test_broken_proof_does_not_burn_jti(redis_client, keypair):
    """A forged proof with a valid jti must not prevent the real one."""
    private_key, jwk = keypair
    jti = str(uuid.uuid4())
    real_proof = _sign(private_key, jwk, jti=jti)

    foreign_key = ec.generate_private_key(ec.SECP256R1())
    forged = _sign(foreign_key, jwk, jti=jti)
    with pytest.raises(DpopInvalidProof):
        await verify_dpop_proof(
            forged,
            expected_htm="POST",
            expected_htu="https://host/api/v1/auth/login/client",
            expected_jkt=None,
            redis_client=redis_client,
        )

    await verify_dpop_proof(
        real_proof,
        expected_htm="POST",
        expected_htu="https://host/api/v1/auth/login/client",
        expected_jkt=None,
        redis_client=redis_client,
    )