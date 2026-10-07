"""Physical game box model."""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.board_game import BoardGame
    from app.db.models.pickup_point import PickupPoint


class GameCopy(Base):
    """One physical box of a catalog game, tracked by inventory number.

    Attributes:
        id: Primary key.
        game_id: The catalog entry this box is a copy of.
        current_point_id: Pickup point holding the box; None while the box is
            with a client or in transit.
        inventory_number: Unique barcode label of the box.
        status: One of AVAILABLE, WITH_CLIENT, IN_TRANSIT, DAMAGED.
        game: The catalog entry.
        current_point: The pickup point holding the box, or None.
    """

    __tablename__ = "game_copies"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AVAILABLE','WITH_CLIENT','IN_TRANSIT','DAMAGED')",
            name="status",
        ),
        CheckConstraint(
            "(status IN ('WITH_CLIENT','IN_TRANSIT') "
            "AND current_point_id IS NULL) "
            "OR (status IN ('AVAILABLE','DAMAGED') "
            "AND current_point_id IS NOT NULL)",
            name="location_matches_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("board_games.id", ondelete="RESTRICT"),
        index=True,
    )
    current_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="RESTRICT"),
        index=True,
    )
    inventory_number: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(
        String(30),
        default="AVAILABLE",
        server_default=text("'AVAILABLE'"),
    )

    game: Mapped["BoardGame"] = relationship(lazy="raise")
    current_point: Mapped["PickupPoint | None"] = relationship(lazy="raise")
