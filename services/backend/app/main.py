"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.cache.client import bootstrap_redis
from app.storage.client import bootstrap_storage
from app.logging_config import setup_logging
from app.middleware.rate_limit import RateLimitMiddleware
from app.integrations.grpc.channel import open_secure_channel
from app.integrations.grpc.matching_client import MatchingClient
from app.integrations.grpc.pricing_client import PricingClient
from app.integrations.grpc.recommendation_client import RecommendationClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify RustFS, gRPC service and Redis are reachable. Setup logging."""
    setup_logging()
    await bootstrap_storage(app)
    await bootstrap_redis(app)

    recommendation_client = RecommendationClient()
    await recommendation_client.start()
    app.state.recommendation_client = recommendation_client

    compute_channel = open_secure_channel()
    app.state.pricing_client = PricingClient(compute_channel)
    app.state.matching_client = MatchingClient(compute_channel)

    try:
        yield
    finally:
        await compute_channel.close()
        await recommendation_client.close()


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