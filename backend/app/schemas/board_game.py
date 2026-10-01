"""Board game API contracts."""

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field, computed_field, model_validator

from app.config import settings
from app.schemas.base import ORMBase


class _PlayerRange(Protocol):
    """Structural type for the values ``validate_against`` reads."""

    min_players: int
    max_players: int


class BoardGameCreate(BaseModel):
    """Payload for adding a game to the catalog.

    Attributes:
        title: Display name.
        description: Optional free-form text.
        min_players: Minimum supported player count, at least 1.
        max_players: Maximum supported player count, at least `min_players`.
        playtime_minutes: Average play time in minutes, at least 1.
        daily_price: Rental price per day, non-negative.
        deposit_price: Refundable deposit, non-negative.
        category_ids: Categories to link. Unknown ids are rejected by the
            service layer with a `ValueError`.
    """

    title: str
    description: str | None = None
    min_players: int = Field(gt=0)
    max_players: int
    playtime_minutes: int = Field(gt=0)
    daily_price: Decimal = Field(ge=0)
    deposit_price: Decimal = Field(ge=0)
    category_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_players_range(self) -> "BoardGameCreate":
        if self.max_players < self.min_players:
            raise ValueError("max_players must be >= min_players")
        return self


class BoardGameRead(ORMBase):
    """Board game as returned by the API.

    Attributes:
        id: Primary key.
        title: Display name.
        description: Optional free-form text.
        min_players: Minimum supported player count.
        max_players: Maximum supported player count.
        playtime_minutes: Average play time in minutes.
        daily_price: Rental price per day.
        deposit_price: Refundable deposit.
        cover_key: S3 object key, excluded from serialisation. Present on
            the model so `cover_url` can be derived; never appears in JSON.
        cover_url: Full public URL of the cover, or None when no image is
            attached. Computed from `cover_key` and `settings`.
    """

    id: int
    title: str
    description: str | None = None
    min_players: int
    max_players: int
    playtime_minutes: int
    daily_price: Decimal
    deposit_price: Decimal
    cover_key: str | None = Field(default=None, exclude=True, repr=False)

    @computed_field
    @property
    def cover_url(self) -> str | None:
        if not self.cover_key:
            return None
        base = settings.public_base_url.rstrip("/")
        return f"{base}/{settings.s3_bucket}/{self.cover_key}"


class BoardGameUpdate(BaseModel):
    """Partial board game update; unset fields are left alone."""

    title: str | None = None
    description: str | None = None
    min_players: int | None = Field(default=None, gt=0)
    max_players: int | None = None
    playtime_minutes: int | None = Field(default=None, gt=0)
    daily_price: Decimal | None = Field(default=None, ge=0)
    deposit_price: Decimal | None = Field(default=None, ge=0)
    category_ids: list[int] | None = None

    def validate_against(self, current: _PlayerRange) -> None:
        """Validate the player range against the merged state.

        Args:
            current: The existing board game row about to be updated. Only
                `min_players` and `max_players` are read from it.

        Raises:
            ValueError: The merged values violate `max_players >= min_players`.
        """
        effective_min = (
            self.min_players
            if "min_players" in self.model_fields_set
            else current.min_players
        )
        effective_max = (
            self.max_players
            if "max_players" in self.model_fields_set
            else current.max_players
        )
        if effective_min is None or effective_max is None:
            return
        if effective_max < effective_min:
            raise ValueError("max_players must be >= min_players")


class CoverUploadResponse(BaseModel):
    """Response returned after a cover image is uploaded.

    Attributes:
        cover_key: RustFS object key of the stored file.
        cover_url: Full public URL of the stored file.
    """

    cover_key: str
    cover_url: str