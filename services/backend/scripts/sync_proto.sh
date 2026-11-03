#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
GRPC_DIR="$(dirname "$BACKEND_DIR")/grpc"

SRC="$GRPC_DIR/app/generated"
DST="$BACKEND_DIR/app/grpc_generated"

if [ ! -d "$SRC" ]; then
  echo "Error: $SRC does not exist. Run services/grpc/scripts/generate_proto.sh first."
  exit 1
fi

rm -rf "$DST"
cp -r "$SRC" "$DST"
echo "Synced generated proto stubs: $SRC -> $DST"