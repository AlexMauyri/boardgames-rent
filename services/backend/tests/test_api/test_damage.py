"""Tests for /api/v1/damage-reports/*."""

from uuid import uuid4

from app.auth.jwt import create_access_token
from app.db.models import GameCopy
from app.schemas import DamageReportCreate, EmployeeCreate
from app.services import create_employee
from app.services import damage as damage_service
from tests.helpers import (
    make_client,
    make_copy,
    make_game,
    make_manager,
    make_point,
)

URL = "/api/v1/damage-reports"


def _headers(user_id: int, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _inv() -> str:
    return f"INV-{uuid4().hex[:8]}"


async def _fresh(session, model, pk):
    row = await session.get(model, pk)
    await session.refresh(row)
    return row


async def _damaged(session, point_id: int, manager_id: int) -> tuple[int, int]:
    """Report a routine damage; return (copy_id, report_id)."""
    game = await make_game(session)
    copy_id = await make_copy(session, game, point_id, _inv())
    report = await damage_service.report_damage(
        session,
        manager_id,
        DamageReportCreate(game_copy_id=copy_id, description="broken box"),
    )
    return copy_id, report.id


async def test_resolve_marks_available(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    copy_id, report_id = await _damaged(session, p, m)

    r = await http.post(
        f"{URL}/{report_id}/resolve", headers=_headers(m, "MANAGER"),
    )
    assert r.status_code == 200
    assert r.json()["resolved_at"] is not None

    copy = await _fresh(session, GameCopy, copy_id)
    assert copy.status == "AVAILABLE"


async def test_resolve_twice_conflicts(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    _, report_id = await _damaged(session, p, m)

    r1 = await http.post(
        f"{URL}/{report_id}/resolve", headers=_headers(m, "MANAGER"),
    )
    assert r1.status_code == 200

    r2 = await http.post(
        f"{URL}/{report_id}/resolve", headers=_headers(m, "MANAGER"),
    )
    assert r2.status_code == 409


async def test_resolve_foreign_point_forbidden(http, session):
    p1 = await make_point(session, "Center")
    p2 = await make_point(session, "North")
    m1 = await make_manager(session, p1, "m1@test.io")
    m2 = await make_manager(session, p2, "m2@test.io")
    _, report_id = await _damaged(session, p1, m1)

    r = await http.post(
        f"{URL}/{report_id}/resolve", headers=_headers(m2, "MANAGER"),
    )
    assert r.status_code == 403


async def test_resolve_by_admin(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    _, report_id = await _damaged(session, p, m)

    admin = await create_employee(session, EmployeeCreate(
        email="admin@test.io", password="secret1",
        full_name="Admin", phone="+7", role="ADMIN",
    ))

    r = await http.post(
        f"{URL}/{report_id}/resolve", headers=_headers(admin.id, "ADMIN"),
    )
    assert r.status_code == 200


async def test_courier_gets_403(http, session):
    from tests.helpers import make_courier
    c = await make_courier(session)
    r = await http.post(
        f"{URL}/1/resolve", headers=_headers(c, "COURIER"),
    )
    assert r.status_code == 403


async def test_client_gets_403(http, session):
    client_id = await make_client(session, f"c-{uuid4().hex[:6]}@test.io")
    r = await http.post(
        f"{URL}/1/resolve", headers=_headers(client_id, "CLIENT"),
    )
    assert r.status_code == 403