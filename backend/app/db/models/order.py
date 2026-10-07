"""Rental order model."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.client import Client
    from app.db.models.delivery import Delivery
    from app.db.models.order_item import OrderItem
    from app.db.models.pickup_point import PickupPoint


class Order(Base):
    """A client's rental request for one or more game boxes.

    Attributes:
        id: Primary key; the booking number shown to the client.
        client_id: The client who placed the order.
        pickup_point_id: Pickup point where the client collects the games.
        start_date: First day of the rental.
        end_date: Last day of the rental, not before `start_date`.
        total_price: Total rental cost, non-negative.
        deposit_paid: Deposit taken from the client, non-negative.
        status: One of CREATED, NEEDS_TRANSFER, IN_TRANSIT, READY_FOR_PICKUP,
            ACTIVE, COMPLETED, CANCELLED.
        created_at: Placement timestamp, set by the database.
        client: The ordering client.
        pickup_point: The collection point.
        items: The boxes included in the order.
        delivery: The transfer task for this order, or None.
    """

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="end_date"),
        CheckConstraint("total_price >= 0", name="total_price"),
        CheckConstraint("deposit_paid >= 0", name="deposit_paid"),
        CheckConstraint(
            "status IN ('CREATED','NEEDS_TRANSFER','IN_TRANSIT',"
            "'READY_FOR_PICKUP','ACTIVE','COMPLETED','CANCELLED')",
            name="status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"),
        index=True,
    )
    pickup_point_id: Mapped[int] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    deposit_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(
        String(30),
        default="CREATED",
        server_default=text("'CREATED'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    client: Mapped["Client"] = relationship(lazy="raise")
    pickup_point: Mapped["PickupPoint"] = relationship(lazy="raise")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    delivery: Mapped["Delivery | None"] = relationship(
        back_populates="order",
        lazy="raise",
        passive_deletes=True,
    )
