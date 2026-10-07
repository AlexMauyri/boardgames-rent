"""Damage report model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.employee import Employee
    from app.db.models.game_copy import GameCopy
    from app.db.models.order import Order


class DamageReport(Base):
    """A record of damage or missing parts found on a game box.

    Attributes:
        id: Primary key.
        game_copy_id: The damaged box.
        order_id: The rental during which the damage was found, or None for a
            routine inspection.
        reported_by: The employee (manager) who filed the report.
        description: What is damaged or missing.
        deposit_withheld: Amount kept from the client's deposit, non-negative.
        created_at: Filing timestamp, set by the database.
        resolved_at: When the box was repaired or written off, or None.
        game_copy: The damaged box.
        order: The related order, or None.
        reporter: The employee who filed the report.
    """

    __tablename__ = "damage_reports"
    __table_args__ = (
        CheckConstraint("deposit_withheld >= 0", name="deposit_withheld"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_copy_id: Mapped[int] = mapped_column(
        ForeignKey("game_copies.id", ondelete="RESTRICT"),
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        index=True,
    )
    reported_by: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
    )
    description: Mapped[str] = mapped_column(Text)
    deposit_withheld: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0"),
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    game_copy: Mapped["GameCopy"] = relationship(lazy="raise")
    order: Mapped["Order | None"] = relationship(lazy="raise")
    reporter: Mapped["Employee"] = relationship(lazy="raise")
