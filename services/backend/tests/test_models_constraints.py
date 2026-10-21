"""Database-level guarantees of the order-flow tables.

Rows are inserted with Core `insert()` so that the database, not the ORM's
identity map or Pydantic, is what rejects bad data. Each negative test names
the constraint it expects, so a failure for the wrong reason is caught.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.db.models import (
    BoardGame,
    Client,
    DamageReport,
    Delivery,
    Employee,
    GameCopy,
    Order,
    OrderItem,
    PickupPoint,
)
from app.schemas import OrderDetailRead


@dataclass
class World:
    """Primary keys of one committed, valid set of parent rows."""

    point_a: int
    point_b: int
    client: int
    courier: int
    game: int
    copy: int


async def _insert_id(session, model, **values) -> int:
    """Insert one row with Core and return its generated id."""
    result = await session.execute(
        insert(model).values(**values).returning(model.id)
    )
    return result.scalar_one()


async def _make_world(session) -> World:
    point_a = await _insert_id(
        session, PickupPoint, name="Center", address="a", phone="+7",
    )
    point_b = await _insert_id(
        session, PickupPoint, name="North", address="b", phone="+7",
    )
    client = await _insert_id(
        session, Client,
        email="c@test.io", password_hash="x", full_name="C", phone="+7",
    )
    courier = await _insert_id(
        session, Employee,
        email="courier@test.io", password_hash="x", full_name="K",
        phone="+7", role="COURIER",
    )
    game = await _insert_id(
        session, BoardGame,
        title="Dune", min_players=2, max_players=4, playtime_minutes=90,
        daily_price=Decimal("300"), deposit_price=Decimal("1000"),
    )
    copy = await _insert_id(
        session, GameCopy,
        game_id=game, current_point_id=point_a, inventory_number="INV-1",
        status="AVAILABLE",
    )
    await session.commit()
    return World(point_a, point_b, client, courier, game, copy)


async def _make_order(session, w: World, **overrides) -> int:
    values = dict(
        client_id=w.client,
        pickup_point_id=w.point_a,
        start_date=date(2026, 10, 10),
        end_date=date(2026, 10, 12),
        total_price=Decimal("600"),
        deposit_paid=Decimal("1000"),
    )
    values.update(overrides)
    order_id = await _insert_id(session, Order, **values)
    await session.commit()
    return order_id


async def _assert_rejected(session, statement, constraint: str) -> None:
    """Run `statement`, expect the DB to reject it, and check which rule."""
    with pytest.raises(IntegrityError) as exc:
        await session.execute(statement)
    await session.rollback()
    assert constraint in str(exc.value)


async def test_valid_chain_persists_and_relationships_load(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    await session.execute(insert(OrderItem).values(
        order_id=order_id, game_copy_id=w.copy,
        price_at_rental=Decimal("300"),
    ))
    await _insert_id(
        session, Delivery,
        order_id=order_id, from_point_id=w.point_b, to_point_id=w.point_a,
    )
    await _insert_id(
        session, DamageReport,
        game_copy_id=w.copy, order_id=order_id, reported_by=w.courier,
        description="Torn box",
    )
    await session.commit()

    order = (await session.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.delivery))
        .where(Order.id == order_id)
    )).scalar_one()
    assert order.status == "CREATED"
    assert [i.game_copy_id for i in order.items] == [w.copy]
    assert order.delivery.status == "CREATED"
    assert order.delivery.courier_id is None

    detail = OrderDetailRead.model_validate(order)
    assert detail.items[0].price_at_rental == Decimal("300.00")

    delivery = (await session.execute(
        select(Delivery).options(
            selectinload(Delivery.from_point),
            selectinload(Delivery.to_point),
        )
    )).scalar_one()
    assert delivery.from_point.name == "North"
    assert delivery.to_point.name == "Center"

    report = (await session.execute(select(DamageReport))).scalar_one()
    assert report.deposit_withheld == Decimal("0")


async def test_copy_available_requires_a_point(session):
    w = await _make_world(session)
    await _assert_rejected(session, insert(GameCopy).values(
        game_id=w.game, current_point_id=None,
        inventory_number="INV-2", status="AVAILABLE",
    ), "ck_game_copies_location_matches_status")


async def test_copy_in_transit_must_have_no_point(session):
    w = await _make_world(session)
    await _assert_rejected(session, insert(GameCopy).values(
        game_id=w.game, current_point_id=w.point_a,
        inventory_number="INV-2", status="IN_TRANSIT",
    ), "ck_game_copies_location_matches_status")


async def test_copy_unknown_status_rejected(session):
    w = await _make_world(session)
    # Both status checks fail; which one Postgres reports first is not
    # specified, so only the table prefix is asserted.
    await _assert_rejected(session, insert(GameCopy).values(
        game_id=w.game, current_point_id=w.point_a,
        inventory_number="INV-2", status="LOST",
    ), "ck_game_copies")


async def test_copy_inventory_number_is_unique(session):
    w = await _make_world(session)
    await _assert_rejected(session, insert(GameCopy).values(
        game_id=w.game, current_point_id=w.point_a,
        inventory_number="INV-1", status="AVAILABLE",
    ), "uq_game_copies_inventory_number")


async def test_order_end_date_before_start_rejected(session):
    w = await _make_world(session)
    await _assert_rejected(session, insert(Order).values(
        client_id=w.client, pickup_point_id=w.point_a,
        start_date=date(2026, 10, 12), end_date=date(2026, 10, 10),
        total_price=Decimal("0"), deposit_paid=Decimal("0"),
    ), "ck_orders_end_date")


async def test_order_unknown_status_rejected(session):
    w = await _make_world(session)
    await _assert_rejected(session, insert(Order).values(
        client_id=w.client, pickup_point_id=w.point_a,
        start_date=date(2026, 10, 10), end_date=date(2026, 10, 12),
        total_price=Decimal("0"), deposit_paid=Decimal("0"),
        status="LOST",
    ), "ck_orders_status")


async def test_order_negative_total_price_rejected(session):
    w = await _make_world(session)
    await _assert_rejected(session, insert(Order).values(
        client_id=w.client, pickup_point_id=w.point_a,
        start_date=date(2026, 10, 10), end_date=date(2026, 10, 12),
        total_price=Decimal("-1"), deposit_paid=Decimal("0"),
    ), "ck_orders_total_price")


async def test_order_item_same_copy_twice_rejected(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    row = dict(order_id=order_id, game_copy_id=w.copy,
               price_at_rental=Decimal("300"))
    await session.execute(insert(OrderItem).values(**row))
    await session.commit()
    await _assert_rejected(
        session, insert(OrderItem).values(**row), "pk_order_items",
    )


async def test_order_item_negative_price_rejected(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    await _assert_rejected(session, insert(OrderItem).values(
        order_id=order_id, game_copy_id=w.copy,
        price_at_rental=Decimal("-1"),
    ), "ck_order_items_price_at_rental")


async def test_delivery_from_and_to_must_differ(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    await _assert_rejected(session, insert(Delivery).values(
        order_id=order_id, from_point_id=w.point_a, to_point_id=w.point_a,
    ), "ck_deliveries_distinct_points")


async def test_order_has_at_most_one_delivery(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    values = dict(order_id=order_id, from_point_id=w.point_b,
                  to_point_id=w.point_a)
    await session.execute(insert(Delivery).values(**values))
    await session.commit()
    await _assert_rejected(
        session, insert(Delivery).values(**values), "uq_deliveries_order_id",
    )


async def test_delivery_unknown_status_rejected(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    await _assert_rejected(session, insert(Delivery).values(
        order_id=order_id, from_point_id=w.point_b, to_point_id=w.point_a,
        status="LOST",
    ), "ck_deliveries_status")


async def test_damage_report_negative_withheld_rejected(session):
    w = await _make_world(session)
    await _assert_rejected(session, insert(DamageReport).values(
        game_copy_id=w.copy, reported_by=w.courier,
        description="Torn box", deposit_withheld=Decimal("-1"),
    ), "ck_damage_reports_deposit_withheld")


async def test_cannot_delete_client_with_orders(session):
    w = await _make_world(session)
    await _make_order(session, w)
    await _assert_rejected(
        session,
        delete(Client).where(Client.id == w.client),
        "fk_orders_client_id_clients",
    )


async def test_cannot_delete_copy_that_is_in_an_order(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    await session.execute(insert(OrderItem).values(
        order_id=order_id, game_copy_id=w.copy,
        price_at_rental=Decimal("300"),
    ))
    await session.commit()
    await _assert_rejected(
        session,
        delete(GameCopy).where(GameCopy.id == w.copy),
        "fk_order_items_game_copy_id_game_copies",
    )


async def test_deleting_order_cascades_to_its_items(session):
    w = await _make_world(session)
    order_id = await _make_order(session, w)
    await session.execute(insert(OrderItem).values(
        order_id=order_id, game_copy_id=w.copy,
        price_at_rental=Decimal("300"),
    ))
    await session.commit()

    await session.execute(delete(Order).where(Order.id == order_id))
    await session.commit()

    remaining = await session.scalar(select(func.count()).select_from(OrderItem))
    assert remaining == 0
