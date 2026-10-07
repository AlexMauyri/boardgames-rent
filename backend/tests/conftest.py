"""Shared fixtures for the service layer tests."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


# Children before parents: every FK to these tables is ON DELETE RESTRICT.
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