"""Fixtures for HTTP-level tests against the real FastAPI app."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.cache.client import bootstrap_redis
from app.main import app as fastapi_app
from app.storage.client import bootstrap_storage


@pytest_asyncio.fixture
async def app(session, redis_client):
    """The real FastAPI app, with state initialised once per process.

    Requesting `session` and `redis_client` forces DB and Redis cleanup
    before each test; the app itself uses its own pools.
    """
    if not hasattr(fastapi_app.state, "redis"):
        await bootstrap_redis(fastapi_app)
    if not hasattr(fastapi_app.state, "s3_client"):
        await bootstrap_storage(fastapi_app)
    return fastapi_app


@pytest_asyncio.fixture
async def http(app):
    """AsyncClient bound to the app via ASGITransport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac