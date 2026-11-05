"""Print the hoard's numbers for `magpie status`. Runs on the Pi with the system Python."""

import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "magpie/backend/magpie.db")
if not path.exists():
    print("hoard      : no database yet")
    raise SystemExit
c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def q(sql: str):
    return c.execute(sql).fetchone()[0]


kept = q("select count(*) from piece")
passed = q("select count(*) from decision where verdict = 'pass'")
ready = q("select count(*) from candidate where served_at is null")
to_tag = q("select count(*) from piece where tag_status = 'pending'")
failed = q("select count(*) from piece where tag_status = 'failed' or image_status = 'failed'")
spent = q("select coalesce(sum(tag_cost_usd), 0) from piece")

print(f"hoard      : {kept} kept, {passed} passed")
print(f"waiting    : {ready} pieces ready, {to_tag} to tag, {failed} failed")
print(f"claude     : ${spent:.2f} spent on tagging")
