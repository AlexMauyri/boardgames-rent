"""
Application settings.

Lowest-level module in the backend — must not import from `app/`.
All configuration is sourced from environment variables / `.env`.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def database_url(self) -> str:
        """Async asyncpg DSN, assembled from discrete POSTGRES_* vars."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()