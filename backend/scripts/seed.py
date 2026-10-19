"""Fill the database with test data.

    uv run python -m scripts.seed            # only into an empty database
    uv run python -m scripts.seed --reset    # wipe everything, then fill

All rows go through the service layer, so passwords are hashed and every
business rule applies exactly as it does for real requests.

Reference data (points, categories, games, copies, employees, clients,
orders) is read from JSON files in `scripts/data/`. Cover images are
looked up in `scripts/data/covers/` by filename; if a file is missing it
is silently skipped, so the script works with or without images.

The tests wipe the same database; seed again after running them, or point
the tests at a separate database with the POSTGRES_DB environment variable.
"""

import argparse
import asyncio
import io
import json
import mimetypes
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers, UploadFile

from app.crud import pickup_point
from app.db.base import Base
from app.db.session import SessionFactory, engine
from app.schemas import (
    BoardGameCreate,
    CategoryCreate,
    ClientCreate,
    EmployeeCreate,
    GameCopyCreate,
    OrderCreate,
    OrderReturnCreate,
    PickupPointCreate,
    ReturnDamage,
)
from app.services import (
    add_game_copy,
    add_new_game_to_catalog,
    create_category,
    create_employee,
    create_pickup_point,
    deactivate_client,
    deactivate_pickup_point,
    register_client,
)
from app.services import covers as covers_service
from app.services import deliveries as deliveries_service
from app.services import manager as manager_service
from app.services import orders as orders_service
from app.crud import delivery as delivery_crud
from app.crud import game_copy as game_copy_crud
from app.crud import order as order_crud
from app.storage.client import build_s3_client
from scripts.console import confirm_wipe, database_label, setup_output

SEED_PASSWORD = "demo-password"

_DATA_DIR = Path(__file__).parent / "data"
_COVERS_DIR = _DATA_DIR / "covers"


@dataclass
class SeedIds:
    """Primary keys of the seeded rows, for cross-references."""

    points: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    games: dict[str, int] = field(default_factory=dict)
    games_by_id: dict[int, str] = field(default_factory=dict)
    employees: dict[str, int] = field(default_factory=dict)
    employees_data: dict[str, dict] = field(default_factory=dict)
    clients: dict[str, int] = field(default_factory=dict)
    accounts: list[tuple[str, str]] = field(default_factory=list)


def load_json(name: str) -> list[dict]:
    """Load `scripts/data/{name}.json`."""
    return json.loads((_DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def maybe_upload_cover(
    s3: Minio,
    game_id: int,
    cover_file: str | None,
) -> None:
    """Upload `scripts/data/covers/{cover_file}` if present, else skip.

    Errors are logged, never raised — a broken cover must not abort the seed.
    """
    if not cover_file:
        return
    path = _COVERS_DIR / cover_file
    if not path.exists():
        print(f"  · cover {cover_file}: not found, skipping")
        return

    data = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    print(f"  · cover {cover_file}: uploading ({len(data)} bytes, {content_type})")
    from app.config import settings
    key = f"covers/{game_id}/{cover_file}"
    try:
        s3.put_object(
            settings.s3_bucket,
            key,
            io.BytesIO(data),
            len(data),
            content_type,
        )
        # Track cover_key via ORM (upload_cover needs UploadFile + service plumbing;
        # direct put is simpler for a batch seed).
        from app.crud import board_game as game_crud
        # caller does this synchronously outside the event loop; use a sync update below
        return key
    except Exception as exc:
        print(f"  ! cover {cover_file}: failed ({exc})")


async def set_cover_key(
    session: AsyncSession,
    game_id: int,
    key: str,
) -> None:
    """Set board_games.cover_key directly (upload already done)."""
    from app.crud import board_game as game_crud
    await game_crud.update(session, id=game_id, data={"cover_key": key})
    await session.commit()


async def reset_database(session: AsyncSession) -> None:
    """Delete every row and restart the id counters."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await session.commit()


async def is_empty(session: AsyncSession) -> bool:
    """True when the database has no pickup points yet."""
    return not await pickup_point.list(session, limit=1)


async def seed_reference_data(
    session: AsyncSession,
    s3: Minio,
) -> SeedIds:
    """Insert points, categories, games, copies, employees, clients."""
    ids = SeedIds()

    for item in load_json("pickup_points"):
        row = await create_pickup_point(session, PickupPointCreate(
            name=item["name"], address=item["address"], phone=item["phone"],
        ))
        ids.points[item["name"]] = row.id
        if item.get("is_active") is False:
            await deactivate_pickup_point(session, row.id)

    for item in load_json("categories"):
        row = await create_category(session, CategoryCreate(name=item["name"]))
        ids.categories[item["name"]] = row.id

    for item in load_json("board_games"):
        game = await add_new_game_to_catalog(session, BoardGameCreate(
            title=item["title"],
            description=item.get("description"),
            min_players=item["min_players"],
            max_players=item["max_players"],
            playtime_minutes=item["playtime_minutes"],
            daily_price=Decimal(item["daily_price"]),
            deposit_price=Decimal(item["deposit_price"]),
            category_ids=[ids.categories[c] for c in item["categories"]],
        ))
        ids.games[item["title"]] = game.id
        ids.games_by_id[game.id] = item["title"]

        key = maybe_upload_cover(s3, game.id, item.get("cover_file"))
        if key:
            await set_cover_key(session, game.id, key)

    number = 0
    for item in load_json("game_copies"):
        title = item["game_title"]
        for point_name, count in item["counts"].items():
            for _ in range(count):
                number += 1
                await add_game_copy(session, GameCopyCreate(
                    game_id=ids.games[title],
                    current_point_id=ids.points[point_name],
                    inventory_number=f"INV-{number:04d}",
                ))

    for item in load_json("employees"):
        point_id = ids.points[item["pickup_point"]] if item.get("pickup_point") else None
        emp = await create_employee(session, EmployeeCreate(
            email=item["email"],
            password=item.get("password", SEED_PASSWORD),
            full_name=item["full_name"],
            phone=item["phone"],
            role=item["role"],
            pickup_point_id=point_id,
        ))
        ids.employees[item["email"]] = emp.id
        ids.employees_data[item["email"]] = item
        ids.accounts.append((item["role"], item["email"]))

    for item in load_json("clients"):
        row = await register_client(session, ClientCreate(
            email=item["email"],
            password=item.get("password", SEED_PASSWORD),
            full_name=item["full_name"],
            phone=item["phone"],
        ))
        ids.clients[item["email"]] = row.id
        ids.accounts.append(("CLIENT", item["email"]))
        if item.get("is_active") is False:
            await deactivate_client(session, row.id)

    return ids


def _pick_courier(ids: SeedIds) -> int:
    """Return the first active courier's id."""
    for email, data in ids.employees_data.items():
        if data["role"] == "COURIER" and data.get("is_active") is not False:
            return ids.employees[email]
    raise RuntimeError("No active courier in employees.json")


def _pick_manager(ids: SeedIds, point: str) -> int:
    """Return the id of the manager assigned to `point`."""
    for email, data in ids.employees_data.items():
        if data["role"] == "MANAGER" and data.get("pickup_point") == point:
            return ids.employees[email]
    raise RuntimeError(f"No MANAGER assigned to point {point!r}")


async def _drive_delivery_to_ready(
    session: AsyncSession,
    order_id: int,
    courier_id: int,
) -> None:
    """Accept, start and complete the delivery for `order_id`."""
    task = await delivery_crud.get_by_order(session, order_id)
    if task is None:
        raise RuntimeError(f"Order {order_id} has no delivery")
    await deliveries_service.accept_delivery(session, task.id, courier_id)
    await deliveries_service.start_delivery(session, task.id, courier_id)
    await deliveries_service.complete_delivery(session, task.id, courier_id)


async def _build_damages(
    session: AsyncSession,
    order_id: int,
    ids: SeedIds,
    damages_spec: list[dict],
) -> list[ReturnDamage]:
    """Resolve `for_game` (game title) into a game_copy_id from the order."""
    detail = await order_crud.get_detail(session, order_id)
    copy_id_by_title: dict[str, int] = {}
    for item in detail.items:
        copy = await game_copy_crud.get(session, item.game_copy_id)
        title = ids.games_by_id[copy.game_id]
        copy_id_by_title[title] = copy.id

    result: list[ReturnDamage] = []
    for dmg in damages_spec:
        title = dmg["for_game"]
        if title not in copy_id_by_title:
            raise RuntimeError(
                f"Order {order_id} has no copy of {title!r} to damage"
            )
        result.append(ReturnDamage(
            game_copy_id=copy_id_by_title[title],
            description=dmg["description"],
            deposit_withheld=Decimal(dmg["deposit_withheld"]),
        ))
    return result


async def seed_order(
    session: AsyncSession,
    ids: SeedIds,
    spec: dict,
    courier_id: int,
) -> None:
    """Drive one order through the workflow to reach `spec['scenario']`."""
    scenario = spec["scenario"]
    client_id = ids.clients[spec["client_email"]]
    point_id = ids.points[spec["point"]]
    game_ids = [ids.games[t] for t in spec["game_titles"]]

    start = date.today() + timedelta(days=spec.get("start_offset_days", 0))
    end = start + timedelta(days=spec.get("duration_days", 1) - 1)

    order = await orders_service.create_order(
        session, client_id,
        OrderCreate(
            pickup_point_id=point_id,
            start_date=start,
            end_date=end,
            game_ids=game_ids,
        ),
    )

    if scenario in {"ready", "needs_transfer"}:
        return

    if scenario == "cancelled":
        await orders_service.cancel_order(session, order.id, client_id)
        return

    # Everything else needs READY_FOR_PICKUP before issue/return.
    if order.status == "NEEDS_TRANSFER":
        if scenario == "in_transit":
            task = await delivery_crud.get_by_order(session, order.id)
            await deliveries_service.accept_delivery(session, task.id, courier_id)
            await deliveries_service.start_delivery(session, task.id, courier_id)
            return
        await _drive_delivery_to_ready(session, order.id, courier_id)

    if scenario == "in_transit":
        raise RuntimeError(
            f"Order at {spec['point']!r} for {spec['game_titles']!r} "
            "did not require a delivery, so it cannot be in_transit"
        )
    if scenario == "ready_after_delivery":
        return

    manager_id = _pick_manager(ids, spec["point"])
    await manager_service.issue_order(session, order.id, manager_id)

    if scenario == "active":
        return

    if scenario in {"completed", "completed_with_damage"}:
        damages = await _build_damages(
            session, order.id, ids, spec.get("damages", []),
        )
        await manager_service.accept_return(
            session, order.id, manager_id,
            OrderReturnCreate(damages=damages),
        )
        return

    raise RuntimeError(f"Unknown scenario: {scenario!r}")


async def populate(session: AsyncSession, s3: Minio) -> SeedIds:
    """Insert all seed data, driving orders through their workflows."""
    ids = await seed_reference_data(session, s3)

    courier_id = _pick_courier(ids)
    for i, spec in enumerate(load_json("orders"), start=1):
        try:
            await seed_order(session, ids, spec, courier_id)
        except Exception as exc:
            print(f"  ! order #{i} ({spec['scenario']}): {exc}")
            raise

    return ids


def print_summary(ids: SeedIds) -> None:
    """Print what was created and how to log in."""
    print(f"Pickup points : {len(ids.points)}")
    print(f"Categories    : {len(ids.categories)}")
    print(f"Games         : {len(ids.games)}")
    print(f"Employees     : {len(ids.employees)}")
    print(f"Clients       : {len(ids.clients)}")
    print(f"Accounts (password for all: {SEED_PASSWORD}):")
    for role, email in ids.accounts:
        print(f"  {role:<8} {email}")


async def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Fill the database with test data.")
    parser.add_argument("--reset", action="store_true",
                        help="delete all data first")
    parser.add_argument("--yes", action="store_true",
                        help="do not ask before deleting")
    args = parser.parse_args(argv)

    s3 = build_s3_client()

    try:
        async with SessionFactory() as session:
            if args.reset:
                if not confirm_wipe(args.yes):
                    print("Cancelled.")
                    return 1
                await reset_database(session)
            elif not await is_empty(session):
                print(
                    f"Database {database_label()} already has data. "
                    "Use --reset to wipe it first."
                )
                return 1
            ids = await populate(session, s3)
            print_summary(ids)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    setup_output()
    sys.exit(asyncio.run(main()))