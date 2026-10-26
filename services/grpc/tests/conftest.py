"""Shared fixtures for recommendation gRPC service tests."""

import os

import grpc
import pytest_asyncio
from grpc_health.v1 import health_pb2
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import create_server


def _build_url(user: str, password: str) -> str:
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "boardgame_db")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


@pytest_asyncio.fixture(scope="session")
async def app_engine():
    engine = create_async_engine(
        _build_url("app_user", os.environ["APP_USER_PASSWORD"]),
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def reader_engine():
    engine = create_async_engine(
        _build_url("reader_user", os.environ["READER_USER_PASSWORD"]),
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


_CLEANUP_ORDER = (
    "app.damage_reports",
    "app.deliveries",
    "app.order_items",
    "app.orders",
    "app.game_copies",
    "app.board_games",
    "app.employees",
    "app.clients",
    "app.pickup_points",
    "app.categories",
)


async def _cleanup(session: AsyncSession) -> None:
    for table in _CLEANUP_ORDER:
        await session.execute(text(f"DELETE FROM {table}"))
    await session.commit()


@pytest_asyncio.fixture
async def app_session(app_engine):
    """Session as ``app_user``; the tables are cleared before each test."""
    factory = async_sessionmaker(
        bind=app_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with factory() as s:
        await _cleanup(s)
        yield s


@pytest_asyncio.fixture
async def reader_session(reader_engine):
    """Session as ``reader_user``; used to test read-only enforcement."""
    factory = async_sessionmaker(
        bind=reader_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def grpc_server():
    """In-process gRPC server bound to a random port (insecure, no TLS)."""
    server, health_servicer = await create_server()
    port = server.add_insecure_port("localhost:0")
    await server.start()
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    yield port

    await server.stop(grace=0)