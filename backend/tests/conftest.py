"""Shared fixtures for the service layer tests."""
import base64
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dpop import compute_jwk_thumbprint
from app.db.models import (
    BoardGame,
    Category,
    Client,
    DamageReport,
    Delivery,
    Employee,
    GameCopy,
    Order,
    OrderItem,
    PickupPoint,
)
from app.db.session import SessionFactory
from app.cache.client import build_redis


_CLEANUP_ORDER = (
    DamageReport,
    Delivery,
    OrderItem,
    Order,
    GameCopy,
    BoardGame,
    Employee,
    Client,
    PickupPoint,
    Category,
)


async def _truncate_all(session: AsyncSession) -> None:
    """Remove every row from the tables this test suite owns."""
    for model in _CLEANUP_ORDER:
        rows = (await session.execute(select(model))).scalars().all()
        for row in rows:
            await session.delete(row)
    await session.commit()


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Yield a clean AsyncSession for a single test.

    Cleans the tables before yielding, so tests are independent regardless
    of whether a previous test failed mid-way and skipped its own cleanup.
    """
    async with SessionFactory() as s:
        await _truncate_all(s)
        yield s


@pytest_asyncio.fixture
async def redis_client():
    """Yield a Redis client pointing at the test DB, emptied first.

    Assumes REDIS_URL points at a database dedicated to tests — the
    fixture runs FLUSHDB, which wipes whatever is in that DB.
    """
    client = build_redis()
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


def _b64url(data: bytes) -> str:
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
def dpop_keypair():
    """Return (private_key, public_jwk, thumbprint) for ES256 testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwk = _public_jwk(private_key)
    return private_key, jwk, compute_jwk_thumbprint(jwk)


@pytest.fixture
def make_dpop_proof(dpop_keypair):
    """Return a callable that builds and signs DPoP proofs.

    Signature: ``make(htm, htu, nonce=None, iat=None, jti=None) -> str``.
    """
    private_key, jwk, _ = dpop_keypair

    def _make(
        *,
        htm: str = "POST",
        htu: str,
        nonce: str | None = None,
        iat: int | None = None,
        jti: str | None = None,
    ) -> str:
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": jwk}
        payload = {
            "jti": jti if jti is not None else str(uuid.uuid4()),
            "htm": htm,
            "htu": htu,
            "iat": iat if iat is not None else int(time.time()),
        }
        if nonce is not None:
            payload["nonce"] = nonce
        return jwt.encode(
            payload, private_key, algorithm="ES256", headers=header,
        )

    return _make


async def do_auth_request(
    http,
    method: str,
    path: str,
    make_proof,
    *,
    body: dict | None = None,
    max_attempts: int = 2,
):
    """Send a DPoP-authenticated request, handling nonce challenges."""
    url = f"http://test{path}"
    proof = make_proof(htm=method, htu=url)
    headers = {"DPoP": proof, "Content-Type": "application/json"}
    content = json.dumps(body) if body is not None else None

    last = None
    for _ in range(max_attempts):
        last = await http.request(method, path, content=content, headers=headers)
        nonce = last.headers.get("DPoP-Nonce")
        if last.status_code == 401 and nonce:
            proof = make_proof(htm=method, htu=url, nonce=nonce)
            headers["DPoP"] = proof
            continue
        return last

    return last