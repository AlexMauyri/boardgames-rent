"""Notification service entrypoint: RabbitMQ consumer plus WebSocket server."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.auth import AuthError, authenticate
from app.config import settings
from app.consumer import run_consumer
from app.hub import ConnectionHub

logger = logging.getLogger(__name__)

WS_UNAUTHORIZED = 4401


def create_app(consume: bool = True) -> FastAPI:
    """Build the app.

    Args:
        consume: Start the RabbitMQ consumer with the app; tests turn it off
            and feed the hub directly.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub = ConnectionHub()
        app.state.hub = hub
        task = asyncio.create_task(run_consumer(hub)) if consume else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Notification Service", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, int | str]:
        """Liveness probe for docker healthcheck."""
        return {"status": "ok", "connections": app.state.hub.count()}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        """Receive notifications in real time.

        Protocol: after connecting, the client sends
        ``{"type": "auth", "token": "<access JWT>"}`` within
        ``WS_AUTH_TIMEOUT_SECONDS``. The server answers
        ``{"type": "ready", "role": ..., "user_id": ...}`` and then pushes
        notifications. A bad or missing token closes the socket with 4401.
        The client may send ``{"type": "ping"}`` and gets ``{"type": "pong"}``.
        """
        await websocket.accept()
        hub: ConnectionHub = websocket.app.state.hub

        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(), settings.ws_auth_timeout_seconds,
            )
            message = json.loads(raw)
            if message.get("type") != "auth":
                raise AuthError("first message must be auth")
            principal = authenticate(message.get("token", ""))
        except (TimeoutError, ValueError, AttributeError, AuthError) as exc:
            logger.warning("websocket auth failed: %r", exc)
            await websocket.close(code=WS_UNAUTHORIZED)
            return
        except WebSocketDisconnect:
            return

        hub.add(principal, websocket)
        logger.info(
            "websocket connected role=%s user_id=%s connections=%s",
            principal.role, principal.id, hub.count(),
        )
        try:
            await websocket.send_json({
                "type": "ready", "role": principal.role, "user_id": principal.id,
            })
            while True:
                text = await websocket.receive_text()
                with suppress(ValueError, AttributeError):
                    if json.loads(text).get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            hub.remove(principal, websocket)
            logger.info(
                "websocket disconnected role=%s user_id=%s connections=%s",
                principal.role, principal.id, hub.count(),
            )

    return app


app = create_app()
