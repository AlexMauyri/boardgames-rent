from sqlalchemy import Column, ForeignKey, Integer, Table

from app.db.base import Base

game_categories = Table(
    "game_categories",
    Base.metadata,
    Column(
        "game_id",
        Integer,
        ForeignKey("board_games.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)