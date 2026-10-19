"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.cache.client import bootstrap_redis
from app.storage.client import bootstrap_storage
from app.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify RustFS and Redis are reachable. Setup logging."""
    setup_logging()
    await bootstrap_storage(app)
    await bootstrap_redis(app)
    yield


app = FastAPI(
    title="Board Game Rental API",
    lifespan=lifespan,
)

app.include_router(api_router)
register_exception_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for docker healthcheck."""
    return {"status": "ok"}