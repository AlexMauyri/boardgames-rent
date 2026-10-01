"""Pickup point model."""

from typing import TYPE_CHECKING

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.employee import Employee


class PickupPoint(Base):
    """A physical location where games are stored and handed out.

    Attributes:
        id: Primary key.
        name: Unique display name.
        address: Physical address of the point.
        phone: Contact phone number of the point.
        is_active: False hides the point from the public list; the row 
            remains visible to administrators.
        employees: Employees assigned to this point.
    """

    __tablename__ = "pickup_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    employees: Mapped[list["Employee"]] = relationship(
        back_populates="pickup_point",
        lazy="raise",
        passive_deletes=True,
    )