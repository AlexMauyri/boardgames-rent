"""Tests for auth"""

import pytest
from pydantic import ValidationError

from app.schemas import ClientCreate, EmployeeCreate, LoginRequest, RefreshRequest, TokenPair
from app.services import (
    authenticate_client,
    authenticate_employee,
    create_employee,
    register_client,
)
from app.services.exceptions import ConflictError


async def test_register_client_creates_active_account(session):
    c = await register_client(session, ClientCreate(
        email="alice@test.io", password="secret1",
        full_name="Alice", phone="+79990000001",
    ))
    assert c.email == "alice@test.io"
    assert c.is_active is True
    assert not hasattr(c, "password_hash")


async def test_register_client_duplicate_email(session):
    await register_client(session, ClientCreate(
        email="dup@test.io", password="secret1",
        full_name="A", phone="+79990000001",
    ))
    with pytest.raises(ConflictError):
        await register_client(session, ClientCreate(
            email="dup@test.io", password="secret2",
            full_name="B", phone="+79990000002",
        ))


async def test_register_client_short_password_rejected_by_schema(session):
    with pytest.raises(Exception):
        ClientCreate(
            email="short@test.io", password="x",
            full_name="S", phone="+7",
        )


async def test_authenticate_client_correct_password(session):
    await register_client(session, ClientCreate(
        email="auth@test.io", password="secret1",
        full_name="A", phone="+79990000001",
    ))
    res = await authenticate_client(session, "auth@test.io", "secret1")
    assert res is not None
    assert res.email == "auth@test.io"


async def test_authenticate_client_wrong_password(session):
    await register_client(session, ClientCreate(
        email="auth@test.io", password="secret1",
        full_name="A", phone="+79990000001",
    ))
    res = await authenticate_client(session, "auth@test.io", "wrong")
    assert res is None


async def test_authenticate_client_unknown_email(session):
    res = await authenticate_client(session, "nobody@test.io", "x")
    assert res is None


async def test_authenticate_employee_correct_password(session):
    await create_employee(session, EmployeeCreate(
        email="emp@test.io", password="secret1",
        full_name="E", phone="+7", role="ADMIN",
    ))
    res = await authenticate_employee(session, "emp@test.io", "secret1")
    assert res is not None
    assert res.email == "emp@test.io"


async def test_authenticate_employee_wrong_password(session):
    await create_employee(session, EmployeeCreate(
        email="emp@test.io", password="secret1",
        full_name="E", phone="+7", role="ADMIN",
    ))
    res = await authenticate_employee(session, "emp@test.io", "wrong")
    assert res is None


def test_login_request_accepts_valid_email_and_password():
    req = LoginRequest(email="alice@test.io", password="secret1")
    assert req.email == "alice@test.io"
    assert req.password == "secret1"


def test_login_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="secret1")


def test_login_request_rejects_empty_password():
    with pytest.raises(ValidationError):
        LoginRequest(email="alice@test.io", password="")


def test_token_pair_defaults_to_dpop():
    pair = TokenPair(access_token="a", refresh_token="r")
    assert pair.token_type == "DPoP"


def test_token_pair_rejects_bearer():
    with pytest.raises(ValidationError):
        TokenPair(access_token="a", refresh_token="r", token_type="bearer")


def test_token_pair_rejects_unknown_token_type():
    with pytest.raises(ValidationError):
        TokenPair(access_token="a", refresh_token="r", token_type="mac")


def test_refresh_request_requires_non_empty_token():
    with pytest.raises(ValidationError):
        RefreshRequest(refresh_token="")