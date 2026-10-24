"""Tests for app.security.jwt."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.auth.jwt import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


def test_access_token_round_trip():
    token = create_access_token(user_id=42, role="CLIENT")
    claims = decode_access_token(token)
    assert claims["sub"] == "42"
    assert claims["role"] == "CLIENT"
    assert claims["type"] == "access"


def test_refresh_token_round_trip_returns_jti():
    token, jti = create_refresh_token(user_id=7, role="ADMIN", cnf_jkt="test-jkt")
    claims = decode_refresh_token(token)
    assert claims["sub"] == "7"
    assert claims["role"] == "ADMIN"
    assert claims["type"] == "refresh"
    assert claims["jti"] == jti
    assert claims["cnf"] == {"jkt": "test-jkt"}


def test_refresh_tokens_are_unique():
    _, jti1 = create_refresh_token(1, "CLIENT", cnf_jkt="a")
    _, jti2 = create_refresh_token(1, "CLIENT", cnf_jkt="a")
    assert jti1 != jti2


def test_expired_access_token():
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "role": "CLIENT",
        "type": "access",
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
    }
    token = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError) as exc:
        decode_access_token(token)
    assert "expired" in exc.value.reason


def test_wrong_signature_rejected():
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "role": "CLIENT",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    wrong_secret = "x" * 64
    foreign = jwt.encode(payload, wrong_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError):
        decode_access_token(foreign)


def test_access_token_passed_as_refresh_rejected():
    access = create_access_token(1, "CLIENT")
    with pytest.raises(InvalidTokenError):
        decode_refresh_token(access)


def test_refresh_token_passed_as_access_rejected():
    refresh, _ = create_refresh_token(1, "CLIENT", cnf_jkt="test-jkt")
    with pytest.raises(InvalidTokenError):
        decode_access_token(refresh)


def test_malformed_token_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt")


def test_missing_jti_on_refresh_rejected():
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "role": "CLIENT",
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError) as exc:
        decode_refresh_token(token)
    assert "jti" in exc.value.reason