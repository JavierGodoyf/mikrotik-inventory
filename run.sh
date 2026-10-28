#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
export MTIK_BASE_DIR="${MTIK_BASE_DIR:-$(pwd)}"
exec .venv/bin/mikrotik-panel
