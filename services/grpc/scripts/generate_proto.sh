#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$ROOT_DIR/proto"
OUT_DIR="$ROOT_DIR/app/generated"

mkdir -p "$OUT_DIR"

PROTO_FILES=$(find "$PROTO_DIR" -name '*.proto' | sort)

# shellcheck disable=SC2086
python -m grpc_tools.protoc \
  -I"$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  $PROTO_FILES

touch "$OUT_DIR/__init__.py"

# protoc emits absolute imports ("from pkg.v1 import x_pb2"); inside the
# generated package they have to be relative.
for PB2_GRPC in $(find "$OUT_DIR" -name '*_pb2_grpc.py'); do
    sed -i -E 's/^from [a-z_]+\.v1 import /from . import /' "$PB2_GRPC"
done

for PKG in $(find "$OUT_DIR" -mindepth 1 -type d -not -name '__pycache__'); do
    touch "$PKG/__init__.py"
done

echo "Generated stubs in $OUT_DIR"
