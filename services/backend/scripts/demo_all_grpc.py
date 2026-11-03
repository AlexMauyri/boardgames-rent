from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, timedelta

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

API = os.environ.get("API_BASE", "http://localhost/api/v1")
COMPOSE = ["docker", "compose"]

GRPC_SERVICE = os.environ.get("GRPC_SERVICE_ADDR", "grpc")


# --- Pretty printing -----------------------------------------------------

def hr() -> None:
    print("=" * 78)


def title(text: str) -> None:
    print()
    hr()
    print(text)
    hr()


# --- HTTP helper (urllib instead of httpx) -------------------------------

def _request(
    method: str,
    url: str,
    headers: dict | None = None,
    data: dict | bytes | None = None,
) -> tuple[int, dict, str]:
    """Send an HTTP request, return (status, headers, body_text).

    Header names in the returned dict keep whatever case the server sent;
    Starlette lowercases all header names before writing them to the wire,
    so use `_get_header` for any lookup.
    """
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if data is not None:
        if isinstance(data, dict):
            data = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        req.data = data
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, dict(e.headers), body


def _get_header(headers: dict, name: str) -> str | None:
    """Case-insensitive header lookup from a plain dict."""
    name_lower = name.lower()
    for key, value in headers.items():
        if key.lower() == name_lower:
            return value
    return None


def _json(body: str):
    return json.loads(body) if body else None


# --- gRPC log capture ----------------------------------------------------

def _logs(service: str) -> list[str]:
    """Fetch current logs for a docker compose service."""
    try:
        out = subprocess.check_output(
            [*COMPOSE, "logs", "--no-color", service],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return [ln for ln in out.splitlines() if ln.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def _print_new_logs(service: str, baseline: int) -> None:
    current = _logs(service)
    new_lines = current[baseline:]
    if not new_lines:
        print(f"   <no new logs from '{service}' — is it running?>")
        return
    for line in new_lines:
        print(f"   [{service}] {line}")


# --- DPoP Helpers --------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    pub = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC", "crv": "P-256",
        "x": _b64url(pub.x.to_bytes(32, "big")),
        "y": _b64url(pub.y.to_bytes(32, "big")),
    }
    return private_key, jwk


def _sign_dpop(private_key, jwk, method: str, url: str, nonce: str | None = None) -> str:
    header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": jwk}
    payload = {
        "jti": uuid.uuid4().hex,
        "htm": method,
        "htu": url,
        "iat": int(time.time()),
    }
    if nonce:
        payload["nonce"] = nonce
    return jwt.encode(payload, private_key, algorithm="ES256", headers=header)


def _dpop_login(email: str, password: str) -> str:
    url = f"{API}/auth/login/client"
    private_key, jwk = _make_keypair()
    body = {"email": email, "password": password}

    proof = _sign_dpop(private_key, jwk, "POST", url)
    status, headers, text = _request("POST", url, {"DPoP": proof}, body)

    nonce = _get_header(headers, "DPoP-Nonce")
    if status == 401 and nonce:
        proof = _sign_dpop(private_key, jwk, "POST", url, nonce=nonce)
        status, headers, text = _request("POST", url, {"DPoP": proof}, body)

    if status != 200:
        raise RuntimeError(f"HTTP {status} — {text}")

    return _json(text)["access_token"]


# --- Demo Steps ----------------------------------------------------------

def step_match(point_id: int) -> None:
    title("STEP 1 — GET /catalog/match (FastAPI → MatchingService)")
    query = urllib.parse.urlencode({
        "pickup_point_id": point_id,
        "players": 4,
        "playtime_max": 90,
        "limit": 3,
    })
    url = f"{API}/catalog/match?{query}"

    baseline = len(_logs(GRPC_SERVICE))
    print(f"-> GET {url}")

    t0 = time.perf_counter()
    status, _, text = _request("GET", url)
    ms = (time.perf_counter() - t0) * 1000

    print(f"<- HTTP {status} in {ms:.0f} ms")
    if status == 200:
        for item in _json(text):
            g = item["game"]
            print(f"   * {g['title']!r} score={item['score']} reason={item['reason']}")
    else:
        print(f"   Error body: {text}")

    print("\nMatchingService logs:")
    _print_new_logs(GRPC_SERVICE, baseline)


def step_similar(game_id: int) -> None:
    title("STEP 2 — GET /catalog/games/{id}/similar (FastAPI → RecommendationService)")
    url = f"{API}/catalog/games/{game_id}/similar?limit=3"

    baseline = len(_logs(GRPC_SERVICE))
    print(f"-> GET {url}")

    t0 = time.perf_counter()
    status, _, text = _request("GET", url)
    ms = (time.perf_counter() - t0) * 1000

    print(f"<- HTTP {status} in {ms:.0f} ms")
    if status == 200:
        for item in _json(text):
            print(f"   * {item['game']['title']!r} reason={item['reason']}")
    else:
        print(f"   Error body: {text}")

    print("\nRecommendationService logs:")
    _print_new_logs(GRPC_SERVICE, baseline)


def step_quote(token: str, point_id: int, game_id: int) -> None:
    title("STEP 3 — POST /orders/quote (FastAPI → PricingService)")
    url = f"{API}/orders/quote"
    body = {
        "pickup_point_id": point_id,
        "start_date": str(date.today() + timedelta(days=1)),
        "end_date": str(date.today() + timedelta(days=7)),
        "game_ids": [game_id],
    }

    baseline = len(_logs(GRPC_SERVICE))
    print(f"-> POST {url}  body={body}")

    t0 = time.perf_counter()
    status, _, text = _request(
        "POST", url, {"Authorization": f"Bearer {token}"}, body,
    )
    ms = (time.perf_counter() - t0) * 1000

    print(f"<- HTTP {status} in {ms:.0f} ms")
    if status == 200:
        print(f"   {_json(text)}")
    else:
        print(f"   Error body: {text}")

    print("\nPricingService logs:")
    _print_new_logs(GRPC_SERVICE, baseline)


def step_create_order(token: str, point_id: int, game_id: int) -> None:
    title("STEP 4 — POST /orders (FastAPI → PricingService + RabbitMQ)")
    url = f"{API}/orders"
    body = {
        "pickup_point_id": point_id,
        "start_date": str(date.today() + timedelta(days=1)),
        "end_date": str(date.today() + timedelta(days=7)),
        "game_ids": [game_id],
    }

    baseline = len(_logs(GRPC_SERVICE))
    print(f"-> POST {url}  body={body}")

    t0 = time.perf_counter()
    status, _, text = _request(
        "POST", url, {"Authorization": f"Bearer {token}"}, body,
    )
    ms = (time.perf_counter() - t0) * 1000

    print(f"<- HTTP {status} in {ms:.0f} ms")
    if status == 201:
        data = _json(text)
        print(f"   Order created: id={data['id']}, total={data['total_price']}")
    else:
        print(f"   Error body: {text}")

    print("\nPricingService logs:")
    _print_new_logs(GRPC_SERVICE, baseline)


def step_personal(token: str) -> None:
    title("STEP 5 — GET /recommendations/personal (FastAPI → RecommendationService)")
    url = f"{API}/recommendations/personal?limit=3"

    baseline = len(_logs(GRPC_SERVICE))
    print(f"-> GET {url}")

    t0 = time.perf_counter()
    status, _, text = _request(
        "GET", url, {"Authorization": f"Bearer {token}"},
    )
    ms = (time.perf_counter() - t0) * 1000

    print(f"<- HTTP {status} in {ms:.0f} ms")
    if status == 200:
        for item in _json(text):
            print(f"   * {item['game']['title']!r} reason={item['reason']}")
    else:
        print(f"   Error body: {text}")

    print("\nRecommendationService logs:")
    _print_new_logs(GRPC_SERVICE, baseline)


# --- Main entrypoint -----------------------------------------------------

def main() -> int:
    hr()
    print("gRPC Delegation Demo — Lab 3")
    hr()

    # 1. Получаем ID пункта выдачи и ID игры для тестов
    try:
        _, _, points_text = _request("GET", f"{API}/catalog/pickup-points")
        _, _, games_text = _request("GET", f"{API}/catalog/games")
        points = _json(points_text)
        games = _json(games_text)
        if not points or not games:
            print("!! Catalog is empty. Run seed first.")
            return 1
        point_id = points[0]["id"]
        game_id = games[0]["id"]
    except Exception as e:
        print(f"!! Cannot reach API: {e}")
        return 1

    # 2. Логинимся как клиент
    print("Logging in as client...")
    try:
        token = _dpop_login("client.ivan@bgrent.io", "demo-password")
    except Exception as e:
        print(f"!! Login failed: {e}")
        return 1

    # 3. Прогоняем все шаги
    step_match(point_id)
    time.sleep(0.3)

    step_similar(game_id)
    time.sleep(0.3)

    step_quote(token, point_id, game_id)
    time.sleep(0.3)

    step_create_order(token, point_id, game_id)
    time.sleep(0.3)

    step_personal(token)

    hr()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())