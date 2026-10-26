"""Health check."""

import os
import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc


def main() -> int:
    port = os.environ.get("GRPC_PORT", "50051")
    with grpc.insecure_channel(f"localhost:{port}") as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        try:
            resp = stub.Check(health_pb2.HealthCheckRequest(), timeout=2.0)
        except grpc.RpcError:
            return 1
        return 0 if resp.status == health_pb2.HealthCheckResponse.SERVING else 1


if __name__ == "__main__":
    sys.exit(main())