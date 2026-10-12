"""Cover image service backed by S3-compatible object storage.

The MinIO SDK is synchronous; every network call is dispatched through
``anyio.to_thread.run_sync`` so the event loop stays free.
"""

import io
import logging
import mimetypes
from uuid import uuid4

import anyio.to_thread
from fastapi import UploadFile
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud import board_game
from app.schemas import CoverUploadResponse
from app.services.exceptions import NotFoundError, ServiceValueError

logger = logging.getLogger(__name__)


def _extension_for(content_type: str) -> str:
    """Return a filename extension (with dot) for an image MIME type."""
    return mimetypes.guess_extension(content_type) or ""


def _public_url(key: str) -> str:
    """Build the browser-facing URL for a stored object key."""
    base = settings.public_base_url.rstrip("/")
    return f"{base}/{settings.s3_bucket}/{key}"


async def _put_object(s3: Minio, key: str, data: bytes, content_type: str) -> None:
    """Upload bytes to S3 off the event loop."""
    await anyio.to_thread.run_sync(
        s3.put_object,
        settings.s3_bucket,
        key,
        io.BytesIO(data),
        len(data),
        content_type,
    )


async def _remove_object(s3: Minio, key: str) -> None:
    """Delete an object from S3 off the event loop."""
    await anyio.to_thread.run_sync(s3.remove_object, settings.s3_bucket, key)


async def upload_cover(
    session: AsyncSession,
    s3: Minio,
    game_id: int,
    file: UploadFile,
) -> CoverUploadResponse:
    """Store a cover image and point the game at it.

    The new object is uploaded before the old one is removed, so a failed
    upload never leaves the game without a cover.

    Args:
        session: Active async session.
        s3: Shared S3 client.
        game_id: Primary key of the board game.
        file: The uploaded image.

    Returns:
        The stored key and its public URL.

    Raises:
        NotFoundError: No board game with that id.
        ServiceValueError: Content type is not allowed, or the file is too large.
    """
    game = await board_game.get(session, game_id)
    if game is None:
        raise NotFoundError("BoardGame", game_id)

    content_type = file.content_type or ""
    if content_type not in settings.upload_allowed_mime_types:
        raise ServiceValueError(
            f"Unsupported content type {content_type!r}; "
            f"allowed: {settings.upload_allowed_mime_types}"
        )

    data = await file.read()
    if len(data) > settings.upload_max_bytes:
        raise ServiceValueError(
            f"File too large: {len(data)} bytes > {settings.upload_max_bytes}"
        )

    new_key = f"covers/{game_id}/{uuid4().hex}{_extension_for(content_type)}"
    old_key = game.cover_key

    await _put_object(s3, new_key, data, content_type)

    if old_key:
        try:
            await _remove_object(s3, old_key)
        except Exception:
            logger.warning("Failed to remove old cover %s", old_key, exc_info=True)

    game.cover_key = new_key
    await session.commit()

    return CoverUploadResponse(cover_key=new_key, cover_url=_public_url(new_key))


async def delete_cover(
    session: AsyncSession,
    s3: Minio,
    game_id: int,
) -> None:
    """Remove a game's cover from storage and clear its key.

    Idempotent: calling it on a game with no cover is a no-op.

    Args:
        session: Active async session.
        s3: Shared S3 client.
        game_id: Primary key of the board game.

    Raises:
        NotFoundError: No board game with that id.
    """
    game = await board_game.get(session, game_id)
    if game is None:
        raise NotFoundError("BoardGame", game_id)

    key = game.cover_key
    if not key:
        return

    await _remove_object(s3, key)
    game.cover_key = None
    await session.commit()