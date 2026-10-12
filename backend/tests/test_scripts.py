"""Smoke tests for the seed and demo scripts."""

from app.services import (
    authenticate_client,
    authenticate_employee,
    list_game_copies,
    list_games,
    list_pickup_points_admin,
    list_pickup_points_public,
    search_available_games,
)
from scripts import demo
from scripts.seed import EMAIL_DOMAIN, SEED_PASSWORD, populate


async def test_seed_creates_the_standard_data(session):
    ids = await populate(session)

    assert len(await list_games(session)) == 6
    assert len(await list_game_copies(session)) == 10
    assert len(await list_pickup_points_admin(session)) == 4
    public = {p.name for p in await list_pickup_points_public(session)}
    assert public == {"Центр", "Север", "Юг"}
    assert len(ids.accounts) == 9


async def test_seeded_accounts_can_log_in(session):
    await populate(session)

    assert await authenticate_client(
        session, f"client1@{EMAIL_DOMAIN}", SEED_PASSWORD,
    )
    assert await authenticate_employee(
        session, f"manager.center@{EMAIL_DOMAIN}", SEED_PASSWORD,
    )
    assert await authenticate_employee(
        session, f"courier1@{EMAIL_DOMAIN}", SEED_PASSWORD,
    )


async def test_seed_supports_the_report_search_scenario(session):
    ids = await populate(session)

    items = await search_available_games(
        session, ids.points["Центр"], players=4, playtime_max=90,
    )

    ready = [i.game.title for i in items if i.free_at_point]
    delivered = [i.game.title for i in items if not i.free_at_point]
    assert ready == ["Каркассон", "Катан", "Codenames"]
    assert delivered == ["Пандемия", "Диксит"]


async def test_demo_runs_to_the_end(session, capsys):
    exit_code = await demo.main(["--yes"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "СЦЕНАРИЙ 4" in output
    assert "ИТОГ. Состояние базы данных" in output
