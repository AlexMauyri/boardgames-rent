"""Validation rules of the order-flow Pydantic schemas (no database)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import (
    DamageReportCreate,
    DeliveryCreate,
    GameCopyCreate,
    OrderCreate,
)


def _order(**overrides):
    values = dict(
        pickup_point_id=1,
        start_date=date(2026, 10, 10),
        end_date=date(2026, 10, 12),
        game_ids=[1],
    )
    values.update(overrides)
    return OrderCreate(**values)


def test_order_create_valid():
    assert _order().game_ids == [1]


def test_order_create_single_day_rental_allowed():
    _order(end_date=date(2026, 10, 10))


def test_order_create_end_before_start_rejected():
    with pytest.raises(ValidationError):
        _order(end_date=date(2026, 10, 9))


def test_order_create_needs_at_least_one_game():
    with pytest.raises(ValidationError):
        _order(game_ids=[])


def test_delivery_create_same_points_rejected():
    with pytest.raises(ValidationError):
        DeliveryCreate(order_id=1, from_point_id=2, to_point_id=2)


def test_delivery_create_valid():
    DeliveryCreate(order_id=1, from_point_id=2, to_point_id=3)


def test_damage_report_negative_withheld_rejected():
    with pytest.raises(ValidationError):
        DamageReportCreate(
            game_copy_id=1, description="x", deposit_withheld=Decimal("-1"),
        )


def test_damage_report_empty_description_rejected():
    with pytest.raises(ValidationError):
        DamageReportCreate(game_copy_id=1, description="")


def test_damage_report_defaults_to_no_withholding():
    report = DamageReportCreate(game_copy_id=1, description="Torn box")
    assert report.deposit_withheld == Decimal("0")
    assert report.order_id is None


def test_game_copy_create_empty_inventory_number_rejected():
    with pytest.raises(ValidationError):
        GameCopyCreate(game_id=1, current_point_id=1, inventory_number="")
