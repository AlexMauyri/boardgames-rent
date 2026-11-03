"""Tests for the RabbitMQ publisher against a fake aio_pika (no broker)."""

import json

import aio_pika
import pytest

from app.integrations.rabbitmq.publisher import RabbitPublisher


class _FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[aio_pika.Message, str]] = []

    async def publish(self, message, routing_key):
        self.published.append((message, routing_key))


class _FakeChannel:
    def __init__(self, exchange: _FakeExchange) -> None:
        self.exchange = exchange
        self.declared: list[tuple[str, object, bool]] = []

    async def declare_exchange(self, name, kind, durable):
        self.declared.append((name, kind, durable))
        return self.exchange


class _FakeConnection:
    def __init__(self, channel: _FakeChannel) -> None:
        self._channel = channel
        self.closed = False

    async def channel(self):
        return self._channel

    async def close(self):
        self.closed = True


@pytest.fixture
def broker(monkeypatch):
    """Patch aio_pika.connect_robust; yields the fakes and the connect log."""
    exchange = _FakeExchange()
    channel = _FakeChannel(exchange)
    connection = _FakeConnection(channel)
    state = {"connects": 0, "fail": False}

    async def connect_robust(url, **kwargs):
        state["connects"] += 1
        if state["fail"]:
            raise ConnectionError("broker down")
        return connection

    monkeypatch.setattr(aio_pika, "connect_robust", connect_robust)
    return exchange, channel, connection, state


async def test_publishes_a_json_envelope_with_the_type_as_routing_key(broker):
    exchange, channel, _, _ = broker
    publisher = RabbitPublisher()

    await publisher.publish("order.created", {"order_id": 5})

    (message, routing_key), = exchange.published
    assert routing_key == "order.created"
    body = json.loads(message.body)
    assert body["type"] == "order.created"
    assert body["data"] == {"order_id": 5}
    assert body["id"] and body["occurred_at"]
    assert message.message_id == body["id"]
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert channel.declared == [
        ("boardgame.events", aio_pika.ExchangeType.TOPIC, True),
    ]


async def test_the_connection_is_opened_once(broker):
    _, _, _, state = broker
    publisher = RabbitPublisher()

    await publisher.publish("order.created", {})
    await publisher.publish("order.created", {})

    assert state["connects"] == 1


async def test_start_survives_an_unreachable_broker_and_publish_retries(broker):
    exchange, _, _, state = broker
    publisher = RabbitPublisher()
    state["fail"] = True

    await publisher.start()
    with pytest.raises(ConnectionError):
        await publisher.publish("order.created", {})

    state["fail"] = False
    await publisher.publish("order.created", {"order_id": 1})

    assert len(exchange.published) == 1


async def test_close_closes_the_connection(broker):
    _, _, connection, _ = broker
    publisher = RabbitPublisher()
    await publisher.start()

    await publisher.close()

    assert connection.closed
