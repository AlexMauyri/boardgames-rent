from decimal import Decimal

from pydantic import BaseModel, Field, computed_field, model_validator

from app.config import settings
from app.schemas.base import ORMBase


class BoardGameCreate(BaseModel):
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
    title: str | None = None
    description: str | None = None
    min_players: int | None = Field(default=None, gt=0)
    max_players: int | None = None
    playtime_minutes: int | None = Field(default=None, gt=0)
    daily_price: Decimal | None = Field(default=None, ge=0)
    deposit_price: Decimal | None = Field(default=None, ge=0)
    category_ids: list[int] | None = None

    @model_validator(mode="after")
    def _validate_players_range(self) -> "BoardGameUpdate":
        if self.min_players is None or self.max_players is None:
            return self
        if self.max_players < self.min_players:
            raise ValueError("max_players must be >= min_players")
        return self


class CoverUploadResponse(BaseModel):
    cover_key: str
    cover_url: str