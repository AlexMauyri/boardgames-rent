"""Configuration for the notification service."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL",
    )
    rabbitmq_exchange: str = Field(
        default="boardgame.events", alias="RABBITMQ_EXCHANGE",
    )
    rabbitmq_queue: str = Field(
        default="notifications", alias="RABBITMQ_QUEUE",
    )
    rabbitmq_retry_seconds: float = Field(
        default=3.0, alias="RABBITMQ_RETRY_SECONDS",
    )

    ws_auth_timeout_seconds: float = Field(
        default=5.0, alias="WS_AUTH_TIMEOUT_SECONDS",
    )


settings = Settings()
