"""Employee account model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.pickup_point import PickupPoint


class Employee(Base):
    """A courier, pickup point manager, or administrator.

    Attributes:
        id: Primary key.
        email: Login address, unique and case-sensitive.
        password_hash: Argon2id digest. Plaintext is never stored.
        full_name: Display name of the employee.
        is_active: False disables authentication; the row is never deleted.
        phone: Contact phone number.
        role: One of COURIER, MANAGER, ADMIN.
        pickup_point_id: Assigned pickup point; non-null iff `role` is MANAGER.
        created_at: Account creation timestamp, set by the database.
        pickup_point: The assigned pickup point, or None.
    """

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
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
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