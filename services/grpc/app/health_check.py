"""Health check."""

import os
import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

CA_CERT_PATH = os.environ.get("GRPC_CA_CERT_PATH", "/app/certs/ca.crt")


def main() -> int:
    port = os.environ.get("GRPC_PORT", "50051")

    try:
        with open(CA_CERT_PATH, "rb") as f:
            trusted_certs = f.read()
    except FileNotFoundError:
        return 1

    credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

    with grpc.secure_channel(f"localhost:{port}", credentials) as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        try:
            resp = stub.Check(health_pb2.HealthCheckRequest(), timeout=2.0)
        except grpc.RpcError:
            return 1

        return 0 if resp.status == health_pb2.HealthCheckResponse.SERVING else 1


if __name__ == "__main__":
    sys.exit(main())