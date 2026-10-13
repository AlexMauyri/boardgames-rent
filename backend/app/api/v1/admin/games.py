"""Admin: catalog games and their cover images.

Every change drops the cached game list and game cards.
"""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Body, Depends, File, UploadFile, status
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, get_session, get_storage_client
from app.schemas import (
    BoardGameCreate,
    BoardGameRead,
    BoardGameUpdate,
    CoverUploadResponse,
)
from app.services import admin_games, catalog_cache, covers

router = APIRouter()


@router.post(
    "",
    response_model=BoardGameRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_game(
    payload: BoardGameCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> BoardGameRead:
    """Add a game to the catalog."""
    result = await admin_games.add_new_game_to_catalog(session, payload)
    await catalog_cache.invalidate_catalog(redis_client, games=True)
    return result


@router.put("/{game_id}", response_model=BoardGameRead)
async def update_game(
    game_id: int,
    payload: BoardGameUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> BoardGameRead:
    """Edit a game; `category_ids`, if given, replaces its category set."""
    result = await admin_games.update_game(session, game_id, payload)
    await catalog_cache.invalidate_catalog(redis_client, games=True)
    return result


@router.put("/{game_id}/categories", response_model=BoardGameRead)
async def set_game_categories(
    game_id: int,
    category_ids: Annotated[list[int], Body()],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> BoardGameRead:
    """Replace the game's category set; `[]` clears it."""
    result = await admin_games.set_game_categories(
        session, game_id, category_ids,
    )
    await catalog_cache.invalidate_catalog(redis_client, games=True)
    return result


@router.post("/{game_id}/cover", response_model=CoverUploadResponse)
async def upload_cover(
    game_id: int,
    file: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    s3: Annotated[Minio, Depends(get_storage_client)],
) -> CoverUploadResponse:
    """Upload a cover image, replacing the previous one."""
    result = await covers.upload_cover(session, s3, game_id, file)
    await catalog_cache.invalidate_catalog(redis_client, games=True)
    return result


@router.delete("/{game_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cover(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    s3: Annotated[Minio, Depends(get_storage_client)],
) -> None:
    """Remove the cover image. A game without a cover is not an error."""
    await covers.delete_cover(session, s3, game_id)
    await catalog_cache.invalidate_catalog(redis_client, games=True)
