"""Drive the API to produce one of each event type.

Uses urllib (wrapped in asyncio.to_thread) and real API transitions.
Run alongside your listener; if the listener prints all five routing keys,
the producer side is wired correctly.

Event sources:
    order.created         client places an order that needs a transfer
    delivery.created      backend creates it automatically inside the order
    delivery.status_changed  courier accept/start/complete
    order.status_changed  automatic after DELIVERED (→ READY_FOR_PICKUP),
                          and again after manager issue (→ ACTIVE)
    delivery.cancelled    client cancels a NEEDS_TRANSFER order
"""

import asyncio
import base64
import json
import sys
import time
import uuid
import urllib.error
import urllib.request

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

API = "http://localhost:8000"

CLIENT_EMAIL = "client.ivan@bgrent.io"
CLIENT_PASSWORD = "demo-password"

MANAGER_EMAIL = "manager.center@bgrent.io"
MANAGER_PASSWORD = "demo-password"

COURIER_EMAIL = "courier.oleg@bgrent.io"
COURIER_PASSWORD = "demo-password"

START_DATE = "2026-11-10"
END_DATE = "2026-11-12"


# --- DPoP login ---------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_keypair() -> tuple[ec.EllipticCurvePrivateKey, dict]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    pub = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC", "crv": "P-256",
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


def _do_login(role: str, email: str, password: str) -> str:
    login_url = f"{API}/api/v1/auth/login/{role}"
    private_key, jwk = _generate_keypair()
    body = json.dumps({"email": email, "password": password}).encode("utf-8")

    def attempt(proof: str) -> tuple[int, dict, str | None]:
        req = urllib.request.Request(
            login_url,
            data=body,
            headers={"Content-Type": "application/json", "DPoP": proof},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return (
                    resp.status,
                    json.loads(resp.read().decode("utf-8")),
                    resp.headers.get("dpop-nonce"),
                )
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"error": raw}
            return e.code, data, e.headers.get("dpop-nonce")

    proof = _make_proof(private_key, jwk, login_url)
    status, data, nonce = attempt(proof)
    if status == 401 and nonce:
        proof = _make_proof(private_key, jwk, login_url, nonce)
        status, data, _ = attempt(proof)

    if status != 200:
        print(f"Login failed for {email}: {status} {data}", file=sys.stderr)
        sys.exit(1)
    return data["access_token"]


async def login(role: str, email: str, password: str) -> str:
    return await asyncio.to_thread(_do_login, role, email, password)


# --- HTTP helpers -------------------------------------------------------

def _do_request(
    method: str,
    path: str,
    token: str | None = None,
    payload: dict | None = None,
) -> dict | list:
    url = f"{API}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {}
    if payload:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"HTTP {e.code} on {method} {path}: {body}", file=sys.stderr)
        raise


async def request(
    method: str,
    path: str,
    token: str | None = None,
    payload: dict | None = None,
) -> dict | list:
    return await asyncio.to_thread(_do_request, method, path, token, payload)


# --- Discovery helpers --------------------------------------------------

async def first_active_point(token: str) -> int:
    points = await request("GET", "/api/v1/catalog/pickup-points", token)
    if not points:
        print("No active pickup points. Seed the database first.", file=sys.stderr)
        sys.exit(1)
    return points[0]["id"]


async def find_transfer_game(token: str, point_id: int) -> int | None:
    """Return a catalog game that has 0 copies at point_id but >0 elsewhere."""
    items = await request(
        "GET",
        f"/api/v1/catalog/search?pickup_point_id={point_id}&limit=50",
        token,
    )
    for item in items:
        if item["free_at_point"] == 0 and item["free_elsewhere"] > 0:
            return item["game"]["id"]
    return None


async def find_open_delivery(token: str, order_id: int) -> int:
    deliveries = await request("GET", "/api/v1/courier/deliveries/open", token)
    for d in deliveries:
        if d["order_id"] == order_id:
            return d["id"]
    raise RuntimeError(f"No open delivery for order {order_id}")


# --- Transitions --------------------------------------------------------

async def create_order(token: str, point_id: int, game_id: int) -> int:
    data = await request("POST", "/api/v1/orders", token, {
        "pickup_point_id": point_id,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "game_ids": [game_id],
    })
    return data["id"]


async def delivery_transition(token: str, delivery_id: int, step: str) -> None:
    endpoint = {
        "ACCEPTED": "accept",
        "IN_TRANSIT": "start",
        "DELIVERED": "complete",
    }[step]
    await request(
        "POST",
        f"/api/v1/courier/deliveries/{delivery_id}/{endpoint}",
        token,
    )


async def order_issue(token: str, order_id: int) -> None:
    await request("POST", f"/api/v1/manager/orders/{order_id}/issue", token)


async def order_cancel(token: str, order_id: int) -> None:
    await request("POST", f"/api/v1/orders/{order_id}/cancel", token)


# --- Orchestration ------------------------------------------------------

async def main() -> None:
    client_token = await login("client", CLIENT_EMAIL, CLIENT_PASSWORD)
    manager_token = await login("employee", MANAGER_EMAIL, MANAGER_PASSWORD)
    courier_token = await login("employee", COURIER_EMAIL, COURIER_PASSWORD)

    target_point = await first_active_point(client_token)
    print(f"Using pickup point id={target_point}")

    print("triggers:")

    # 1. order.created + 2. delivery.created
    game_id = await find_transfer_game(client_token, target_point)
    if game_id is None:
        print("No game requiring transfer. All games are already at the point.",
              file=sys.stderr)
        return
    order_id = await create_order(client_token, target_point, game_id)
    print(f"  order.created           order_id={order_id}")

    delivery_id = await find_open_delivery(courier_token, order_id)
    print(f"  delivery.created        delivery_id={delivery_id}")

    # 3. delivery.status_changed: ACCEPTED → IN_TRANSIT → DELIVERED
    # After DELIVERED the order goes to READY_FOR_PICKUP,
    # which fires 4. order.status_changed.
    for step in ("ACCEPTED", "IN_TRANSIT", "DELIVERED"):
        await delivery_transition(courier_token, delivery_id, step)
        print(f"  delivery.status_changed delivery_id={delivery_id} -> {step}")

    # 4. order.status_changed again: READY → ACTIVE via manager issue
    await order_issue(manager_token, order_id)
    print(f"  order.status_changed    order_id={order_id} -> ACTIVE")

    # 5. delivery.cancelled: client books a fresh transfer and cancels it
    #    before the courier picks it up. The backend removes the open
    #    delivery; the notification service emits delivery.cancelled.
    game_id2 = await find_transfer_game(client_token, target_point)
    if game_id2 is None:
        print("  (skipped delivery.cancelled: no game left to transfer)",
              file=sys.stderr)
        return
    order_id2 = await create_order(client_token, target_point, game_id2)
    await order_cancel(client_token, order_id2)
    print(f"  order.cancelled + delivery.cancelled order_id={order_id2}")


if __name__ == "__main__":
    asyncio.run(main())