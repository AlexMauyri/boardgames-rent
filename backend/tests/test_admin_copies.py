"""Tests for admin management of physical boxes."""

import pytest

from app.schemas import GameCopyCreate, GameCopyUpdate
from app.services import (
    ConflictError,
    NotFoundError,
    add_game_copy,
    deactivate_pickup_point,
    get_game_copy,
    list_game_copies,
    update_game_copy,
)
from tests.helpers import make_copy, make_game, make_point


def _new(game_id: int, point_id: int, number: str = "INV-1") -> GameCopyCreate:
    return GameCopyCreate(
        game_id=game_id, current_point_id=point_id, inventory_number=number,
    )


async def test_add_copy_starts_available_at_the_point(session):
    point = await make_point(session)
    game = await make_game(session)

    copy = await add_game_copy(session, _new(game, point))

    assert copy.status == "AVAILABLE"
    assert copy.current_point_id == point
    assert copy.game_id == game
    assert copy.inventory_number == "INV-1"


async def test_add_copy_unknown_game_not_found(session):
    point = await make_point(session)

    with pytest.raises(NotFoundError):
        await add_game_copy(session, _new(999999, point))


async def test_add_copy_unknown_point_not_found(session):
    game = await make_game(session)

    with pytest.raises(NotFoundError):
        await add_game_copy(session, _new(game, 999999))


async def test_add_copy_to_inactive_point_rejected(session):
    point = await make_point(session)
    game = await make_game(session)
    await deactivate_pickup_point(session, point)

    with pytest.raises(ValueError):
        await add_game_copy(session, _new(game, point))


async def test_add_copy_duplicate_inventory_number_conflicts(session):
    point = await make_point(session)
    game = await make_game(session)
    await add_game_copy(session, _new(game, point, "INV-1"))

    with pytest.raises(ConflictError):
        await add_game_copy(session, _new(game, point, "INV-1"))


async def test_update_inventory_number(session):
    point = await make_point(session)
    game = await make_game(session)
    copy = await add_game_copy(session, _new(game, point, "INV-1"))

    updated = await update_game_copy(
        session, copy.id, GameCopyUpdate(inventory_number="INV-9"),
    )

    assert updated.inventory_number == "INV-9"


async def test_update_to_taken_inventory_number_conflicts(session):
    point = await make_point(session)
    game = await make_game(session)
    await add_game_copy(session, _new(game, point, "INV-1"))
    second = await add_game_copy(session, _new(game, point, "INV-2"))

    with pytest.raises(ConflictError):
        await update_game_copy(
            session, second.id, GameCopyUpdate(inventory_number="INV-1"),
        )


async def test_update_to_own_inventory_number_is_a_no_op(session):
    point = await make_point(session)
    game = await make_game(session)
    copy = await add_game_copy(session, _new(game, point, "INV-1"))

    updated = await update_game_copy(
        session, copy.id, GameCopyUpdate(inventory_number="INV-1"),
    )

    assert updated.inventory_number == "INV-1"


async def test_update_unknown_copy_not_found(session):
    with pytest.raises(NotFoundError):
        await update_game_copy(
            session, 999999, GameCopyUpdate(inventory_number="X"),
        )


async def test_get_copy(session):
    point = await make_point(session)
    game = await make_game(session)
    copy = await add_game_copy(session, _new(game, point))

    assert (await get_game_copy(session, copy.id)).id == copy.id
    with pytest.raises(NotFoundError):
        await get_game_copy(session, 999999)


async def test_list_copies_with_filters(session):
    center = await make_point(session, "Center")
    north = await make_point(session, "North")
    dune = await make_game(session, "Dune")
    chess = await make_game(session, "Chess")
    a = await make_copy(session, dune, center, "INV-1")
    b = await make_copy(session, dune, north, "INV-2")
    c = await make_copy(session, chess, center, "INV-3")
    d = await make_copy(session, chess, None, "INV-4", status="WITH_CLIENT")

    def ids(rows):
        return [r.id for r in rows]

    assert ids(await list_game_copies(session)) == [a, b, c, d]
    assert ids(await list_game_copies(session, game_id=dune)) == [a, b]
    assert ids(await list_game_copies(session, point_id=center)) == [a, c]
    assert ids(await list_game_copies(session, status="WITH_CLIENT")) == [d]
    assert ids(await list_game_copies(
        session, game_id=chess, point_id=center,
    )) == [c]
    assert ids(await list_game_copies(session, skip=1, limit=2)) == [b, c]
