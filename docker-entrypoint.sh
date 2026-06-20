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

# 儲存 Railway 給的真實 PORT
REAL_PORT="${PORT:-8000}"

# 關鍵：將 agent 套件路徑加入 PYTHONPATH，以解決 hermes-agent 套件將 cron 模組包在 agent 資料夾下導致的 ModuleNotFoundError
export PYTHONPATH="/usr/local/lib/python3.11/site-packages/agent:$PYTHONPATH"

# 啟動背景的 Hermes Gateway，監聽 8646 (專收 LINE Webhook)
export PORT=8646
export LINE_PORT=8646
# 關鍵：啟用允許所有使用者，否則 LINE Adapter 會靜默丟棄沒在 Allowlist 裡的使用者訊息
export LINE_ALLOW_ALL_USERS=true
hermes gateway &

# 等待 Gateway 完全啟動
sleep 3

# 啟動前景的自訂捷徑 API 代理伺服器，監聽 Railway 給的真實 PORT
export PORT="$REAL_PORT"
exec python /opt/hermes-data/api.py
