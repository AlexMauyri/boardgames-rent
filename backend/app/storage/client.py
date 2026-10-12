"""
RustFS / S3-compatible client bootstrap and FastAPI dependency.

The `minio` SDK is synchronous and blocking. Every call that performs network
I/O must be dispatched by the caller via `anyio.to_thread.run_sync`.
"""

import logging

import anyio.to_thread
from fastapi import FastAPI, Request
from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


def build_s3_client() -> Minio:
    """Construct a synchronous S3 client from settings. Performs no network I/O."""
    return Minio(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.s3_secure,
    )


async def check_bucket_exists(client: Minio, bucket: str) -> bool:
    """Run the blocking `bucket_exists` probe off the event loop."""
    return await anyio.to_thread.run_sync(client.bucket_exists, bucket)


async def bootstrap_storage(app: FastAPI) -> None:
    """Create the client and verify the bucket exists. Called from lifespan.

    Raises on any failure — a backend that cannot reach object storage must not
    start, otherwise cover uploads fail at request time instead of boot time.
    """
    client = build_s3_client()
    try:
        exists = await check_bucket_exists(client, settings.s3_bucket)
    except S3Error as exc:
        logger.exception("RustFS unreachable or rejected credentials")
        raise RuntimeError(
            f"Cannot verify bucket {settings.s3_bucket!r} on {settings.s3_endpoint}"
        ) from exc

    if not exists:
        raise RuntimeError(
            f"Bucket {settings.s3_bucket!r} does not exist on {settings.s3_endpoint}. "
            "Was rustfs-init run?"
        )

    logger.info(
        "RustFS client ready: endpoint=%s bucket=%s secure=%s",
        settings.s3_endpoint,
        settings.s3_bucket,
        settings.s3_secure,
    )
    app.state.s3_client = client


def get_storage_client(request: Request) -> Minio:
    """FastAPI dependency returning the shared client from app.state."""
    return request.app.state.s3_client