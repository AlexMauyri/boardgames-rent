"""Registry of live WebSocket connections and delivery to them."""

import logging

from fastapi import WebSocket

from app.auth import Principal
from app.events import Notification

logger = logging.getLogger(__name__)


class ConnectionHub:
    """Tracks connections per ``(role, user_id)``; a user may have several."""

    def __init__(self) -> None:
        self._connections: dict[tuple[str, int], set[WebSocket]] = {}

    def add(self, principal: Principal, websocket: WebSocket) -> None:
        """Register an authenticated connection."""
        key = (principal.role, principal.id)
        self._connections.setdefault(key, set()).add(websocket)

    def remove(self, principal: Principal, websocket: WebSocket) -> None:
        """Forget a connection; safe to call twice."""
        key = (principal.role, principal.id)
        sockets = self._connections.get(key)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del self._connections[key]

    def count(self) -> int:
        """Number of live connections."""
        return sum(len(s) for s in self._connections.values())

    async def deliver(self, notification: Notification) -> int:
        """Send a notification to every matching connection.

        A connection that fails to accept the message is dropped.

        Returns:
            How many connections the message was sent to.
        """
        recipient = notification.recipient
        targets = [
            ws
            for (role, user_id), sockets in self._connections.items()
            if role == recipient.role
            and (recipient.user_id is None or recipient.user_id == user_id)
            for ws in sockets
        ]
        sent = 0
        for websocket in targets:
            try:
                await websocket.send_json(notification.payload)
                sent += 1
            except Exception:
                logger.warning("dropping dead connection", exc_info=True)
                for key, sockets in list(self._connections.items()):
                    sockets.discard(websocket)
                    if not sockets:
                        del self._connections[key]
        return sent
