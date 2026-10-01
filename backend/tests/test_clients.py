"""Tests for client activation and its effect on authentication."""

import pytest

from app.schemas import ClientCreate
from app.services import (
    activate_client,
    authenticate_client,
    deactivate_client,
    register_client,
)
from app.services.exceptions import NotFoundError


async def _make_client(session, email="c@test.io"):
    return await register_client(session, ClientCreate(
        email=email, password="secret1",
        full_name="C", phone="+7",
    ))


async def test_deactivate_client(session):
    c = await _make_client(session)
    deact = await deactivate_client(session, c.id)
    assert deact.is_active is False


async def test_authenticate_inactive_client_returns_none(session):
    c = await _make_client(session, "c@test.io")
    await deactivate_client(session, c.id)
    res = await authenticate_client(session, "c@test.io", "secret1")
    assert res is None


async def test_activate_client(session):
    c = await _make_client(session)
    await deactivate_client(session, c.id)
    act = await activate_client(session, c.id)
    assert act.is_active is True


async def test_activate_client_not_found(session):
    with pytest.raises(NotFoundError):
        await activate_client(session, 999999)


async def test_deactivate_client_not_found(session):
    with pytest.raises(NotFoundError):
        await deactivate_client(session, 999999)