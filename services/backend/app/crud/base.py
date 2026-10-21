"""Generic async CRUD base."""

from collections.abc import Collection
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class CRUDBase(Generic[ModelT]):
    """Generic CRUD operations over a single SQLAlchemy model."""

    def __init__(self, model: type[ModelT]) -> None:
        """Bind the base to a concrete ORM model.

        Args:
            model: The SQLAlchemy mapped class this instance manages.
        """
        self.model = model

    def _column_keys(self) -> set[str]:
        """Return the set of column attribute names on the bound model.

        Returns:
            Attribute names of every mapped column.
        """
        return {attr.key for attr in self.model.__mapper__.column_attrs}

    def _validate_columns(self, data: dict[str, Any]) -> None:
        """Reject dict keys that are not mapped columns.

        Args:
            data: Column values keyed by attribute name.

        Raises:
            ValueError: `data` contains an unknown key.
        """
        unknown = set(data) - self._column_keys()
        if unknown:
            raise ValueError(
                f"Unknown columns for {self.model.__name__}: {sorted(unknown)}"
            )

    async def get(self, session: AsyncSession, id: int) -> ModelT | None:
        """Fetch a row by primary key."""
        return await session.get(self.model, id)

    async def get_many(
        self,
        session: AsyncSession,
        ids: Collection[int],
    ) -> list[ModelT]:
        """Fetch several rows by primary key in one query, id-ascending."""
        if not ids:
            return []
        stmt = (
            select(self.model)
            .where(self.model.id.in_(set(ids)))
            .order_by(self.model.id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelT]:
        """List rows, id-ascending."""
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
        """Insert a row from a plain dict of column values."""
        self._validate_columns(data)
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
        """Apply a partial update to a row."""
        obj = await self.get(session, id)
        if obj is None:
            return None
        self._validate_columns(data)
        for key, value in data.items():
            setattr(obj, key, value)
        await session.flush()
        return obj

    async def delete(self, session: AsyncSession, *, id: int) -> bool:
        """Delete a row by primary key."""
        obj = await self.get(session, id)
        if obj is None:
            return False
        await session.delete(obj)
        await session.flush()
        return True