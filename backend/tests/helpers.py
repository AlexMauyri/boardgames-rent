"""Builders for the order-flow tests.

Every builder commits and returns plain ids, so tests do not depend on ORM
objects that a later rollback would expire.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.crud import game_copy
from app.schemas import (
    BoardGameCreate,
    ClientCreate,
    EmployeeCreate,
    OrderCreate,
    PickupPointCreate,
)
from app.services import (
    add_new_game_to_catalog,
    create_employee,
    create_pickup_point,
    register_client,
)


async def make_point(session, name: str = "Center") -> int:
    point = await create_pickup_point(
        session, PickupPointCreate(name=name, address="addr", phone="+7"),
    )
    return point.id


async def make_client(session, email: str = "client@test.io") -> int:
    row = await register_client(session, ClientCreate(
        email=email, password="secret1", full_name="Client", phone="+7",
    ))
    return row.id


async def make_employee(session, role: str, email: str) -> int:
    row = await create_employee(session, EmployeeCreate(
        email=email, password="secret1", full_name="Staff", phone="+7",
        role=role,
    ))
    return row.id


async def make_courier(session, email: str = "courier@test.io") -> int:
    return await make_employee(session, "COURIER", email)


async def make_game(
    session,
    title: str = "Dune",
    daily: str = "300",
    deposit: str = "1000",
) -> int:
    game = await add_new_game_to_catalog(session, BoardGameCreate(
        title=title, min_players=2, max_players=4, playtime_minutes=90,
        daily_price=Decimal(daily), deposit_price=Decimal(deposit),
    ))
    return game.id


async def make_copy(
    session,
    game_id: int,
    point_id: int | None,
    inventory_number: str,
    status: str = "AVAILABLE",
) -> int:
    row = await game_copy.create(session, data={
        "game_id": game_id,
        "current_point_id": point_id,
        "inventory_number": inventory_number,
        "status": status,
    })
    await session.commit()
    return row.id


def order_request(
    pickup_point_id: int,
    game_ids: list[int],
    days: int = 3,
    starts_in: int = 1,
) -> OrderCreate:
    """Build an order starting `starts_in` days from today, `days` long."""
    start = date.today() + timedelta(days=starts_in)
    return OrderCreate(
        pickup_point_id=pickup_point_id,
        start_date=start,
        end_date=start + timedelta(days=days - 1),
        game_ids=game_ids,
    )


async def make_manager(
    session,
    point_id: int,
    email: str = "manager@test.io",
) -> int:
    row = await create_employee(session, EmployeeCreate(
        email=email, password="secret1", full_name="Manager", phone="+7",
        role="MANAGER", pickup_point_id=point_id,
    ))
    return row.id
