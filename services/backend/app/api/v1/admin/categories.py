"""Admin: category management. Every change drops the cached catalog."""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, get_session
from app.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.services import admin_categories, catalog_cache

router = APIRouter()


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    payload: CategoryCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> CategoryRead:
    """Create a category. 409 if the name is taken."""
    result = await admin_categories.create_category(session, payload)
    await catalog_cache.invalidate_catalog(redis_client, categories=True)
    return result


@router.put("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> CategoryRead:
    """Rename a category. 409 if the new name is taken."""
    result = await admin_categories.update_category(
        session, category_id, payload,
    )
    await catalog_cache.invalidate_catalog(redis_client, categories=True)
    return result


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> None:
    """Delete a category; games lose it from their category set."""
    await admin_categories.delete_category(session, category_id)
    await catalog_cache.invalidate_catalog(redis_client, categories=True)
