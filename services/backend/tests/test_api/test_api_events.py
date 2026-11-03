"""Tests that the HTTP endpoints publish domain events.

The publisher is replaced by a recorder on ``app.state``; the database is the
real test database.
"""

from datetime import date, timedelta

import pytest

from app.auth.jwt import create_access_token
from app.main import app as fastapi_app
from tests.helpers import (
    make_client,
    make_copy,
    make_courier,
    make_game,
    make_manager,
    make_point,
)


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, event_type, data):
        self.events.append((event_type, data))

    def types(self) -> list[str]:
        return [t for t, _ in self.events]


@pytest.fixture
def recorder(monkeypatch):
    stub = _Recorder()
    monkeypatch.setattr(fastapi_app.state, "event_publisher", stub, raising=False)
    return stub


def _headers(user_id: int, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _payload(point_id: int, game_id: int) -> dict:
    start = date.today() + timedelta(days=1)
    return {
        "pickup_point_id": point_id,
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=2)).isoformat(),
        "game_ids": [game_id],
    }


async def test_placing_and_cancelling_an_order_publishes_events(http, session, recorder):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    client = await make_client(session)

    created = await http.post(
        "/api/v1/orders", json=_payload(here, game), headers=_headers(client, "CLIENT"),
    )
    assert created.status_code == 201
    assert recorder.types() == ["order.created", "delivery.created"]

    cancelled = await http.post(
        f"/api/v1/orders/{created.json()['id']}/cancel",
        headers=_headers(client, "CLIENT"),
    )
    assert cancelled.status_code == 200
    assert recorder.types()[2:] == ["order.status_changed", "delivery.cancelled"]


async def test_courier_and_manager_endpoints_publish_events(http, session, recorder):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    client = await make_client(session)
    courier = await make_courier(session)
    manager = await make_manager(session, here)

    created = await http.post(
        "/api/v1/orders", json=_payload(here, game), headers=_headers(client, "CLIENT"),
    )
    order_id = created.json()["id"]
    delivery_id = next(
        d["delivery_id"] for t, d in recorder.events if t == "delivery.created"
    )
    recorder.events.clear()

    courier_auth = _headers(courier, "COURIER")
    for step in ("accept", "start", "complete"):
        r = await http.post(
            f"/api/v1/courier/deliveries/{delivery_id}/{step}", headers=courier_auth,
        )
        assert r.status_code == 200
    issued = await http.post(
        f"/api/v1/manager/orders/{order_id}/issue",
        headers=_headers(manager, "MANAGER"),
    )
    assert issued.status_code == 200

    assert recorder.types() == [
        "delivery.status_changed",                          # accept
        "delivery.status_changed", "order.status_changed",  # start
        "delivery.status_changed", "order.status_changed",  # complete
        "order.status_changed",                             # issue
    ]


async def test_requests_work_without_a_publisher(http, session, monkeypatch):
    monkeypatch.delattr(fastapi_app.state, "event_publisher", raising=False)
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    r = await http.post(
        "/api/v1/orders", json=_payload(point, game), headers=_headers(client, "CLIENT"),
    )

    assert r.status_code == 201
