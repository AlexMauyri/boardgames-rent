"""Tests for the WebSocket endpoint and the message handler, end to end."""

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.consumer import handle_body
from app.events import EventError
from tests.conftest import make_event, make_token


def _auth(token: str) -> str:
    return json.dumps({"type": "auth", "token": token})


def _publish(client, event: dict) -> int:
    """Feed an event through the same path a RabbitMQ message takes."""
    return client.portal.call(
        handle_body, json.dumps(event).encode(), client.app.state.hub,
    )


def test_health_reports_connections(client):
    assert client.get("/health").json() == {"status": "ok", "connections": 0}


def test_valid_token_gets_ready_and_then_notifications(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(_auth(make_token(3, "CLIENT")))
        assert ws.receive_json() == {"type": "ready", "role": "CLIENT", "user_id": 3}

        delivered = _publish(client, make_event("order.status_changed", {
            "order_id": 5, "client_id": 3, "pickup_point_id": 1,
            "old_status": "IN_TRANSIT", "new_status": "READY_FOR_PICKUP",
        }))

        assert delivered == 1
        note = ws.receive_json()
        assert note["type"] == "order.status_changed"
        assert note["title"] == "Статус заказа изменён"
        assert "готов к выдаче" in note["message"]
        assert note["data"]["order_id"] == 5


def test_a_notification_for_another_client_is_not_received(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(_auth(make_token(3, "CLIENT")))
        ws.receive_json()

        delivered = _publish(client, make_event("order.created", {
            "order_id": 6, "client_id": 99, "pickup_point_id": 1,
            "status": "READY_FOR_PICKUP", "total_price": "1.00",
        }))

        assert delivered == 0
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json() == {"type": "pong"}


def test_a_delivery_event_reaches_a_courier_but_not_a_client(client):
    with client.websocket_connect("/ws") as courier, \
            client.websocket_connect("/ws") as customer:
        courier.send_text(_auth(make_token(4, "COURIER")))
        courier.receive_json()
        customer.send_text(_auth(make_token(3, "CLIENT")))
        customer.receive_json()

        delivered = _publish(client, make_event("delivery.created", {
            "delivery_id": 9, "order_id": 5, "from_point_id": 2, "to_point_id": 1,
        }))

        assert delivered == 1
        assert courier.receive_json()["title"] == "Новая доставка"


@pytest.mark.parametrize(
    "first_message",
    [
        pytest.param(_auth("garbage"), id="bad-token"),
        pytest.param(_auth(make_token(token_type="refresh")), id="refresh-token"),
        pytest.param(json.dumps({"type": "hello"}), id="not-auth"),
        pytest.param("not json", id="not-json"),
    ],
)
def test_bad_first_message_closes_with_4401(client, first_message):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(first_message)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()

    assert exc.value.code == 4401


def test_silence_closes_with_4401(client, monkeypatch):
    monkeypatch.setattr(settings, "ws_auth_timeout_seconds", 0.1)

    with client.websocket_connect("/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()

    assert exc.value.code == 4401


def test_connection_is_forgotten_after_disconnect(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(_auth(make_token(3, "CLIENT")))
        ws.receive_json()
        assert client.get("/health").json()["connections"] == 1

    assert client.get("/health").json()["connections"] == 0


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b'{"type": "order.created"}'])
async def test_malformed_messages_raise_event_error(body):
    from app.hub import ConnectionHub

    with pytest.raises(EventError):
        await handle_body(body, ConnectionHub())


async def test_unknown_event_is_ignored():
    from app.hub import ConnectionHub

    body = json.dumps(make_event("something.else", {})).encode()

    assert await handle_body(body, ConnectionHub()) == 0
