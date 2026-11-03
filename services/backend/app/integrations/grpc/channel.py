"""Shared TLS channel to the gRPC compute service."""

import grpc
import grpc.aio

from app.config import settings


def open_secure_channel() -> grpc.aio.Channel:
    """Open a TLS channel to ``settings.grpc_recommendation_addr``.

    The server hosts several services (recommendation, pricing, matching),
    so one channel is shared by all their clients.
    """
    with open(settings.grpc_ca_cert_path, "rb") as f:
        trusted_certs = f.read()

    credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)
    return grpc.aio.secure_channel(
        settings.grpc_recommendation_addr, credentials,
    )
