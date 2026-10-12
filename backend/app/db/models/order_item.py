"""Order line model: the M:N link between orders and game boxes."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.game_copy import GameCopy
    from app.db.models.order import Order


class OrderItem(Base):
    """One game box inside an order.

    Mapped as a class rather than a plain `Table` (unlike `game_categories`)
    because the link carries its own data, `price_at_rental`.

    Attributes:
        order_id: The order; part of the composite primary key.
        game_copy_id: The rented box; part of the composite primary key.
        price_at_rental: Tariff frozen at booking time, non-negative.
        order: The owning order.
        game_copy: The rented box.
    """

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("price_at_rental >= 0", name="price_at_rental"),
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        primary_key=True,
    )
    game_copy_id: Mapped[int] = mapped_column(
        ForeignKey("game_copies.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    price_at_rental: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    order: Mapped["Order"] = relationship(back_populates="items", lazy="raise")
    game_copy: Mapped["GameCopy"] = relationship(lazy="raise")
