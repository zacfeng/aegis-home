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
cp "$SEED_DIR/api.py" "$DATA_DIR/api.py"

# 直接啟動我們自己的 API 伺服器
# 同時處理 LINE Webhook 和 iOS 捷徑
exec python /opt/hermes-data/api.py
