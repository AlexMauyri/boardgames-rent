"""Tests for app.cache.client."""

from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import redis.asyncio as redis
from fastapi import FastAPI

from app.cache.client import build_redis, bootstrap_redis, get_redis
from app.config import settings


def test_build_redis_uses_settings_url():
    client = build_redis()
    parsed = urlparse(settings.redis_url)
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["host"] == parsed.hostname
    assert kwargs["port"] == (parsed.port or 6379)
    db = int((parsed.path or "/0").lstrip("/") or "0")
    assert kwargs["db"] == db


async def test_bootstrap_redis_stores_client_on_app():
    app = FastAPI()
    await bootstrap_redis(app)
    client = app.state.redis
    assert isinstance(client, redis.Redis)
    assert await client.ping() is True
    await client.aclose()


async def test_bootstrap_redis_unreachable_raises(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    app = FastAPI()
    with pytest.raises(RuntimeError, match="Cannot reach Redis"):
        await bootstrap_redis(app)
    assert not hasattr(app.state, "redis")


def test_get_redis_returns_state_client():
    sentinel = object()
    app = FastAPI()
    app.state.redis = sentinel
    request = SimpleNamespace(app=app)
    assert get_redis(request) is sentinel