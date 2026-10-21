"""Damage report resolution: available to managers and administrators.

Managers may resolve reports for boxes at their own point; admins may
resolve any report. The check is done by the service layer; the router
only enforces the role.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_role
from app.db.models import Employee
from app.schemas import DamageReportRead
from app.services import damage as damage_service

router = APIRouter()

_Resolver = Annotated[Employee, Depends(require_role("MANAGER", "ADMIN"))]


@router.post("/{report_id}/resolve", response_model=DamageReportRead)
async def resolve_report(
    report_id: int,
    employee: _Resolver,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DamageReportRead:
    """Mark a damage report as resolved. Idempotent per report — a second
    resolve of the same report returns 409."""
    return await damage_service.resolve_damage_report(
        session, report_id, employee.id,
    )