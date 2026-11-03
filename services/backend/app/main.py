"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.cache.client import bootstrap_redis
from app.integrations.grpc.channel import open_secure_channel, probe_channel
from app.integrations.grpc.matching_client import MatchingClient
from app.integrations.grpc.pricing_client import PricingClient
from app.integrations.grpc.recommendation_client import RecommendationClient
from app.integrations.rabbitmq.publisher import RabbitPublisher
from app.logging_config import setup_logging
from app.middleware.rate_limit import RateLimitMiddleware
from app.storage.client import bootstrap_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify RustFS and Redis, open gRPC and RabbitMQ clients."""
    setup_logging()
    await bootstrap_storage(app)
    await bootstrap_redis(app)

    compute_channel = open_secure_channel()
    await probe_channel(compute_channel)
    app.state.recommendation_client = RecommendationClient(compute_channel)
    app.state.pricing_client = PricingClient(compute_channel)
    app.state.matching_client = MatchingClient(compute_channel)

    event_publisher = RabbitPublisher()
    await event_publisher.start()
    app.state.event_publisher = event_publisher

    try:
        yield
    finally:
        await event_publisher.close()
        await compute_channel.close()


app = FastAPI(
    title="Board Game Rental API",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.include_router(api_router)
register_exception_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for docker healthcheck."""
    return {"status": "ok"}