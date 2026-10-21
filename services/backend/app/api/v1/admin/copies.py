"""Admin: physical game boxes across all points.

Box data is not part of the cached catalog, so nothing is invalidated here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas import (
    GameCopyCreate,
    GameCopyRead,
    GameCopyStatus,
    GameCopyUpdate,
)
from app.services import admin_copies

router = APIRouter()


@router.get("", response_model=list[GameCopyRead])
async def list_copies(
    session: Annotated[AsyncSession, Depends(get_session)],
    game_id: int | None = Query(None),
    point_id: int | None = Query(None),
    status: GameCopyStatus | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[GameCopyRead]:
    """List boxes, optionally by game, point and status."""
    return await admin_copies.list_game_copies(
        session,
        game_id=game_id,
        point_id=point_id,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.get("/{copy_id}", response_model=GameCopyRead)
async def get_copy(
    copy_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GameCopyRead:
    """Fetch a single box."""
    return await admin_copies.get_game_copy(session, copy_id)


@router.post(
    "",
    response_model=GameCopyRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_copy(
    payload: GameCopyCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GameCopyRead:
    """Register a new box; it starts AVAILABLE at an active point."""
    return await admin_copies.add_game_copy(session, payload)


@router.put("/{copy_id}", response_model=GameCopyRead)
async def update_copy(
    copy_id: int,
    payload: GameCopyUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GameCopyRead:
    """Change a box's inventory number. 409 if it is taken."""
    return await admin_copies.update_game_copy(session, copy_id, payload)
