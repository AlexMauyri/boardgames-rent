"""Tests for app.services.tokens."""

import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.jwt import InvalidTokenError, decode_refresh_token
from app.config import settings
from app.services.tokens import issue_pair, revoke, rotate

_JKT_A = "thumbprint-A"
_JKT_B = "thumbprint-B"


# --- issue_pair -------------------------------------------------------


async def test_issue_pair_stores_jti_with_ttl(redis_client):
    pair = await issue_pair(
        redis_client, user_id=11, role="CLIENT", cnf_jkt=_JKT_A,
    )

    claims = decode_refresh_token(pair.refresh_token)
    key = f"refresh:{claims['jti']}"

    raw = await redis_client.get(key)
    assert raw is not None
    stored = json.loads(raw)
    assert stored == {"user_id": 11, "role": "CLIENT", "jkt": _JKT_A}

    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= settings.refresh_token_ttl


async def test_issue_pair_binds_refresh_but_not_access(redis_client):
    pair = await issue_pair(
        redis_client, user_id=1, role="ADMIN", cnf_jkt=_JKT_A,
    )
    assert pair.token_type == "DPoP"

    refresh_claims = decode_refresh_token(pair.refresh_token)
    assert refresh_claims["cnf"] == {"jkt": _JKT_A}

    # Access token must not carry cnf.jkt: access is Bearer.
    from app.auth.jwt import decode_access_token
    access_claims = decode_access_token(pair.access_token)
    assert "cnf" not in access_claims


# --- rotate -----------------------------------------------------------


async def test_rotate_issues_new_pair_and_removes_old_jti(redis_client):
    pair = await issue_pair(
        redis_client, user_id=5, role="CLIENT", cnf_jkt=_JKT_A,
    )
    old_jti = decode_refresh_token(pair.refresh_token)["jti"]

    new_pair = await rotate(
        redis_client, pair.refresh_token, proof_jkt=_JKT_A,
    )
    new_jti = decode_refresh_token(new_pair.refresh_token)["jti"]

    assert new_jti != old_jti
    assert await redis_client.get(f"refresh:{old_jti}") is None
    assert await redis_client.get(f"refresh:{new_jti}") is not None


async def test_rotate_preserves_subject_and_jkt(redis_client):
    pair = await issue_pair(
        redis_client, user_id=99, role="MANAGER", cnf_jkt=_JKT_A,
    )
    new_pair = await rotate(
        redis_client, pair.refresh_token, proof_jkt=_JKT_A,
    )
    claims = decode_refresh_token(new_pair.refresh_token)
    assert claims["sub"] == "99"
    assert claims["role"] == "MANAGER"
    assert claims["cnf"] == {"jkt": _JKT_A}


async def test_rotate_with_wrong_proof_jkt_rejected(redis_client):
    pair = await issue_pair(
        redis_client, user_id=1, role="CLIENT", cnf_jkt=_JKT_A,
    )
    with pytest.raises(InvalidTokenError) as exc:
        await rotate(redis_client, pair.refresh_token, proof_jkt=_JKT_B)
    assert exc.value.reason == "jkt_mismatch"


async def test_rotate_twice_with_same_token_rejected(redis_client):
    pair = await issue_pair(
        redis_client, user_id=1, role="CLIENT", cnf_jkt=_JKT_A,
    )
    await rotate(redis_client, pair.refresh_token, proof_jkt=_JKT_A)
    with pytest.raises(InvalidTokenError):
        await rotate(redis_client, pair.refresh_token, proof_jkt=_JKT_A)


async def test_rotate_revoked_token_rejected(redis_client):
    pair = await issue_pair(
        redis_client, user_id=1, role="CLIENT", cnf_jkt=_JKT_A,
    )
    await revoke(redis_client, pair.refresh_token, proof_jkt=_JKT_A)
    with pytest.raises(InvalidTokenError):
        await rotate(redis_client, pair.refresh_token, proof_jkt=_JKT_A)


async def test_rotate_expired_token_rejected(redis_client):
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "role": "CLIENT",
        "type": "refresh",
        "jti": "expired-jti",
        "cnf": {"jkt": _JKT_A},
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
    }
    token = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError) as exc:
        await rotate(redis_client, token, proof_jkt=_JKT_A)
    assert "expired" in exc.value.reason


async def test_rotate_garbage_token_rejected(redis_client):
    with pytest.raises(InvalidTokenError):
        await rotate(redis_client, "not-a-jwt", proof_jkt=_JKT_A)


async def test_rotate_token_without_cnf_rejected(redis_client):
    """A token issued before DPoP binding must not rotate."""
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "role": "CLIENT",
        "type": "refresh",
        "jti": "legacy-jti",
        "iat": now,
        "exp": now + timedelta(days=30),
    }
    token = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError) as exc:
        await rotate(redis_client, token, proof_jkt=_JKT_A)
    assert "cnf" in exc.value.reason


# --- revoke -----------------------------------------------------------


async def test_revoke_deletes_key(redis_client):
    pair = await issue_pair(
        redis_client, user_id=1, role="CLIENT", cnf_jkt=_JKT_A,
    )
    jti = decode_refresh_token(pair.refresh_token)["jti"]

    assert await redis_client.get(f"refresh:{jti}") is not None
    await revoke(redis_client, pair.refresh_token, proof_jkt=_JKT_A)
    assert await redis_client.get(f"refresh:{jti}") is None


async def test_revoke_is_idempotent(redis_client):
    pair = await issue_pair(
        redis_client, user_id=1, role="CLIENT", cnf_jkt=_JKT_A,
    )
    await revoke(redis_client, pair.refresh_token, proof_jkt=_JKT_A)
    await revoke(redis_client, pair.refresh_token, proof_jkt=_JKT_A)


async def test_revoke_with_wrong_proof_jkt_rejected(redis_client):
    pair = await issue_pair(
        redis_client, user_id=1, role="CLIENT", cnf_jkt=_JKT_A,
    )
    with pytest.raises(InvalidTokenError):
        await revoke(redis_client, pair.refresh_token, proof_jkt=_JKT_B)


async def test_revoke_garbage_token_rejected(redis_client):
    with pytest.raises(InvalidTokenError):
        await revoke(redis_client, "not-a-jwt", proof_jkt=_JKT_A)