"""Configuration for the gRPC service."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    grpc_port: int = Field(default=50051, alias="GRPC_PORT")
    grpc_server_key_path: str = Field(
        default="/app/certs/server.key", alias="GRPC_SERVER_KEY_PATH",
    )
    grpc_server_cert_path: str = Field(
        default="/app/certs/server.crt", alias="GRPC_SERVER_CERT_PATH",
    )

    grpc_default_limit: int = Field(default=10, alias="GRPC_DEFAULT_LIMIT")
    grpc_max_candidates: int = Field(default=300, alias="GRPC_MAX_CANDIDATES")
    grpc_max_history_games: int = Field(default=20, alias="GRPC_MAX_HISTORY_GAMES")
    grpc_query_timeout_seconds: float = Field(
        default=3.0, alias="GRPC_QUERY_TIMEOUT_SECONDS",
    )

    @property
    def database_url(self) -> str:
        """Async asyncpg DSN assembled from discrete POSTGRES_* vars."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()