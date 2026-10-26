"""gRPC recommendation service entrypoint."""

import asyncio
import logging

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc, health

from app.config import settings
from app.generated.recommendation.v1 import recommendation_pb2_grpc
from app.recommendation.service import RecommendationServicer

logger = logging.getLogger(__name__)


async def create_server() -> tuple[grpc.aio.Server, health_aio.HealthServicer]:
    """Build the gRPC server with all services registered, no port bound."""
    server = grpc.aio.server()

    health_servicer = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationServicer(), server,
    )

    return server, health_servicer


async def serve() -> None:
    """Start the TLS gRPC server and block until termination."""
    from app.db import engine

    with open(settings.grpc_server_key_path, "rb") as f:
        private_key = f.read()
    with open(settings.grpc_server_cert_path, "rb") as f:
        certificate_chain = f.read()

    server_credentials = grpc.ssl_server_credentials(
        ((private_key, certificate_chain),)
    )

    server, health_servicer = await create_server()
    server.add_secure_port(
        f"[::]:{settings.grpc_port}", server_credentials,
    )
    await server.start()
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    logger.info(
        "gRPC recommendation service listening on :%s (TLS)",
        settings.grpc_port,
    )

    try:
        await server.wait_for_termination()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    )
    asyncio.run(serve())