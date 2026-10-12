"""Tests for app.services.covers."""

import io
from unittest.mock import MagicMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.config import settings
from app.crud import board_game
from app.services.covers import delete_cover, upload_cover
from app.services.exceptions import NotFoundError, ServiceValueError
from tests.helpers import make_game


def _upload(
    data: bytes,
    content_type: str = "image/png",
    filename: str = "cover.png",
) -> UploadFile:
    return UploadFile(
        io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


async def _set_cover_key(session, game_id: int, key: str | None) -> None:
    game = await board_game.get(session, game_id)
    assert game is not None
    game.cover_key = key
    await session.commit()


@pytest.fixture
def mock_s3():
    return MagicMock()


# --- upload ------------------------------------------------------------


async def test_upload_rejects_disallowed_mime(session, mock_s3):
    game = await make_game(session)
    file = _upload(b"data", content_type="text/plain")

    with pytest.raises(ServiceValueError, match="Unsupported content type"):
        await upload_cover(session, mock_s3, game, file)
    mock_s3.put_object.assert_not_called()


async def test_upload_rejects_oversized_file(session, mock_s3, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_bytes", 4)
    game = await make_game(session)
    file = _upload(b"12345", content_type="image/png")

    with pytest.raises(ServiceValueError, match="too large"):
        await upload_cover(session, mock_s3, game, file)
    mock_s3.put_object.assert_not_called()


async def test_upload_unknown_game_not_found(session, mock_s3):
    file = _upload(b"data")

    with pytest.raises(NotFoundError):
        await upload_cover(session, mock_s3, 999999, file)
    mock_s3.put_object.assert_not_called()


async def test_upload_puts_object_and_updates_key(session, mock_s3):
    game_id = await make_game(session)
    payload = b"png-bytes"
    file = _upload(payload, content_type="image/png")

    result = await upload_cover(session, mock_s3, game_id, file)

    assert result.cover_key.startswith(f"covers/{game_id}/")
    assert result.cover_key.endswith(".png")
    expected_url = (
        f"{settings.public_base_url.rstrip('/')}"
        f"/{settings.s3_bucket}/{result.cover_key}"
    )
    assert result.cover_url == expected_url

    args = mock_s3.put_object.call_args.args
    assert args[0] == settings.s3_bucket
    assert args[1] == result.cover_key
    assert args[3] == len(payload)
    assert args[4] == "image/png"

    game = await board_game.get(session, game_id)
    assert game.cover_key == result.cover_key


async def test_upload_replaces_existing_object(session, mock_s3):
    game_id = await make_game(session)
    await _set_cover_key(session, game_id, "covers/old-key.png")

    file = _upload(b"new-bytes", content_type="image/png")
    result = await upload_cover(session, mock_s3, game_id, file)

    assert result.cover_key != "covers/old-key.png"
    mock_s3.put_object.assert_called_once()
    mock_s3.remove_object.assert_called_once_with(
        settings.s3_bucket, "covers/old-key.png",
    )


async def test_upload_keeps_new_cover_when_old_removal_fails(
    session, mock_s3, monkeypatch,
):
    game_id = await make_game(session)
    await _set_cover_key(session, game_id, "covers/old-key.png")

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("storage hiccup")

    monkeypatch.setattr(
        "app.services.covers._remove_object", _boom,
    )

    file = _upload(b"new-bytes", content_type="image/png")
    result = await upload_cover(session, mock_s3, game_id, file)

    game = await board_game.get(session, game_id)
    assert game.cover_key == result.cover_key


# --- delete ------------------------------------------------------------


async def test_delete_unknown_game_not_found(session, mock_s3):
    with pytest.raises(NotFoundError):
        await delete_cover(session, mock_s3, 999999)
    mock_s3.remove_object.assert_not_called()


async def test_delete_is_noop_when_no_cover(session, mock_s3):
    game_id = await make_game(session)

    await delete_cover(session, mock_s3, game_id)

    mock_s3.remove_object.assert_not_called()


async def test_delete_removes_object_and_clears_key(session, mock_s3):
    game_id = await make_game(session)
    await _set_cover_key(session, game_id, "covers/gone.png")

    await delete_cover(session, mock_s3, game_id)

    mock_s3.remove_object.assert_called_once_with(
        settings.s3_bucket, "covers/gone.png",
    )
    game = await board_game.get(session, game_id)
    assert game.cover_key is None


async def test_delete_is_idempotent(session, mock_s3):
    game_id = await make_game(session)
    await _set_cover_key(session, game_id, "covers/once.png")

    await delete_cover(session, mock_s3, game_id)
    await delete_cover(session, mock_s3, game_id)  # no error

    mock_s3.remove_object.assert_called_once()