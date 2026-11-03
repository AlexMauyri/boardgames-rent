"""Shared fixtures for the notification service tests."""

import os
import time

os.environ.setdefault("JWT_SECRET", "test_secret_test_secret_test_secret_32")

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import create_app  # noqa: E402


def make_token(
    user_id: int = 1,
    role: str = "CLIENT",
    *,
    token_type: str = "access",
    expires_in: int = 300,
    secret: str | None = None,
) -> str:
    """Sign a token the way the API service does."""
    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(user_id),
            "role": role,
            "type": token_type,
            "iat": now,
            "exp": now + expires_in,
        },
        secret or settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def make_event(event_type: str, data: dict, event_id: str = "evt-1") -> dict:
    """Build an event envelope as the API service publishes it."""
    return {
        "id": event_id,
        "type": event_type,
        "occurred_at": "2026-11-03T10:00:00+00:00",
        "data": data,
    }


@pytest.fixture
def client():
    """Test client over an app without the RabbitMQ consumer."""
    with TestClient(create_app(consume=False)) as c:
        yield c
