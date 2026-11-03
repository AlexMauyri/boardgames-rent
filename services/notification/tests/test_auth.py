"""Tests for WebSocket token verification."""

import pytest

from app.auth import AuthError, Principal, authenticate
from tests.conftest import make_token


def test_valid_access_token_gives_the_principal():
    assert authenticate(make_token(7, "COURIER")) == Principal(7, "COURIER")


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(make_token(secret="x" * 40), id="wrong-signature"),
        pytest.param(make_token(expires_in=-10), id="expired"),
        pytest.param(make_token(token_type="refresh"), id="refresh-token"),
    ],
)
def test_untrusted_tokens_are_rejected(token):
    with pytest.raises(AuthError):
        authenticate(token)


def test_non_numeric_subject_is_rejected():
    import jwt
    import time
    from app.config import settings

    token = jwt.encode(
        {"sub": "abc", "role": "CLIENT", "type": "access",
         "exp": int(time.time()) + 60},
        settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthError):
        authenticate(token)
