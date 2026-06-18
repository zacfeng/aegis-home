#!/bin/sh
set -e
export PYTHONUNBUFFERED=1

SEED_DIR="/opt/hermes-seed"
DATA_DIR="${HERMES_HOME:-/opt/hermes-data}"

mkdir -p "$DATA_DIR/plugins"

# Always sync static config from the image (updated on every Railway deploy)
cp "$SEED_DIR/SOUL.md"     "$DATA_DIR/SOUL.md"
cp "$SEED_DIR/config.yaml" "$DATA_DIR/config.yaml"
cp -r "$SEED_DIR/plugins/." "$DATA_DIR/plugins/"

# 儲存 Railway 給的真實 PORT
REAL_PORT="${PORT:-8000}"

# 啟動背景的 Hermes Gateway，監聽 8646 (專收 LINE Webhook)
export PORT=8646
export LINE_PORT=8646
hermes gateway &

# 啟動前景的自訂捷徑 API 代理伺服器，監聽 Railway 給的真實 PORT
export PORT="$REAL_PORT"
exec python /opt/hermes-data/api.py
