"""Tests for app.api.deps: auth extraction, role gating, inactive subjects."""

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    Principal,
    get_current_client,
    get_current_employee,
    get_current_principal,
    require_role,
)
from app.api.errors import register_exception_handlers
from app.auth.jwt import create_access_token
from app.schemas import ClientCreate, EmployeeCreate
from app.services import (
    create_employee,
    deactivate_client,
    register_client,
)


def _mini_app() -> FastAPI:
    """A tiny app exposing deps directly, for testing them in isolation."""
    mini = FastAPI()

    @mini.get("/me")
    async def me(
        principal: Principal = Depends(get_current_principal),
    ) -> dict:
        return {"id": principal.id, "role": principal.role}

    @mini.get("/admin-only")
    async def admin_only(
        _: object = Depends(require_role("ADMIN")),
    ) -> dict:
        return {"ok": True}

    @mini.get("/client-only")
    async def client_only(
        _: object = Depends(get_current_client),
    ) -> dict:
        return {"ok": True}

    @mini.get("/employee-only")
    async def employee_only(
        _: object = Depends(get_current_employee),
    ) -> dict:
        return {"ok": True}

    register_exception_handlers(mini)
    return mini


async def _get(app: FastAPI, path: str, token: str | None = None):
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        return await ac.get(path, headers=headers)


async def test_missing_header_401():
    r = await _get(_mini_app(), "/me")
    assert r.status_code == 401


async def test_garbage_token_401():
    r = await _get(_mini_app(), "/me", token="not-a-jwt")
    assert r.status_code == 401


async def test_refresh_token_as_access_401(session):
    # A refresh token must not authenticate a request.
    from app.auth.jwt import create_refresh_token
    refresh, _ = create_refresh_token(1, "CLIENT")
    r = await _get(_mini_app(), "/me", token=refresh)
    assert r.status_code == 401


async def test_valid_principal(session):
    c = await register_client(session, ClientCreate(
        email="me@test.io", password="secret1",
        full_name="Me", phone="+7",
    ))
    token = create_access_token(c.id, "CLIENT")
    r = await _get(_mini_app(), "/me", token=token)
    assert r.status_code == 200
    assert r.json() == {"id": c.id, "role": "CLIENT"}


async def test_require_role_mismatch_403(session):
    emp = await create_employee(session, EmployeeCreate(
        email="c@test.io", password="secret1",
        full_name="C", phone="+7", role="COURIER",
    ))
    token = create_access_token(emp.id, "COURIER")
    r = await _get(_mini_app(), "/admin-only", token=token)
    assert r.status_code == 403


async def test_require_role_match_200(session):
    emp = await create_employee(session, EmployeeCreate(
        email="a@test.io", password="secret1",
        full_name="A", phone="+7", role="ADMIN",
    ))
    token = create_access_token(emp.id, "ADMIN")
    r = await _get(_mini_app(), "/admin-only", token=token)
    assert r.status_code == 200


async def test_get_current_client_inactive_401(session):
    c = await register_client(session, ClientCreate(
        email="inactive@test.io", password="secret1",
        full_name="I", phone="+7",
    ))
    await deactivate_client(session, c.id)
    token = create_access_token(c.id, "CLIENT")
    r = await _get(_mini_app(), "/client-only", token=token)
    assert r.status_code == 401


async def test_get_current_client_with_employee_token_401(session):
    emp = await create_employee(session, EmployeeCreate(
        email="emp@test.io", password="secret1",
        full_name="E", phone="+7", role="ADMIN",
    ))
    token = create_access_token(emp.id, "ADMIN")
    r = await _get(_mini_app(), "/client-only", token=token)
    assert r.status_code == 401


async def test_get_current_employee_with_client_token_401(session):
    c = await register_client(session, ClientCreate(
        email="cl@test.io", password="secret1",
        full_name="C", phone="+7",
    ))
    token = create_access_token(c.id, "CLIENT")
    r = await _get(_mini_app(), "/employee-only", token=token)
    assert r.status_code == 401