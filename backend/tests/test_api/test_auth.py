"""Tests for /api/v1/auth/*."""

import pytest

from app.crud import client as client_crud
from app.schemas import EmployeeCreate, PickupPointCreate
from app.services import (
    create_employee,
    create_pickup_point,
    deactivate_client,
)

REGISTER = "/api/v1/auth/register/client"
LOGIN_CLIENT = "/api/v1/auth/login/client"
LOGIN_EMPLOYEE = "/api/v1/auth/login/employee"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


async def _register(http, email="alice@test.io", password="secret1"):
    return await http.post(REGISTER, json={
        "email": email,
        "password": password,
        "full_name": "Alice",
        "phone": "+79990000001",
    })


async def _login_client(http, email="alice@test.io", password="secret1"):
    return await http.post(LOGIN_CLIENT, json={
        "email": email, "password": password,
    })


async def _login_employee(http, email, password="secret1"):
    return await http.post(LOGIN_EMPLOYEE, json={
        "email": email, "password": password,
    })


# --- register ----------------------------------------------------------


async def test_register_client_returns_201(http):
    r = await _register(http)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@test.io"
    assert body["is_active"] is True
    assert "password_hash" not in body


async def test_register_duplicate_email_conflicts(http):
    await _register(http)
    r = await _register(http)
    assert r.status_code == 409


async def test_register_invalid_email_returns_422(http):
    r = await http.post(REGISTER, json={
        "email": "not-an-email",
        "password": "secret1",
        "full_name": "A",
        "phone": "+7",
    })
    assert r.status_code == 422


# --- login client ------------------------------------------------------


async def test_login_client_success(http):
    await _register(http)
    r = await _login_client(http)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_client_wrong_password_401(http):
    await _register(http)
    r = await _login_client(http, password="wrong")
    assert r.status_code == 401


async def test_login_unknown_email_401(http):
    r = await _login_client(http, email="nobody@test.io")
    assert r.status_code == 401


async def test_login_inactive_client_401(http, session):
    await _register(http)
    row = await client_crud.get_by_email(session, "alice@test.io")
    await deactivate_client(session, row.id)

    r = await _login_client(http)
    assert r.status_code == 401


# --- login employee ----------------------------------------------------


@pytest.mark.parametrize("role", ["COURIER", "ADMIN"])
async def test_login_employee_roles_without_point(http, session, role):
    email = f"{role.lower()}@test.io"
    await create_employee(session, EmployeeCreate(
        email=email, password="secret1",
        full_name="Staff", phone="+7", role=role,
    ))
    r = await _login_employee(http, email)
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_login_employee_manager(http, session):
    point = await create_pickup_point(session, PickupPointCreate(
        name="Center", address="a", phone="+7",
    ))
    await create_employee(session, EmployeeCreate(
        email="manager@test.io", password="secret1",
        full_name="Manager", phone="+7",
        role="MANAGER", pickup_point_id=point.id,
    ))
    r = await _login_employee(http, "manager@test.io")
    assert r.status_code == 200


# --- refresh -----------------------------------------------------------


async def test_refresh_rotates_and_invalidates_old(http):
    await _register(http)
    old = (await _login_client(http)).json()["refresh_token"]

    r = await http.post(REFRESH, json={"refresh_token": old})
    assert r.status_code == 200
    new = r.json()["refresh_token"]
    assert new != old

    # Old refresh is now revoked.
    r2 = await http.post(REFRESH, json={"refresh_token": old})
    assert r2.status_code == 401


async def test_refresh_garbage_401(http):
    r = await http.post(REFRESH, json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 401


async def test_refresh_empty_422(http):
    r = await http.post(REFRESH, json={"refresh_token": ""})
    assert r.status_code == 422


# --- logout ------------------------------------------------------------


async def test_logout_revokes_refresh(http):
    await _register(http)
    refresh = (await _login_client(http)).json()["refresh_token"]

    r = await http.post(LOGOUT, json={"refresh_token": refresh})
    assert r.status_code == 204

    r2 = await http.post(REFRESH, json={"refresh_token": refresh})
    assert r2.status_code == 401


async def test_logout_with_garbage_token_is_still_204(http):
    r = await http.post(LOGOUT, json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 204