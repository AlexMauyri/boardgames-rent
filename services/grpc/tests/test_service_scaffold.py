"""Tests for the scaffolded gRPC service."""

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)


async def test_health_reports_serving(grpc_server):
    async with grpc.aio.insecure_channel(f"localhost:{grpc_server}") as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        resp = await stub.Check(health_pb2.HealthCheckRequest(), timeout=2.0)
    assert resp.status == health_pb2.HealthCheckResponse.SERVING
