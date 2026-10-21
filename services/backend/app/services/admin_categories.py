"""Category administration — write paths."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import category
from app.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.exceptions import ConflictError, NotFoundError

logger = logging.getLogger(__name__)


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
        logger.warning(
            "category creation rejected name=%s reason=name_taken",
            data.name,
        )
        raise ConflictError("Category", data.name)

    obj = await category.create(session, data=data.model_dump())
    result = CategoryRead.model_validate(obj)
    await session.commit()
    logger.info("category created category_id=%s name=%s", result.id, result.name)
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
            logger.warning(
                "category update rejected category_id=%s name=%s reason=name_taken",
                category_id, data.name,
            )
            raise ConflictError("Category", data.name)

    obj = await category.update(
        session,
        id=category_id,
        data=data.model_dump(exclude_unset=True),
    )
    result = CategoryRead.model_validate(obj)
    await session.commit()
    logger.info(
        "category updated category_id=%s changed_fields=%s",
        category_id, sorted(data.model_fields_set),
    )
    return result


async def delete_category(session: AsyncSession, category_id: int) -> None:
    """Delete a category.

    Args:
        session: Active async session.
        category_id: Primary key of the category.

    Raises:
        NotFoundError: No category with that id.
    """
    current = await category.get(session, category_id)
    if current is None:
        raise NotFoundError("Category", category_id)
    name = current.name

    deleted = await category.delete(session, id=category_id)
    if not deleted:
        raise NotFoundError("Category", category_id)
    await session.commit()
    logger.info("category deleted category_id=%s name=%s", category_id, name)