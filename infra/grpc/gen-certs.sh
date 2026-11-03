#!/usr/bin/env bash
# Generate a development CA and a TLS certificate for the gRPC service.
#
#   bash infra/grpc/gen-certs.sh [output_dir]
#
# Default output: infra/grpc_certs (gitignored), mounted read-only into the
# `grpc` and `backend` containers as /app/certs. The server certificate is
# valid for the compose service name `grpc` and for localhost, so the backend
# (GRPC_RECOMMENDATION_ADDR=grpc:50051) and local tools can both verify it.
set -euo pipefail

# Git Bash on Windows rewrites "/CN=..." into a file path without this.
export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-$SCRIPT_DIR/../grpc_certs}"
DAYS="${CERT_DAYS:-825}"

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout ca.key -out ca.crt -days "$DAYS" -subj "/CN=boardgames-dev-ca" 2>/dev/null

openssl req -newkey rsa:2048 -nodes \
  -keyout server.key -out server.csr -subj "/CN=grpc" 2>/dev/null

printf 'subjectAltName=DNS:grpc,DNS:localhost,IP:127.0.0.1\n' > san.ext

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days "$DAYS" -extfile san.ext 2>/dev/null

rm -f server.csr san.ext ca.srl

# The containers run as uid 1000 and mount this directory read-only.
chmod 644 ca.crt server.crt server.key
chmod 600 ca.key

echo "Generated ca.crt, server.crt, server.key in $(pwd)"
