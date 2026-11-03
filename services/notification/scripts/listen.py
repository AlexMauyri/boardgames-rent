"""Console client: connect to the notification service and print messages.

A separate process that plays the role of the notified user. Get an access
token by logging in through the API, then:

    python scripts/listen.py --token <access JWT>
    python scripts/listen.py --url ws://localhost/ws --token <access JWT>
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url", default="ws://localhost/ws",
        help="WebSocket URL (through nginx by default)",
    )
    parser.add_argument(
        "--token", default=os.environ.get("NOTIFY_TOKEN"),
        help="access JWT; defaults to $NOTIFY_TOKEN",
    )
    args = parser.parse_args()
    if not args.token:
        parser.error("an access token is required (--token or $NOTIFY_TOKEN)")
    return args


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


async def listen(url: str, token: str) -> int:
    """Print notifications until the server closes the connection."""
    async with connect(url) as websocket:
        await websocket.send(json.dumps({"type": "auth", "token": token}))
        try:
            async for raw in websocket:
                message = json.loads(raw)
                if message.get("type") == "ready":
                    print(
                        f"[{_stamp()}] connected as {message['role']} "
                        f"#{message['user_id']}, waiting for notifications...",
                        flush=True,
                    )
                elif "message" in message:
                    print(
                        f"[{_stamp()}] {message['title']}: {message['message']}",
                        flush=True,
                    )
        except ConnectionClosed as closed:
            code = closed.rcvd.code if closed.rcvd else None
            print(f"[{_stamp()}] connection closed (code={code})", flush=True)
            return 1 if code == 4401 else 0
    return 0


def main() -> int:
    args = _parse_args()
    try:
        return asyncio.run(listen(args.url, args.token))
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"cannot connect to {args.url}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
