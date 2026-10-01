"""Generic async CRUD."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


class CRUDBase(Generic[ModelT, CreateT, UpdateT]):
    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    def _column_keys(self) -> set[str]:
        return {attr.key for attr in self.model.__mapper__.column_attrs}

    async def get(self, session: AsyncSession, id: int) -> ModelT | None:
        return await session.get(self.model, id)

    async def list(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelT]:
        stmt = (
            select(self.model)
            .order_by(self.model.id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        session: AsyncSession,
        *,
        data: dict[str, Any],
    ) -> ModelT:
        unknown = set(data) - self._column_keys()
        if unknown:
            raise ValueError(
                f"Unknown columns for {self.model.__name__}: {sorted(unknown)}"
            )
        obj = self.model(**data)
        session.add(obj)
        await session.flush()
        return obj

    async def update(
        self,
        session: AsyncSession,
        *,
        id: int,
        data: dict[str, Any],
    ) -> ModelT | None:
        obj = await self.get(session, id)
        if obj is None:
            return None

        unknown = set(data) - self._column_keys()
        if unknown:
            raise ValueError(
                f"Unknown columns for {self.model.__name__}: {sorted(unknown)}"
            )
        
        for key, value in data.items():
            setattr(obj, key, value)
        await session.flush()
        return obj

    async def delete(self, session: AsyncSession, *, id: int) -> bool:
        obj = await self.get(session, id)
        if obj is None:
            return False
        await session.delete(obj)
        await session.flush()
        return True