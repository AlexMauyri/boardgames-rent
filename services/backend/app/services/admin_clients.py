"""Client administration."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import client
from app.schemas import ClientRead
from app.services.exceptions import NotFoundError

logger = logging.getLogger(__name__)


async def activate_client(
    session: AsyncSession,
    client_id: int,
) -> ClientRead:
    """Switch a client account back on.

    Args:
        session: Active async session.
        client_id: Primary key of the client.

    Returns:
        The activated client.

    Raises:
        NotFoundError: No client with that id.
    """
    obj = await client.activate(session, id=client_id)
    if obj is None:
        raise NotFoundError("Client", client_id)
    result = ClientRead.model_validate(obj)
    await session.commit()
    logger.info("client activated client_id=%s", client_id)
    return result


async def deactivate_client(
    session: AsyncSession,
    client_id: int,
) -> ClientRead:
    """Switch a client account off.

    Args:
        session: Active async session.
        client_id: Primary key of the client.

    Returns:
        The deactivated client.

    Raises:
        NotFoundError: No client with that id.
    """
    obj = await client.deactivate(session, id=client_id)
    if obj is None:
        raise NotFoundError("Client", client_id)
    result = ClientRead.model_validate(obj)
    await session.commit()
    logger.info("client deactivated client_id=%s", client_id)
    return result