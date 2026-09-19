#!/usr/bin/env bash
# Copy an existing local data/ directory (profile, corpus, postgen.db, voice profile) into
# the named Docker volume used by compose, with ownership set for the container's
# nonroot user. Run once when moving from a local checkout to the container.
#
#   scripts/import-data.sh [source-dir]   # default: ./data
set -euo pipefail
cd "$(dirname "$0")/.."
src="${1:-./data}"
[[ -d "$src" ]] || { echo "no such directory: $src" >&2; exit 1; }
project="$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_-' '-')"
volume="${POSTGEN_VOLUME:-${project}_postgen-data}"
echo "Copying $src -> volume $volume"
docker volume create "$volume" >/dev/null
docker run --rm -v "$volume:/data" -v "$(cd "$src" && pwd):/src:ro" busybox \
  sh -c 'cp -a /src/. /data/ && chown -R 65532:65532 /data && ls -la /data'
echo "Done. Start the app with: docker compose up -d"
