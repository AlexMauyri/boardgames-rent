"""Fill the database with test data.

    uv run python -m scripts.seed            # only into an empty database
    uv run python -m scripts.seed --reset    # wipe everything, then fill

All rows go through the service layer, so passwords are hashed and every
business rule applies exactly as it does for real requests.

The tests wipe the same database; seed again after running them, or point the
tests at a separate database with the POSTGRES_DB environment variable.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import pickup_point
from app.db import models  # noqa: F401  (registers every table on the metadata)
from app.db.base import Base
from app.db.session import SessionFactory, engine
from app.schemas import (
    BoardGameCreate,
    CategoryCreate,
    ClientCreate,
    EmployeeCreate,
    GameCopyCreate,
    PickupPointCreate,
)
from app.services import (
    add_game_copy,
    add_new_game_to_catalog,
    create_category,
    create_employee,
    create_pickup_point,
    deactivate_pickup_point,
    register_client,
)
from scripts.console import confirm_wipe, database_label, setup_output

# Every seeded account uses this password. Local test data only.
SEED_PASSWORD = "demo-password"
EMAIL_DOMAIN = "bgrent.io"

_POINTS = (
    ("Центр", "ул. Ленина, 10", "+7 900 000-00-01"),
    ("Север", "пр. Мира, 45", "+7 900 000-00-02"),
    ("Юг", "ул. Садовая, 7", "+7 900 000-00-03"),
)
_CLOSED_POINT = ("Запад", "ул. Кирова, 3", "+7 900 000-00-04")

_CATEGORIES = ("Стратегии", "Кооператив", "Вечериночные", "Семейные")

# title, min players, max players, minutes, daily price, deposit, categories
_GAMES = (
    ("Каркассон", 2, 5, 45, "80", "500", ("Семейные", "Стратегии")),
    ("Катан", 3, 4, 90, "120", "800", ("Стратегии", "Семейные")),
    ("Пандемия", 2, 4, 60, "120", "800", ("Кооператив",)),
    ("Codenames", 4, 8, 20, "70", "400", ("Вечериночные",)),
    ("Диксит", 3, 8, 30, "90", "500", ("Вечериночные", "Семейные")),
    ("Мафия", 6, 12, 40, "60", "300", ("Вечериночные",)),
)

# game title -> pickup points holding one box each (a point twice = two boxes)
_STOCK = {
    "Каркассон": ("Центр", "Север"),
    "Катан": ("Центр", "Юг"),
    "Пандемия": ("Север", "Юг"),
    "Codenames": ("Центр", "Центр"),
    "Диксит": ("Юг",),
    "Мафия": ("Север",),
}

_COURIERS = ("Курьер Олег", "Курьер Дарья")
_CLIENTS = ("Иван Петров", "Мария Сидорова", "Пётр Иванов")


@dataclass
class SeedIds:
    """Primary keys of the seeded rows, for the demo to use."""

    points: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    games: dict[str, int] = field(default_factory=dict)
    couriers: list[int] = field(default_factory=list)
    managers: dict[str, int] = field(default_factory=dict)
    admin: int = 0
    clients: list[int] = field(default_factory=list)
    accounts: list[tuple[str, str]] = field(default_factory=list)


async def reset_database(session: AsyncSession) -> None:
    """Delete every row and restart the id counters.

    The table list comes from the model metadata, so it cannot drift from the
    schema.
    """
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await session.commit()


async def is_empty(session: AsyncSession) -> bool:
    """True when the database has no pickup points yet."""
    return not await pickup_point.list(session, limit=1)


async def populate(session: AsyncSession) -> SeedIds:
    """Insert the standard test data through the service layer.

    Args:
        session: Active async session over an empty database.

    Returns:
        The ids of everything created.
    """
    ids = SeedIds()

    for name, address, phone in _POINTS:
        row = await create_pickup_point(
            session, PickupPointCreate(name=name, address=address, phone=phone),
        )
        ids.points[name] = row.id
    closed = await create_pickup_point(
        session,
        PickupPointCreate(
            name=_CLOSED_POINT[0], address=_CLOSED_POINT[1],
            phone=_CLOSED_POINT[2],
        ),
    )
    await deactivate_pickup_point(session, closed.id)
    ids.points[_CLOSED_POINT[0]] = closed.id

    for name in _CATEGORIES:
        ids.categories[name] = (
            await create_category(session, CategoryCreate(name=name))
        ).id

    for title, low, high, minutes, daily, deposit, cats in _GAMES:
        game = await add_new_game_to_catalog(session, BoardGameCreate(
            title=title, min_players=low, max_players=high,
            playtime_minutes=minutes, daily_price=Decimal(daily),
            deposit_price=Decimal(deposit),
            category_ids=[ids.categories[c] for c in cats],
        ))
        ids.games[title] = game.id

    number = 0
    for title, points in _STOCK.items():
        for point_name in points:
            number += 1
            await add_game_copy(session, GameCopyCreate(
                game_id=ids.games[title],
                current_point_id=ids.points[point_name],
                inventory_number=f"INV-{number:04d}",
            ))

    async def staff(role, name, email_name, point=None) -> int:
        email = f"{email_name}@{EMAIL_DOMAIN}"
        row = await create_employee(session, EmployeeCreate(
            email=email, password=SEED_PASSWORD, full_name=name,
            phone="+7 900 111-00-00", role=role,
            pickup_point_id=ids.points[point] if point else None,
        ))
        ids.accounts.append((role, email))
        return row.id

    ids.admin = await staff("ADMIN", "Админ Анна", "admin")
    for n, name in enumerate(_COURIERS, start=1):
        ids.couriers.append(await staff("COURIER", name, f"courier{n}"))
    for point_name, slug in (("Центр", "center"), ("Север", "north"), ("Юг", "south")):
        ids.managers[point_name] = await staff(
            "MANAGER", f"Менеджер ({point_name})", f"manager.{slug}",
            point=point_name,
        )

    for n, name in enumerate(_CLIENTS, start=1):
        email = f"client{n}@{EMAIL_DOMAIN}"
        row = await register_client(session, ClientCreate(
            email=email, password=SEED_PASSWORD, full_name=name,
            phone="+7 900 222-00-00",
        ))
        ids.clients.append(row.id)
        ids.accounts.append(("CLIENT", email))

    return ids


def print_summary(ids: SeedIds) -> None:
    """Print what was created and how to log in."""
    print(f"Pickup points : {', '.join(ids.points)} (the last one is closed)")
    print(f"Categories    : {len(ids.categories)}")
    print(f"Games         : {len(ids.games)}")
    print(f"Boxes         : {sum(len(p) for p in _STOCK.values())}")
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
            ids = await populate(session)
            print_summary(ids)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    setup_output()
    sys.exit(asyncio.run(main()))
