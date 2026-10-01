"""Category administration — write paths."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import category
from app.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.exceptions import ConflictError, NotFoundError


async def create_category(session: AsyncSession, data: CategoryCreate) -> CategoryRead:
    """Create a category.

    Args:
        session: Active async session.
        data: Validated creation payload.

    Returns:
        The created category.

    Raises:
        ConflictError: A category with that name already exists.
    """
    existing = await category.get_by_name(session, data.name)
    if existing is not None:
        raise ConflictError("Category", data.name)

    obj = await category.create(session, data=data.model_dump())
    result = CategoryRead.model_validate(obj)
    await session.commit()
    return result


async def update_category(
    session: AsyncSession,
    category_id: int,
    data: CategoryUpdate,
) -> CategoryRead:
    """Update a category.

    Args:
        session: Active async session.
        category_id: Primary key of the category.
        data: Partial update payload; unset fields are left alone.

    Returns:
        The updated category.

    Raises:
        NotFoundError: No category with that id.
        ConflictError: The new name belongs to a different category.
    """
    current = await category.get(session, category_id)
    if current is None:
        raise NotFoundError("Category", category_id)

    if data.name is not None and data.name != current.name:
        clash = await category.get_by_name(session, data.name)
        if clash is not None and clash.id != category_id:
            raise ConflictError("Category", data.name)

    obj = await category.update(
        session,
        id=category_id,
        data=data.model_dump(exclude_unset=True),
    )
    result = CategoryRead.model_validate(obj)
    await session.commit()
    return result


async def delete_category(session: AsyncSession, category_id: int) -> None:
    """Delete a category.

    Args:
        session: Active async session.
        category_id: Primary key of the category.

    Raises:
        NotFoundError: No category with that id.
    """
    deleted = await category.delete(session, id=category_id)
    if not deleted:
        raise NotFoundError("Category", category_id)
    await session.commit()