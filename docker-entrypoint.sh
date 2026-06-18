#!/bin/sh
set -e

SEED_DIR="/opt/hermes-seed"
DATA_DIR="${HERMES_HOME:-/opt/hermes-data}"

mkdir -p "$DATA_DIR/plugins"

# Always sync static config from the image (updated on every Railway deploy)
cp "$SEED_DIR/SOUL.md"     "$DATA_DIR/SOUL.md"
cp "$SEED_DIR/config.yaml" "$DATA_DIR/config.yaml"
cp -r "$SEED_DIR/plugins/." "$DATA_DIR/plugins/"

# Let Railway's PORT drive the LINE webhook port
export LINE_PORT="${PORT:-8646}"

exec "$@"
