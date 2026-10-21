"""CRUD for clients."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Client


class CRUDClient(CRUDBase[Client]):
    """CRUD operations for clients."""

    async def get_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> Client | None:
        """Fetch a client by exact email."""
        stmt = select(Client).where(Client.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_with_hash(
        self,
        session: AsyncSession,
        *,
        data: dict[str, Any],
        password_hash: str,
    ) -> Client:
        """Insert a client with a pre-computed password hash.

        Args:
            session: Active async session.
            data: Column values of the client (without ``password``; the
                service layer strips it).
            password_hash: Pre-computed argon2 digest.

        Returns:
            The flushed and refreshed client.

        Raises:
            ValueError: ``data`` contains an unknown column.
        """
        payload = {**data, "password_hash": password_hash}
        self._validate_columns(payload)
        obj = Client(**payload)
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def activate(self, session: AsyncSession, *, id: int) -> Client | None:
        """Set ``is_active`` to True."""
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = True
        await session.flush()
        return obj

    async def deactivate(self, session: AsyncSession, *, id: int) -> Client | None:
        """Set ``is_active`` to False."""
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = False
        await session.flush()
        return obj


client = CRUDClient(Client)