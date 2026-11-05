#!/usr/bin/env bash
# Install (or re-install) Magpie on the Pi. Run it ON the Pi:
#
#   cd ~/magpie && ./deploy/install-pi.sh
#
# Safe to re-run: never touches the database, the pictures or backend/.env. It does not
# build the frontend (that happens on the laptop, via `magpie rebuild`) and it does not
# configure Caddy: one Caddyfile serves every app and it lives in the recipe-for-disaster repo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$(id -un)" = root ] && { echo "run this as your normal user, not root" >&2; exit 1; }

echo "==> backend dependencies"
"$HOME/.local/bin/uv" --version >/dev/null 2>&1 || { echo "uv is not installed: https://astral.sh/uv" >&2; exit 1; }
(cd "$ROOT/backend" && "$HOME/.local/bin/uv" sync -q --no-dev)

[ -f "$ROOT/backend/.env" ] || echo "warning: no backend/.env, so kept pieces won't be tagged until ANTHROPIC_API_KEY is set" >&2

echo "==> systemd units"
sudo cp "$ROOT/deploy/magpie.service" /etc/systemd/system/magpie.service
sudo cp "$ROOT/deploy/magpie-backup.service" /etc/systemd/system/magpie-backup.service
sudo cp "$ROOT/deploy/magpie-backup.timer" /etc/systemd/system/magpie-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable magpie.service >/dev/null
sudo systemctl restart magpie.service
sudo systemctl enable --now magpie-backup.timer >/dev/null

echo "==> waiting for the app"
for _ in $(seq 1 40); do
	curl -sf -m 1 http://127.0.0.1:8060/api/health >/dev/null && break
	sleep 0.5
done
curl -sf -m 3 http://127.0.0.1:8060/api/health >/dev/null \
	|| { echo "the app did not come up; see: sudo journalctl -u magpie -n 50" >&2; exit 1; }

echo
echo "installed."
printf "  app        : %s\n" "$(systemctl is-active magpie)"
printf "  next backup: %s\n" "$(systemctl list-timers magpie-backup --no-pager 2>/dev/null | awk 'NR==2 {print $1, $2, $3}')"
