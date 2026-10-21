"""Tests for app.auth.nonce."""

import asyncio

from app.auth.nonce import (
    DEFAULT_NONCE_TTL_SECONDS,
    consume_nonce,
    issue_nonce,
)


async def test_issue_returns_hex_and_stores_in_redis(redis_client):
    value = await issue_nonce(redis_client)

    assert len(value) == 32
    assert all(c in "0123456789abcdef" for c in value)

    stored = await redis_client.get(f"dpop:nonce:{value}")
    assert stored is not None


async def test_issue_sets_ttl(redis_client):
    value = await issue_nonce(redis_client)
    ttl = await redis_client.ttl(f"dpop:nonce:{value}")
    assert 0 < ttl <= DEFAULT_NONCE_TTL_SECONDS


async def test_issue_returns_distinct_values(redis_client):
    values = {await issue_nonce(redis_client) for _ in range(10)}
    assert len(values) == 10


async def test_issue_respects_custom_ttl(redis_client):
    value = await issue_nonce(redis_client, ttl_seconds=10)
    ttl = await redis_client.ttl(f"dpop:nonce:{value}")
    assert 0 < ttl <= 10


async def test_consume_deletes_and_returns_true(redis_client):
    value = await issue_nonce(redis_client)
    assert await consume_nonce(redis_client, value) is True
    assert await redis_client.get(f"dpop:nonce:{value}") is None


async def test_consume_returns_false_when_absent(redis_client):
    assert await consume_nonce(redis_client, "never-issued") is False


async def test_consume_returns_false_on_second_call(redis_client):
    value = await issue_nonce(redis_client)
    assert await consume_nonce(redis_client, value) is True
    assert await consume_nonce(redis_client, value) is False


async def test_consume_returns_false_for_empty_string(redis_client):
    assert await consume_nonce(redis_client, "") is False


async def test_consume_returns_false_for_expired_nonce(redis_client):
    value = await issue_nonce(redis_client, ttl_seconds=1)
    await asyncio.sleep(1.1)
    assert await consume_nonce(redis_client, value) is False