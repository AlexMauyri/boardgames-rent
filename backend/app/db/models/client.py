"""Client account model."""

from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Client(Base):
    """A customer who rents board games.
    
    Attributes:
        id: Primary key.
        email: Login address, unique and case-sensitive.
        password_hash: Argon2id digest. Plaintext is never stored.
        full_name: Display name of the client.
        is_active: False disables authentication; the row is never deleted.
        phone: Contact phone number.
        created_at: Registration timestamp, set by the database.
    """

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    phone: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )