"""RabbitMQ consumer: events in, notifications out to the hub."""

import asyncio
import json
import logging

import aio_pika

from app.config import settings
from app.events import EventError, build_notifications
from app.hub import ConnectionHub

logger = logging.getLogger(__name__)

_AE_EXCHANGE = "events.ae"
_UNROUTABLE_QUEUE = "events.unroutable"
_BINDING_KEYS = ("v1.order.*", "v1.delivery.*")


async def handle_body(body: bytes, hub: ConnectionHub) -> int:
    """Turn one broker message into notifications and deliver them.

    Args:
        body: Raw message body, a JSON event envelope.
        hub: Where connected users are.

    Returns:
        How many connections received a notification.

    Raises:
        EventError: The body is not valid JSON or the event is malformed.
    """
    try:
        event = json.loads(body)
    except ValueError as exc:
        raise EventError(f"not JSON: {exc}") from exc
    if not isinstance(event, dict):
        raise EventError("event is not an object")

    notifications = build_notifications(event)
    delivered = 0
    for notification in notifications:
        delivered += await hub.deliver(notification)
    logger.info(
        "event handled type=%s id=%s notifications=%s delivered=%s",
        event.get("type"), event.get("id"), len(notifications), delivered,
    )
    return delivered


async def run_consumer(hub: ConnectionHub) -> None:
    """Consume events forever, reconnecting while the broker is away.

    A malformed message is logged and discarded (not requeued, or it would
    loop forever). Runs until cancelled.
    """
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        except Exception:
            logger.warning(
                "RabbitMQ unreachable, retrying in %ss",
                settings.rabbitmq_retry_seconds,
            )
            await asyncio.sleep(settings.rabbitmq_retry_seconds)
            continue

        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=10)

            ae = await channel.declare_exchange(
                _AE_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True,
            )
            unroutable_q = await channel.declare_queue(
                _UNROUTABLE_QUEUE, durable=True,
            )
            await unroutable_q.bind(ae)

            exchange = await channel.declare_exchange(
                settings.rabbitmq_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
                arguments={"alternate-exchange": _AE_EXCHANGE},
            )
            queue = await channel.declare_queue(
                settings.rabbitmq_queue, durable=True,
            )
            for binding_key in _BINDING_KEYS:
                await queue.bind(exchange, routing_key=binding_key)
            logger.info(
                "consuming queue=%s exchange=%s bindings=%s",
                settings.rabbitmq_queue,
                settings.rabbitmq_exchange,
                ",".join(_BINDING_KEYS),
            )

            async with queue.iterator() as messages:
                async for message in messages:
                    async with message.process(requeue=False):
                        try:
                            await handle_body(message.body, hub)
                        except EventError:
                            logger.warning(
                                "discarding malformed event", exc_info=True,
                            )