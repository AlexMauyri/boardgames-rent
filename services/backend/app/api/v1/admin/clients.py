"""Admin: switch client accounts on and off.

A deactivated client's access tokens stop working at once:
`get_current_client` checks `is_active` on every request.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas import ClientRead
from app.services import admin_clients

router = APIRouter()


@router.post("/{client_id}/activate", response_model=ClientRead)
async def activate_client(
    client_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClientRead:
    """Switch a client account back on."""
    return await admin_clients.activate_client(session, client_id)


@router.post("/{client_id}/deactivate", response_model=ClientRead)
async def deactivate_client(
    client_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClientRead:
    """Switch a client account off."""
    return await admin_clients.deactivate_client(session, client_id)
