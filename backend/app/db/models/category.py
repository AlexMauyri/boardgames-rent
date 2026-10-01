"""Game category model."""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.game_category import game_categories

if TYPE_CHECKING:
    from app.db.models.board_game import BoardGame


class Category(Base):
    """A genre tag applied to board games.

    Attributes:
        id: Primary key.
        name: Unique category name.
        games: Board games tagged with this category.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    games: Mapped[list["BoardGame"]] = relationship(
        secondary=game_categories,
        back_populates="categories",
        lazy="raise",
        passive_deletes=True,
    )