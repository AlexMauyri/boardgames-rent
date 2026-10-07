"""Generic async CRUD base."""

from collections.abc import Collection
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


class CRUDBase(Generic[ModelT, CreateT, UpdateT]):
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

    async def get(self, session: AsyncSession, id: int) -> ModelT | None:
        """Fetch a row by primary key.

        Args:
            session: Active async session.
            id: Primary key value.

        Returns:
            The row, or None if no row has that id.
        """
        return await session.get(self.model, id)

    async def get_many(
        self,
        session: AsyncSession,
        ids: Collection[int],
    ) -> list[ModelT]:
        """Fetch several rows by primary key in one query, id-ascending.

        Args:
            session: Active async session.
            ids: Primary key values. Duplicates are harmless.

        Returns:
            The rows that exist; ids with no row are silently absent.
        """
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
        """List rows, id-ascending.

        Args:
            session: Active async session.
            skip: Rows to skip.
            limit: Maximum rows to return.

        Returns:
            Matching rows; empty list if none.
        """
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
        """Insert a row from a plain dict of column values.

        Args:
            session: Active async session.
            data: Column values keyed by mapped attribute name.

        Returns:
            The flushed row.

        Raises:
            ValueError: `data` contains a key that is not a mapped column.
        """
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
        """Apply a partial update to a row.

        Args:
            session: Active async session.
            id: Primary key of the row to update.
            data: Column values to set, keyed by mapped attribute name.

        Returns:
            The flushed row, or None if no row has that id.

        Raises:
            ValueError: `data` contains a key that is not a mapped column.
        """
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
        """Delete a row by primary key.

        Args:
            session: Active async session.
            id: Primary key of the row to delete.

        Returns:
            True if a row was deleted, False if no row had that id.
        """
        obj = await self.get(session, id)
        if obj is None:
            return False
        await session.delete(obj)
        await session.flush()
        return True