#!/usr/bin/env bash
# Generate one draft. Intended for cron / launchd. Logs to data/logs/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/logs
exec .venv/bin/postgen run >> "data/logs/run-$(date +%F).log" 2>&1
