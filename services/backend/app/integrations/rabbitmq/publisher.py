"""RabbitMQ publisher for domain events."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection

from app.config import settings

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 3.0


class RabbitPublisher:
    """Publishes events to a durable topic exchange.

    The connection is opened lazily and re-opened on demand, so the API
    starts and serves requests even while the broker is down; events raised
    in that window are logged and dropped by ``services.events.emit``.
    """

    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Try to connect now; log and carry on if the broker is down."""
        try:
            await self._ensure_exchange()
        except Exception:
            logger.warning(
                "RabbitMQ unreachable at startup, will retry on publish",
                exc_info=True,
            )

    async def close(self) -> None:
        """Close the connection. Called on shutdown."""
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._exchange = None

    async def _ensure_exchange(self) -> AbstractExchange:
        async with self._lock:
            if self._exchange is None:
                connection = await aio_pika.connect_robust(
                    settings.rabbitmq_url, timeout=_CONNECT_TIMEOUT,
                )
                channel = await connection.channel()
                self._exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                self._connection = connection
                logger.info(
                    "RabbitMQ publisher ready exchange=%s",
                    settings.rabbitmq_exchange,
                )
            return self._exchange

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish one event with ``event_type`` as the routing key."""
        envelope = {
            "id": uuid4().hex,
            "type": event_type,
            "occurred_at": datetime.now(UTC).isoformat(),
            "data": data,
        }
        exchange = await self._ensure_exchange()
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(envelope, default=str).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=envelope["id"],
                type=event_type,
            ),
            routing_key=event_type,
        )
        logger.info("event published type=%s id=%s", event_type, envelope["id"])
