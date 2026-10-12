"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.storage.client import bootstrap_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify RustFS is reachable and the bucket exists.
    Shutdown: nothing to tear down (engine and S3 client are process-wide).
    """
    await bootstrap_storage(app)
    yield


app = FastAPI(
    title="Board Game Rental API",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for docker healthcheck."""
    return {"status": "ok"}