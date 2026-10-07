"""Courier delivery task model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.employee import Employee
    from app.db.models.order import Order
    from app.db.models.pickup_point import PickupPoint


class Delivery(Base):
    """A courier task moving an order's box between two pickup points.

    Attributes:
        id: Primary key.
        order_id: The order being served; unique, so an order has at most one
            delivery (1:1).
        courier_id: The assigned courier, or None until someone accepts. That
            the employee has role COURIER is checked by the service layer; a
            CHECK cannot look into another table.
        from_point_id: Pickup point the box is taken from.
        to_point_id: Pickup point the box is brought to; differs from
            `from_point_id`.
        status: One of CREATED, ACCEPTED, IN_TRANSIT, DELIVERED.
        created_at: Task creation timestamp, set by the database.
        delivered_at: Completion timestamp, or None while unfinished.
        order: The served order.
        courier: The assigned courier, or None.
        from_point: The departure point.
        to_point: The destination point.
    """

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("to_point_id <> from_point_id", name="distinct_points"),
        CheckConstraint(
            "status IN ('CREATED','ACCEPTED','IN_TRANSIT','DELIVERED')",
            name="status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        unique=True,
    )
    courier_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        index=True,
    )
    from_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
    )
    to_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="CREATED",
        server_default=text("'CREATED'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    order: Mapped["Order"] = relationship(back_populates="delivery", lazy="raise")
    courier: Mapped["Employee | None"] = relationship(lazy="raise")
    from_point: Mapped["PickupPoint"] = relationship(
        foreign_keys=[from_point_id],
        lazy="raise",
    )
    to_point: Mapped["PickupPoint"] = relationship(
        foreign_keys=[to_point_id],
        lazy="raise",
    )
