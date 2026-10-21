"""Tests for the public read-only catalog services."""

from app.schemas import CategoryCreate, PickupPointCreate
from app.services import (
    create_category,
    create_pickup_point,
    list_categories,
    list_pickup_points_public,
)


async def test_list_categories(session):
    await create_category(session, CategoryCreate(name="Strategy"))
    await create_category(session, CategoryCreate(name="Coop"))
    rows = await list_categories(session)
    assert len(rows) == 2


async def test_list_pickup_points_public_returns_only_active(session):
    active = await create_pickup_point(session, PickupPointCreate(
        name="Active", address="a", phone="+7",
    ))
    inactive = await create_pickup_point(session, PickupPointCreate(
        name="Inactive", address="b", phone="+7",
    ))
    
    from app.services import deactivate_pickup_point
    await deactivate_pickup_point(session, inactive.id)

    rows = await list_pickup_points_public(session)
    names = {p.name for p in rows}
    assert "Active" in names
    assert "Inactive" not in names