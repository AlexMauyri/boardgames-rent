"""CRUD for clients."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Client
from app.schemas import ClientCreate, ClientUpdate


class CRUDClient(CRUDBase[Client, ClientCreate, ClientUpdate]):
    async def get_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> Client | None:
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
        obj = Client(
            email=data.email,
            password_hash=password_hash,
            full_name=data.full_name,
            phone=data.phone,
        )
        session.add(obj)
        await session.flush()
        return obj


client = CRUDClient(Client)