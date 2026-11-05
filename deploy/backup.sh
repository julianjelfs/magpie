#!/usr/bin/env bash
# Nightly snapshot of the Magpie database, taken on the Pi.
#
# Pictures are not backed up: every kept piece records its museum image URL, and Magpie
# fetches any missing picture again when it starts.
set -euo pipefail

DB="${MAGPIE_DB_PATH:-/home/julian_jelfs/magpie/backend/magpie.db}"
DEST="${MAGPIE_BACKUP_DIR:-/home/julian_jelfs/magpie-backups}"
KEEP=14

mkdir -p "$DEST"
out="$DEST/magpie-$(date +%Y%m%d-%H%M%S).db"

# SQLite's online backup API copies a consistent snapshot while uvicorn keeps serving.
# `cp` would catch a half-written page and give us a file that only looks like a backup.
python3 - "$DB" "$out" <<'PY'
import sqlite3
import sys

src, dst = sys.argv[1], sys.argv[2]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
target = sqlite3.connect(dst)
with target:
    source.backup(target)

state = target.execute("PRAGMA integrity_check").fetchone()[0]
tables = target.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
verdicts = target.execute("select count(*) from decision").fetchone()[0] if tables else 0
target.close()
source.close()

if state != "ok":
    raise SystemExit(f"integrity check failed: {state}")
if tables == 0:
    raise SystemExit("backup holds no tables")
print(f"backed up {verdicts} verdicts")
PY

echo "wrote $out ($(du -h "$out" | cut -f1))"
ls -1t "$DEST"/magpie-*.db 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "keeping $(ls -1 "$DEST"/magpie-*.db 2>/dev/null | wc -l | tr -d ' ') backups in $DEST"
