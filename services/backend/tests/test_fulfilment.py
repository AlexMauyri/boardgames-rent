"""Tests for box selection (pure function, no database)."""

from dataclasses import dataclass

import pytest

from app.services.exceptions import NotAvailableError
from app.services.fulfilment import plan_fulfilment

HERE = 1  # the pickup point of the order
NORTH = 2
SOUTH = 3


@dataclass
class Box:
    id: int
    game_id: int
    current_point_id: int | None


def ids(plan) -> list[int]:
    return [c.id for c in plan.copies]


def test_box_at_pickup_point_needs_no_transfer():
    plan = plan_fulfilment([Box(10, 1, HERE)], {1: 1}, HERE)
    assert ids(plan) == [10]
    assert plan.source_point_id is None


def test_box_elsewhere_travels_from_its_point():
    plan = plan_fulfilment([Box(10, 1, NORTH)], {1: 1}, HERE)
    assert ids(plan) == [10]
    assert plan.source_point_id == NORTH


def test_local_box_is_preferred_over_a_lower_id_remote_one():
    boxes = [Box(10, 1, NORTH), Box(11, 1, HERE)]
    plan = plan_fulfilment(boxes, {1: 1}, HERE)
    assert ids(plan) == [11]
    assert plan.source_point_id is None


def test_mixed_order_takes_local_box_and_travelling_box():
    boxes = [Box(10, 1, HERE), Box(20, 2, NORTH)]
    plan = plan_fulfilment(boxes, {1: 1, 2: 1}, HERE)
    assert sorted(ids(plan)) == [10, 20]
    assert plan.source_point_id == NORTH


def test_two_units_of_one_game_use_local_then_remote():
    boxes = [Box(10, 1, HERE), Box(11, 1, NORTH)]
    plan = plan_fulfilment(boxes, {1: 2}, HERE)
    assert sorted(ids(plan)) == [10, 11]
    assert plan.source_point_id == NORTH


def test_lowest_source_point_id_wins():
    boxes = [Box(10, 1, SOUTH), Box(11, 1, NORTH)]
    plan = plan_fulfilment(boxes, {1: 1}, HERE)
    assert ids(plan) == [11]
    assert plan.source_point_id == NORTH


def test_all_travelling_boxes_come_from_one_point():
    boxes = [
        Box(10, 1, NORTH), Box(11, 1, SOUTH),
        Box(20, 2, SOUTH),
    ]
    plan = plan_fulfilment(boxes, {1: 1, 2: 1}, HERE)
    assert sorted(ids(plan)) == [11, 20]
    assert plan.source_point_id == SOUTH


def test_not_enough_boxes_names_the_uncovered_games():
    boxes = [Box(10, 1, HERE)]
    with pytest.raises(NotAvailableError) as exc:
        plan_fulfilment(boxes, {1: 2, 2: 1}, HERE)
    assert exc.value.game_ids == [1, 2]


def test_boxes_spread_over_several_points_are_rejected():
    boxes = [Box(10, 1, NORTH), Box(20, 2, SOUTH)]
    with pytest.raises(NotAvailableError) as exc:
        plan_fulfilment(boxes, {1: 1, 2: 1}, HERE)
    assert exc.value.game_ids == [1, 2]
    assert "several pickup points" in exc.value.reason


def test_no_stock_at_all():
    with pytest.raises(NotAvailableError):
        plan_fulfilment([], {1: 1}, HERE)
