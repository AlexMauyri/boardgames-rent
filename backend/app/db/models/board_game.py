"""Board game catalog model."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.game_category import game_categories

if TYPE_CHECKING:
    from app.db.models.category import Category


class BoardGame(Base):
    """A catalog entry describing a game model.

    Attributes:
        id: Primary key.
        title: Display name of the game.
        description: Free-form text, optionally including short rules.
        min_players: Minimum supported player count, at least 1.
        max_players: Maximum supported player count, at least `min_players`.
        playtime_minutes: Average play time of one session.
        daily_price: Rental price per day, non-negative.
        deposit_price: Refundable deposit, non-negative.
        cover_key: S3 object key of the cover image, or None.
        categories: The categories this game is tagged with.
    """

    __tablename__ = "board_games"
    __table_args__ = (
        CheckConstraint("min_players > 0", name="min_players"),
        CheckConstraint("max_players >= min_players", name="max_players"),
        CheckConstraint("daily_price >= 0", name="daily_price"),
        CheckConstraint("deposit_price >= 0", name="deposit_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    min_players: Mapped[int] = mapped_column(SmallInteger)
    max_players: Mapped[int] = mapped_column(SmallInteger)
    playtime_minutes: Mapped[int] = mapped_column(SmallInteger)
    daily_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    deposit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    cover_key: Mapped[str | None] = mapped_column(String(255))

    categories: Mapped[list["Category"]] = relationship(
        secondary=game_categories,
        back_populates="games",
        lazy="raise",
        passive_deletes=True,
    )