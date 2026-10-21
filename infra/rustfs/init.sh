#!/bin/sh
set -e

rc alias set local http://rustfs:9000 "$RUSTFS_ACCESS_KEY" "$RUSTFS_SECRET_KEY"

rc mb --ignore-existing local/board-game-covers

rc anonymous set download local/board-game-covers

rc admin policy create local covers-write /policies/board-game-covers-write.json 2>/dev/null || true

rc admin service-account create local/ "$RUSTFS_APP_ACCESS_KEY" "$RUSTFS_APP_SECRET_KEY" --policy /policies/board-game-covers-write.json 2>/dev/null || true

echo "RustFS init done"

rc anonymous get local/board-game-covers
rc admin service-account ls local