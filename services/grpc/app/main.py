"""gRPC recommendation service entrypoint."""

import logging
import os
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

SERVER_KEY_PATH = os.environ.get("GRPC_SERVER_KEY_PATH", "/app/certs/server.key")
SERVER_CERT_PATH = os.environ.get("GRPC_SERVER_CERT_PATH", "/app/certs/server.crt")


def serve() -> None:
    port = os.environ.get("GRPC_PORT", "50051")

    with open(SERVER_KEY_PATH, "rb") as f:
        private_key = f.read()
    with open(SERVER_CERT_PATH, "rb") as f:
        certificate_chain = f.read()

    server_credentials = grpc.ssl_server_credentials(
        ((private_key, certificate_chain),)
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    server.add_secure_port(f"[::]:{port}", server_credentials)
    server.start()
    logger.info("gRPC recommendation service listening securely on :%s", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()