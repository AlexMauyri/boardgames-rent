"""Reusable model mixins."""

from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class IdModel(Base):
    """Mixin that adds an integer surrogate primary key."""
    
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)