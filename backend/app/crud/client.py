"""CRUD for clients."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Client
from app.schemas import ClientCreate, ClientUpdate


class CRUDClient(CRUDBase[Client, ClientCreate, ClientUpdate]):
    """CRUD operations for clients."""

    async def get_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> Client | None:
        """Fetch a client by exact email.

        Args:
            session: Active async session.
            email: Exact, case-sensitive email address.

        Returns:
            The matching client, or None.
        """
        stmt = select(Client).where(Client.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_with_hash(
        self,
        session: AsyncSession,
        *,
        data: ClientCreate,
        password_hash: str,
    ) -> Client:
        """Insert a client with a pre-computed password hash.

        Args:
            session: Active async session.
            data: Validated creation payload.
            password_hash: Pre-computed argon2 digest.

        Returns:
            The flushed and refreshed client.
        """
        obj = Client(
            email=data.email,
            password_hash=password_hash,
            full_name=data.full_name,
            phone=data.phone,
        )
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def activate(
        self,
        session: AsyncSession,
        *,
        id: int,
    ) -> Client | None:
        """Set `is_active` to True.

        Args:
            session: Active async session.
            id: Primary key of the client.

        Returns:
            The activated client, or None if no row has that id.
        """
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = True
        await session.flush()
        return obj

    async def deactivate(
        self,
        session: AsyncSession,
        *,
        id: int,
    ) -> Client | None:
        """Set `is_active` to False.

        Args:
            session: Active async session.
            id: Primary key of the client.

        Returns:
            The deactivated client, or None if no row has that id.
        """
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = False
        await session.flush()
        return obj


client = CRUDClient(Client)