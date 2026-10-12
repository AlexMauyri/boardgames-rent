"""Tests for employee creation, role/point assignment and role transitions."""

import pytest

from app.schemas import EmployeeCreate, EmployeeUpdate, PickupPointCreate
from app.services import (
    assign_manager_to_point,
    authenticate_employee,
    change_employee_role,
    create_employee,
    create_pickup_point,
    list_employees,
    update_employee,
)
from app.services.exceptions import ConflictError, NotFoundError


async def _make_point(session, name="Center"):
    return await create_pickup_point(session, PickupPointCreate(
        name=name, address="addr", phone="+7",
    ))


async def _make_manager(session, point_id, email="mgr@test.io"):
    return await create_employee(session, EmployeeCreate(
        email=email, password="secret1",
        full_name="Manager", phone="+79990000010",
        role="MANAGER", pickup_point_id=point_id,
    ))


async def _make_courier(session, email="cour@test.io"):
    return await create_employee(session, EmployeeCreate(
        email=email, password="secret1",
        full_name="Courier", phone="+79990000011",
        role="COURIER",
    ))


async def test_create_manager_with_point(session):
    p = await _make_point(session)
    m = await _make_manager(session, p.id)
    assert m.role == "MANAGER"
    assert m.pickup_point_id == p.id


async def test_create_courier_without_point(session):
    c = await _make_courier(session)
    assert c.role == "COURIER"
    assert c.pickup_point_id is None


async def test_create_employee_duplicate_email(session):
    p = await _make_point(session)
    await _make_manager(session, p.id, "dup@test.io")
    with pytest.raises(ConflictError):
        await create_employee(session, EmployeeCreate(
            email="dup@test.io", password="secret1",
            full_name="X", phone="+7", role="ADMIN",
        ))


async def test_manager_without_point_rejected_by_schema(session):
    with pytest.raises(Exception):
        EmployeeCreate(
            email="m2@test.io", password="secret1",
            full_name="M2", phone="+7", role="MANAGER",
        )


async def test_invalid_role_rejected_by_schema(session):
    with pytest.raises(Exception):
        EmployeeCreate(
            email="bad@test.io", password="secret1",
            full_name="Bad", phone="+7", role="INVALID",
        )


async def test_authenticate_employee_correct(session):
    p = await _make_point(session)
    await _make_manager(session, p.id)
    res = await authenticate_employee(session, "mgr@test.io", "secret1")
    assert res is not None
    assert res.email == "mgr@test.io"


async def test_authenticate_employee_wrong_password(session):
    p = await _make_point(session)
    await _make_manager(session, p.id)
    res = await authenticate_employee(session, "mgr@test.io", "wrong")
    assert res is None


async def test_list_employees_all(session):
    p = await _make_point(session)
    await _make_manager(session, p.id)
    await _make_courier(session)
    rows = await list_employees(session)
    assert len(rows) == 2


async def test_list_employees_role_filter(session):
    p = await _make_point(session)
    await _make_manager(session, p.id)
    await _make_courier(session)
    rows = await list_employees(session, role="MANAGER")
    assert len(rows) == 1
    assert rows[0].email == "mgr@test.io"


async def test_assign_manager_to_point_rejects_non_manager(session):
    p = await _make_point(session)
    c = await _make_courier(session)
    with pytest.raises(ValueError):
        await assign_manager_to_point(session, c.id, p.id)


async def test_assign_manager_to_point_reassigns(session):
    p1 = await _make_point(session, "North")
    p2 = await _make_point(session, "Center")
    m = await _make_manager(session, p1.id)
    assigned = await assign_manager_to_point(session, m.id, p2.id)
    assert assigned.pickup_point_id == p2.id


async def test_assign_manager_to_point_missing_point(session):
    p = await _make_point(session)
    m = await _make_manager(session, p.id)
    with pytest.raises(NotFoundError):
        await assign_manager_to_point(session, m.id, 999999)


async def test_assign_manager_to_point_cannot_clear(session):
    p = await _make_point(session)
    m = await _make_manager(session, p.id)
    with pytest.raises(ValueError):
        await assign_manager_to_point(session, m.id, None)


async def test_change_role_manager_to_courier_explicit_none(session):
    p = await _make_point(session)
    m = await _make_manager(session, p.id)
    demoted = await change_employee_role(
        session, m.id, "COURIER", pickup_point_id=None,
    )
    assert demoted.role == "COURIER"
    assert demoted.pickup_point_id is None


async def test_change_role_manager_to_courier_implicit_default(session):
    p = await _make_point(session)
    m = await _make_manager(session, p.id)
    # No pickup_point_id argument: defaults to None, which is the correct
    # target for COURIER.
    demoted = await change_employee_role(session, m.id, "COURIER")
    assert demoted.role == "COURIER"
    assert demoted.pickup_point_id is None


async def test_change_role_courier_to_manager_without_point(session):
    c = await _make_courier(session)
    with pytest.raises(ValueError):
        await change_employee_role(session, c.id, "MANAGER")


async def test_update_employee_demote_without_point(session):
    p = await _make_point(session)
    m = await _make_manager(session, p.id)
    with pytest.raises(ValueError):
        await update_employee(session, m.id, EmployeeUpdate(role="COURIER"))


async def test_update_employee_profile_change(session):
    c = await _make_courier(session)
    upd = await update_employee(session, c.id, EmployeeUpdate(full_name="Courier2"))
    assert upd.full_name == "Courier2"