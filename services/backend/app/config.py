"""
Application settings.

Lowest-level module in the backend — must not import from `app/`.
All configuration is sourced from environment variables / `.env`.
"""

from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateLimitRule(BaseModel):
    """A single rate-limit rule."""

    limit: int = Field(gt=0)
    window: int = Field(gt=0, description="Window in seconds")


_DEFAULT_RULES: dict[str, RateLimitRule] = {
    "/api/v1/auth/login":    RateLimitRule(limit=10,   window=100),
    "/api/v1/auth/register": RateLimitRule(limit=3,   window=3600),
    "/api/v1/auth/refresh":  RateLimitRule(limit=30,  window=60),
    "/api/v1/auth/logout":   RateLimitRule(limit=10,  window=60),
    "/api/v1/orders":        RateLimitRule(limit=10,  window=3600),
    "/api/v1/catalog":       RateLimitRule(limit=120, window=60),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    s3_endpoint: str = Field(alias="S3_ENDPOINT")
    s3_access_key: str = Field(alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(alias="S3_SECRET_KEY")
    s3_bucket: str = Field(alias="S3_BUCKET")
    s3_secure: bool = Field(default=False, alias="S3_SECURE")

    public_base_url: str = Field(alias="PUBLIC_BASE_URL")

    upload_max_bytes: int = Field(alias="UPLOAD_MAX_BYTES")
    upload_allowed_mime_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"],
        alias="UPLOAD_ALLOWED_MIME_TYPES",
    )

    redis_url: str = Field(alias="REDIS_URL")
    catalog_cache_ttl: int = Field(default=600, alias="CATALOG_CACHE_TTL")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_ttl: int = Field(default=900, alias="ACCESS_TOKEN_TTL")
    refresh_token_ttl: int = Field(
        default=60 * 60 * 24 * 30,
        alias="REFRESH_TOKEN_TTL",
    )

    dpop_iat_window_seconds: int = Field(
        default=60, alias="DPOP_IAT_WINDOW_SECONDS",
    )
    dpop_jti_ttl_seconds: int = Field(
        default=300, alias="DPOP_JTI_TTL_SECONDS",
    )
    dpop_require_nonce: bool = Field(
        default=True, alias="DPOP_REQUIRE_NONCE",
    )

    rate_limit_rules: dict[str, RateLimitRule] = Field(
        default_factory=lambda: dict(_DEFAULT_RULES),
        description="Per-prefix rate-limit rules. Override via RATE_LIMIT_RULES JSON.",
    )

    @property
    def database_url(self) -> str:
        """Async asyncpg DSN, assembled from discrete POSTGRES_* vars."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()