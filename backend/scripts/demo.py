"""Walk through the four use cases of the report against a live database.

    uv run python -m scripts.demo            # asks before wiping the database
    uv run python -m scripts.demo --yes      # no question

The script wipes the database, loads the standard seed data, and then plays
the scenarios of LR0 in order: administrator adds a game, client finds and
books it, courier delivers it, manager hands it out and takes it back. Every
step goes through the service layer, and the state of the order and of the
physical box is printed after each one.
"""

import argparse
import asyncio
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import GameCopy
from app.db.session import SessionFactory, engine
from app.schemas import (
    BoardGameCreate,
    ClientCreate,
    GameCopyCreate,
    OrderCreate,
    OrderReturnCreate,
    ReturnDamage,
)
from app.services import (
    ForbiddenError,
    InvalidTransitionError,
    NotAvailableError,
    NotFoundError,
    accept_delivery,
    accept_return,
    add_game_copy,
    add_new_game_to_catalog,
    authenticate_client,
    cancel_order,
    complete_delivery,
    create_order,
    find_point_order,
    get_game_copy,
    get_order,
    issue_order,
    list_client_orders,
    list_courier_deliveries,
    list_game_copies,
    list_games,
    list_open_deliveries,
    list_pickup_points_admin,
    list_point_inventory,
    register_client,
    resolve_damage_report,
    search_available_games,
    start_delivery,
)
from scripts.console import confirm_wipe, setup_output
from scripts.seed import SEED_PASSWORD, SeedIds, populate, reset_database

ORDER_STATUS = {
    "CREATED": "Создан",
    "NEEDS_TRANSFER": "Ожидает доставки в пункт выдачи",
    "IN_TRANSIT": "В пути в пункт выдачи",
    "READY_FOR_PICKUP": "Готов к выдаче",
    "ACTIVE": "Игра выдана",
    "COMPLETED": "Завершён",
    "CANCELLED": "Отменён",
}
DELIVERY_STATUS = {
    "CREATED": "Новая задача",
    "ACCEPTED": "Принята курьером",
    "IN_TRANSIT": "Курьер в пути",
    "DELIVERED": "Доставлена",
}
COPY_STATUS = {
    "AVAILABLE": "на полке",
    "WITH_CLIENT": "у клиента",
    "IN_TRANSIT": "в дороге",
    "DAMAGED": "повреждена",
}


class Demo:
    """Holds the session and the lookups the printing helpers need."""

    def __init__(self, session: AsyncSession, ids: SeedIds) -> None:
        self.session = session
        self.ids = ids
        self.point_names: dict[int, str] = {}
        self.game_titles: dict[int, str] = {}

    async def refresh_names(self) -> None:
        """Reload the id -> name lookups (new games appear during the demo)."""
        points = await list_pickup_points_admin(self.session)
        self.point_names = {p.id: p.name for p in points}
        games = await list_games(self.session, limit=1000)
        self.game_titles = {g.id: g.title for g in games}

    async def copy_line(self, copy_id: int) -> str:
        """Describe a box: title, inventory number, status and place."""
        copy = await get_game_copy(self.session, copy_id)
        where = (
            f", пункт «{self.point_names[copy.current_point_id]}»"
            if copy.current_point_id else ""
        )
        return (
            f"{self.game_titles[copy.game_id]} [{copy.inventory_number}]: "
            f"{COPY_STATUS[copy.status]}{where}"
        )

    async def show_order(self, order_id: int) -> None:
        """Print an order's status and the state of its boxes."""
        order = await get_order(self.session, order_id)
        info(f"Заказ №{order.id}: «{ORDER_STATUS[order.status]}»")
        for item in order.items:
            info(f"  коробка — {await self.copy_line(item.game_copy_id)}")


def title(text: str) -> None:
    print(f"\n{'=' * 74}\n{text}\n{'=' * 74}")


def step(text: str) -> None:
    print(f"\n-- {text}")


def info(text: str) -> None:
    print(f"   {text}")


def refused(error: Exception) -> None:
    """Print an expected refusal."""
    info(f"Отказ ({type(error).__name__}): {error}")


async def scenario_admin_adds_game(d: Demo) -> int:
    """LR0 2.2.4: the administrator adds a new game."""
    title("СЦЕНАРИЙ 1. Администратор добавляет новую игру")
    s, ids = d.session, d.ids

    step("Администратор заполняет карточку игры и сохраняет")
    game = await add_new_game_to_catalog(s, BoardGameCreate(
        title="Дюна", description="Борьба за пустынную планету",
        min_players=2, max_players=4, playtime_minutes=90,
        daily_price=Decimal("200"), deposit_price=Decimal("1500"),
        category_ids=[ids.categories["Стратегии"]],
    ))
    info(f"Игра «{game.title}» добавлена в каталог (id={game.id})")

    step("Администратор заводит физическую коробку в пункте «Север»")
    copy = await add_game_copy(s, GameCopyCreate(
        game_id=game.id,
        current_point_id=ids.points["Север"],
        inventory_number="INV-0100",
    ))
    await d.refresh_names()
    info(f"Коробка {copy.inventory_number}: {await d.copy_line(copy.id)}")

    step("Игра сразу видна в каталоге (категория «Стратегии»)")
    rows = await list_games(s, category_id=ids.categories["Стратегии"])
    info("Каталог: " + ", ".join(r.title for r in rows))
    return game.id


async def scenario_client_books(d: Demo, game_id: int) -> tuple[int, int]:
    """LR0 2.2.1: the client picks a game and books it."""
    title("СЦЕНАРИЙ 2. Клиент подбирает и бронирует настольную игру")
    s, ids = d.session, d.ids

    step("Клиент регистрируется и входит в аккаунт")
    client = await register_client(s, ClientCreate(
        email="alexey@bgrent.io", password=SEED_PASSWORD,
        full_name="Алексей Смирнов", phone="+7 900 333-00-00",
    ))
    info(f"Зарегистрирован клиент id={client.id}, {client.email}")
    ok = await authenticate_client(s, client.email, SEED_PASSWORD)
    bad = await authenticate_client(s, client.email, "wrong-password")
    info(f"Вход с верным паролем: {'успешно' if ok else 'отказ'}")
    info(f"Вход с неверным паролем: {'успешно' if bad else 'отказ'}")

    step("«Подбор игры»: 4 игрока, до 1.5 часов, пункт «Центр»")
    results = await search_available_games(
        s, ids.points["Центр"], players=4, playtime_max=90,
    )
    for item in results:
        where = (
            "есть в пункте" if item.free_at_point
            else "будет доставлена из другого пункта"
        )
        info(
            f"{item.game.title:<10} {item.game.playtime_minutes:>3} мин, "
            f"{item.game.min_players}-{item.game.max_players} игр., "
            f"{item.game.daily_price} руб/сут — {where}"
        )

    step("Клиент выбирает «Дюна», нажимает «Забронировать» на 3 дня")
    start = date.today() + timedelta(days=1)
    order = await create_order(s, client.id, OrderCreate(
        pickup_point_id=ids.points["Центр"],
        start_date=start, end_date=start + timedelta(days=2),
        game_ids=[game_id],
    ))
    info(f"Номер заказа: {order.id}")
    info(f"Стоимость аренды: {order.total_price} руб, залог: {order.deposit_paid} руб")
    await d.show_order(order.id)

    step("Другой клиент пытается забронировать ту же единственную коробку")
    try:
        await create_order(s, ids.clients[0], OrderCreate(
            pickup_point_id=ids.points["Центр"],
            start_date=start, end_date=start,
            game_ids=[game_id],
        ))
    except NotAvailableError as exc:
        refused(exc)
    return client.id, order.id


async def scenario_courier(d: Demo, order_id: int) -> None:
    """LR0 2.2.2: the courier moves the box between points."""
    title("СЦЕНАРИЙ 3. Курьер перевозит игру между пунктами выдачи")
    s, ids = d.session, d.ids
    courier = ids.couriers[0]

    step("Курьер открывает приложение и видит новые задачи")
    open_tasks = await list_open_deliveries(s)
    for task in open_tasks:
        info(
            f"Доставка №{task.id}: заказ №{task.order_id}, из пункта "
            f"«{d.point_names[task.from_point_id]}» в «{d.point_names[task.to_point_id]}»"
        )
    task = open_tasks[0]

    step("Курьер нажимает «Принять заказ»")
    done = await accept_delivery(s, task.id, courier)
    info(f"Статус доставки: {DELIVERY_STATUS[done.status]}")

    step("Другой курьер пытается взять уже принятую задачу")
    try:
        await accept_delivery(s, task.id, ids.couriers[1])
    except InvalidTransitionError as exc:
        refused(exc)

    step("Курьер забирает коробку у менеджера и нажимает «Забрал, в пути»")
    done = await start_delivery(s, task.id, courier)
    info(f"Статус доставки: {DELIVERY_STATUS[done.status]}")
    await d.show_order(order_id)

    step("Курьер приезжает в «Центр» и нажимает «Доставлено»")
    done = await complete_delivery(s, task.id, courier)
    info(f"Статус доставки: {DELIVERY_STATUS[done.status]}")
    await d.show_order(order_id)
    active = await list_courier_deliveries(s, courier)
    info(f"Заказ пропал из активного списка курьера: {not active}")


async def scenario_manager(d: Demo, order_id: int) -> None:
    """LR0 2.2.3: the manager hands the game out and takes it back."""
    title("СЦЕНАРИЙ 4. Менеджер выдаёт игру клиенту и принимает её обратно")
    s, ids = d.session, d.ids
    manager = ids.managers["Центр"]

    step("Клиент называет номер заказа, менеджер вбивает его в поиск")
    found = await find_point_order(s, manager, order_id)
    info(f"Статус: «{ORDER_STATUS[found.status]}»")

    step("Менеджер другого пункта этот заказ не видит")
    try:
        await find_point_order(s, ids.managers["Север"], order_id)
    except NotFoundError as exc:
        refused(exc)

    step("Менеджер отдаёт коробку и нажимает «Выдать»")
    await issue_order(s, order_id, manager)
    await d.show_order(order_id)
    shelf = await list_point_inventory(s, manager)
    info("На полках «Центра» теперь: " + ", ".join(
        d.game_titles[c.game_id] for c in shelf
    ))

    step("Клиент возвращает игру. Менеджер находит нехватку компонентов")
    copy_id = (await get_order(s, order_id)).items[0].game_copy_id
    result = await accept_return(s, order_id, manager, OrderReturnCreate(damages=[
        ReturnDamage(
            game_copy_id=copy_id, description="Нет двух фишек",
            deposit_withheld=Decimal("300"),
        ),
    ]))
    info(f"Аренда завершена: «{ORDER_STATUS[result.order.status]}»")
    report = result.damage_reports[0]
    info(f"Акт №{report.id}: «{report.description}», удержано {report.deposit_withheld} руб")
    info(f"Возврат залога клиенту: {result.deposit_refund} руб")
    info(f"Коробка — {await d.copy_line(copy_id)}")

    step("Повреждённую коробку чинят, менеджер закрывает акт")
    resolved = await resolve_damage_report(s, report.id, manager)
    info(f"Акт закрыт: {resolved.resolved_at is not None}")
    info(f"Коробка — {await d.copy_line(copy_id)}")


async def scenario_cancel(d: Demo) -> None:
    """A client cancels a booking."""
    title("ДОПОЛНИТЕЛЬНО. Клиент отменяет бронь")
    s, ids = d.session, d.ids
    client = ids.clients[1]
    start = date.today() + timedelta(days=2)

    step("Клиент бронирует «Каркассон» в «Центре» (коробка уже там)")
    order = await create_order(s, client, OrderCreate(
        pickup_point_id=ids.points["Центр"], start_date=start, end_date=start,
        game_ids=[ids.games["Каркассон"]],
    ))
    await d.show_order(order.id)

    step("Клиент передумал и отменяет бронь")
    cancelled = await cancel_order(s, order.id, client)
    info(f"Статус: «{ORDER_STATUS[cancelled.status]}»")

    step("Чужой клиент не может отменить заказ")
    try:
        await cancel_order(s, order.id, ids.clients[2])
    except (NotFoundError, InvalidTransitionError, ForbiddenError) as exc:
        refused(exc)


async def scenario_integrity(d: Demo) -> None:
    """The database itself refuses inconsistent rows."""
    title("ДОПОЛНИТЕЛЬНО. Целостность данных на уровне БД")
    s = d.session
    step("Прямая вставка коробки «на полке», но без пункта (в обход сервисов)")
    game_id = next(iter(d.game_titles))
    try:
        await s.execute(insert(GameCopy).values(
            game_id=game_id, current_point_id=None,
            inventory_number="INV-BAD", status="AVAILABLE",
        ))
    except IntegrityError as exc:
        info("PostgreSQL отклонил строку:")
        info(str(exc.orig).splitlines()[0])
    await s.rollback()


async def print_totals(d: Demo, client_id: int) -> None:
    """Show what is left in the database."""
    title("ИТОГ. Состояние базы данных")
    s = d.session
    for table in Base.metadata.sorted_tables:
        count = (await s.execute(
            select(func.count()).select_from(table)
        )).scalar_one()
        info(f"{table.name:<18} {count:>3} строк")
    orders = await list_client_orders(s, client_id)
    info("Заказы клиента Алексея: " + ", ".join(
        f"№{o.id} «{ORDER_STATUS[o.status]}»" for o in orders
    ))
    history = await list_courier_deliveries(s, d.ids.couriers[0], active_only=False)
    info("История курьера: " + ", ".join(
        f"доставка №{t.id} «{DELIVERY_STATUS[t.status]}»" for t in history
    ))
    free = await list_game_copies(s, status="AVAILABLE")
    info(f"Свободных коробок на полках: {len(free)}")


async def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Play the LR0 scenarios.")
    parser.add_argument("--yes", action="store_true",
                        help="do not ask before wiping the database")
    args = parser.parse_args(argv)

    if not confirm_wipe(args.yes):
        print("Cancelled.")
        return 1
    try:
        async with SessionFactory() as session:
            await reset_database(session)
            ids = await populate(session)
            demo = Demo(session, ids)
            await demo.refresh_names()
            print("База очищена и заполнена тестовыми данными.")

            game_id = await scenario_admin_adds_game(demo)
            client_id, order_id = await scenario_client_books(demo, game_id)
            await scenario_courier(demo, order_id)
            await scenario_manager(demo, order_id)
            await scenario_cancel(demo)
            await scenario_integrity(demo)
            await print_totals(demo, client_id)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    setup_output()
    sys.exit(asyncio.run(main()))
