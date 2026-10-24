"""Tests for pickup point CRUD and soft-delete semantics."""

import pytest

from app.schemas import PickupPointCreate, PickupPointUpdate
from app.services import (
    activate_pickup_point,
    create_pickup_point,
    deactivate_pickup_point,
    list_pickup_points_admin,
    list_pickup_points_public,
    update_pickup_point,
)
from app.services.exceptions import ConflictError, NotFoundError


async def _make_point(session, name="North", address="addr", phone="+7"):
    return await create_pickup_point(session, PickupPointCreate(
        name=name, address=address, phone=phone,
    ))


async def test_create_pickup_point(session):
    p = await _make_point(session)
    assert p.name == "North"
    assert p.is_active is True


async def test_create_pickup_point_duplicate_name(session):
    await _make_point(session, "North")
    with pytest.raises(ConflictError):
        await _make_point(session, "North")


async def test_update_pickup_point(session):
    p = await _make_point(session)
    updated = await update_pickup_point(
        session, p.id, PickupPointUpdate(address="new addr"),
    )
    assert updated.address == "new addr"


async def test_update_pickup_point_rename_to_existing(session):
    p = await _make_point(session, "North")
    await _make_point(session, "Center")
    with pytest.raises(ConflictError):
        await update_pickup_point(session, p.id, PickupPointUpdate(name="Center"))


async def test_update_pickup_point_not_found(session):
    with pytest.raises(NotFoundError):
        await update_pickup_point(session, 999999, PickupPointUpdate(address="x"))


async def test_list_pickup_points_public(session):
    await _make_point(session, "North")
    rows = await list_pickup_points_public(session)
    assert any(p.name == "North" for p in rows)


async def test_deactivate_pickup_point(session):
    p = await _make_point(session)
    deact = await deactivate_pickup_point(session, p.id)
    assert deact.is_active is False


async def test_list_public_excludes_inactive(session):
    p = await _make_point(session, "North")
    await deactivate_pickup_point(session, p.id)
    rows = await list_pickup_points_public(session)
    assert not any(r.name == "North" for r in rows)


async def test_list_admin_includes_inactive(session):
    p = await _make_point(session, "North")
    await deactivate_pickup_point(session, p.id)
    rows = await list_pickup_points_admin(session)
    assert any(r.name == "North" for r in rows)


async def test_activate_pickup_point(session):
    p = await _make_point(session)
    await deactivate_pickup_point(session, p.id)
    act = await activate_pickup_point(session, p.id)
    assert act.is_active is True


async def test_activate_pickup_point_not_found(session):
    with pytest.raises(NotFoundError):
        await activate_pickup_point(session, 999999)


async def test_deactivate_pickup_point_not_found(session):
    with pytest.raises(NotFoundError):
        await deactivate_pickup_point(session, 999999)