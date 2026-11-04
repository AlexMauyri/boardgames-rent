"""Console client: connect to the notification service and print messages.

A separate process that plays the role of the notified user. It can
either take a ready access token, or log in automatically via the API
(handling the DPoP nonce challenge) and then connect.

Examples:
    python scripts/listen.py --email client1@bgrent.io --password demo-password
    python scripts/listen.py --token <access JWT>
    python scripts/listen.py --url ws://localhost/ws --email admin@bgrent.io --password demo-password --role employee
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url", default="ws://localhost/ws",
        help="WebSocket URL (through nginx by default)",
    )
    parser.add_argument(
        "--api-url", default="http://localhost/api/v1",
        help="Base URL of the API for login",
    )
    parser.add_argument(
        "--role", choices=("client", "employee"), default="client",
        help="Which login endpoint to use when auto-logging in",
    )
    parser.add_argument("--email", help="Email for auto-login")
    parser.add_argument("--password", help="Password for auto-login")
    parser.add_argument(
        "--token", default=os.environ.get("NOTIFY_TOKEN"),
        help="access JWT; defaults to $NOTIFY_TOKEN",
    )
    args = parser.parse_args()
    
    if not args.token and not (args.email and args.password):
        parser.error("Either --token or both --email and --password are required")
        
    return args


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_keypair() -> tuple[ec.EllipticCurvePrivateKey, dict]:
    """Generate an ES256 keypair and return (private_key, public_jwk)."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pub = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(pub.x.to_bytes(32, "big")),
        "y": _b64url(pub.y.to_bytes(32, "big")),
    }
    return private_key, jwk


def _make_proof(
    private_key: ec.EllipticCurvePrivateKey,
    jwk: dict,
    url: str,
    nonce: str | None = None,
) -> str:
    """Build and sign a DPoP proof JWT."""
    header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": jwk}
    payload = {
        "jti": str(uuid.uuid4()),
        "htm": "POST",
        "htu": url,
        "iat": int(time.time()),
    }
    if nonce:
        payload["nonce"] = nonce
    return jwt.encode(payload, private_key, algorithm="ES256", headers=header)


def get_access_token(api_url: str, role: str, email: str, password: str) -> str:
    """Log in via the API and return the access token, handling DPoP."""
    login_url = f"{api_url}/auth/login/{role}"
    private_key, jwk = _generate_keypair()
    body = json.dumps({"email": email, "password": password}).encode("utf-8")

    print(f"[{_stamp()}] Logging in as {email} ({role})...", file=sys.stderr)

    def do_request(proof: str) -> tuple[int, dict, str | None]:
        req = urllib.request.Request(
            login_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "DPoP": proof,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as response:
                resp_body = response.read().decode("utf-8")
                nonce = response.headers.get("dpop-nonce")
                return response.status, json.loads(resp_body), nonce
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8")
            nonce = e.headers.get("dpop-nonce")
            try:
                parsed_body = json.loads(resp_body)
            except json.JSONDecodeError:
                parsed_body = {"error": resp_body}
            return e.code, parsed_body, nonce

    proof = _make_proof(private_key, jwk, login_url)
    status, data, nonce = do_request(proof)

    if status == 401 and nonce:
        proof = _make_proof(private_key, jwk, login_url, nonce)
        status, data, _ = do_request(proof)

    if status != 200:
        print(f"[{_stamp()}] Login failed: {status} {data}", file=sys.stderr)
        sys.exit(1)

    return data["access_token"]


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
    
    token = args.token
    if not token:
        token = get_access_token(args.api_url, args.role, args.email, args.password)
        
    try:
        return asyncio.run(listen(args.url, token))
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"cannot connect to {args.url}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())