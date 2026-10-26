#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$ROOT_DIR/proto"
OUT_DIR="$ROOT_DIR/app/generated"

mkdir -p "$OUT_DIR"

python -m grpc_tools.protoc \
  -I"$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR/recommendation/v1/recommendation.proto"

PB2_GRPC="$OUT_DIR/recommendation/v1/recommendation_pb2_grpc.py"
if [ -f "$PB2_GRPC" ]; then
    sed -i \
    's/^from recommendation\.v1 import /from . import /' \
    "$PB2_GRPC"
fi

touch "$OUT_DIR/__init__.py"
touch "$OUT_DIR/recommendation/__init__.py"
touch "$OUT_DIR/recommendation/v1/__init__.py"

echo "Generated stubs in $OUT_DIR"