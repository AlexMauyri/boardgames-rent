from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.pickup_point import PickupPoint


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("role IN ('COURIER','MANAGER','ADMIN')", name="role"),
        CheckConstraint(
            "(role = 'MANAGER' AND pickup_point_id IS NOT NULL) "
            "OR (role <> 'MANAGER' AND pickup_point_id IS NULL)",
            name="manager_requires_point",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20))
    pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    pickup_point: Mapped["PickupPoint | None"] = relationship(
        back_populates="employees",
        lazy="raise",
    )