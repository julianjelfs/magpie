#!/usr/bin/env bash
# Run the API and the Vite dev server together. Ctrl-C stops both.
# The API reads backend/.env for ANTHROPIC_API_KEY; without it, kept pieces wait untagged.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

env_file=()
[ -f "$root/backend/.env" ] && env_file=(--env-file "$root/backend/.env")

(cd "$root/backend" && uv run "${env_file[@]}" uvicorn app.main:app --reload --port 8060) &
(cd "$root/frontend" && npm run dev) &

wait
