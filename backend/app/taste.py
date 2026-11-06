"""What the verdicts say: keep rates by room, century and kind, and how picks are steered.

Steering is by room, and by how often picks come from the Met's highlights. Both cost
nothing extra to act on. A room's weight is its keep rate, smoothed towards the overall
keep rate so that a room seen twice and kept once doesn't leap to the top, and no open
room falls below FLOOR of the picks, so the feed never closes in on one corner of the
museum.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict

from . import store
from .met import HIGHLIGHT_SHARE, room_of
from .sources import ROOMS

# Pseudo-verdicts at the overall keep rate added to every group before comparing.
PRIOR_STRENGTH = 10
# Every open room gets at least this share of picks.
FLOOR = 0.05
# Bounds on the share of picks drawn from highlights.
HIGHLIGHTS_MIN, HIGHLIGHTS_MAX = 0.10, 0.40


def _verdicts(conn: sqlite3.Connection) -> list[tuple[bool, dict]]:
    return [(v == "keep", json.loads(m)) for v, m in conn.execute("SELECT verdict, source_meta FROM decision")]


def _smoothed(kept: int, seen: int, base: float) -> float:
    return (kept + PRIOR_STRENGTH * base) / (seen + PRIOR_STRENGTH)


def _base(verdicts: list[tuple[bool, dict]]) -> float:
    if not verdicts:
        return 0.1
    # Never exactly zero, or every room would tie at nothing.
    return max(sum(k for k, _ in verdicts) / len(verdicts), 0.01)


def room_weights(conn: sqlite3.Connection, rooms: list[int]) -> list[float]:
    """One weight per room, in order, summing to 1, none below FLOOR."""
    if not rooms:
        return []
    verdicts = _verdicts(conn)
    base = _base(verdicts)
    tally: dict[int | None, list[int]] = defaultdict(lambda: [0, 0])
    for kept, meta in verdicts:
        tally[room_of(meta)][0] += kept
        tally[room_of(meta)][1] += 1
    raw = [_smoothed(*tally[r], base) for r in rooms]
    return with_floor(raw, FLOOR)


def with_floor(raw: list[float], floor: float) -> list[float]:
    """Normalise to sum to 1, lifting any share below floor and taking it from the rest."""
    n = len(raw)
    floor = min(floor, 1 / n)
    total = sum(raw) or 1.0
    shares = [w / total for w in raw]
    lifted = [False] * n
    while True:
        low = [i for i, s in enumerate(shares) if s < floor - 1e-12 and not lifted[i]]
        if not low:
            return shares
        for i in low:
            lifted[i] = True
        free = 1 - floor * sum(lifted)
        rest = sum(raw[i] for i in range(n) if not lifted[i]) or 1.0
        shares = [floor if lifted[i] else free * raw[i] / rest for i in range(n)]


def highlight_share(conn: sqlite3.Connection) -> float:
    """More picks from the highlights if you keep more of them than of the rest."""
    verdicts = _verdicts(conn)
    if len(verdicts) < 30:
        return HIGHLIGHT_SHARE
    base = _base(verdicts)
    h = [k for k, m in verdicts if m.get("highlight")]
    o = [k for k, m in verdicts if not m.get("highlight")]
    hr, orate = _smoothed(sum(h), len(h), base), _smoothed(sum(o), len(o), base)
    share = HIGHLIGHT_SHARE * hr / (HIGHLIGHT_SHARE * hr + (1 - HIGHLIGHT_SHARE) * orate)
    return min(max(share, HIGHLIGHTS_MIN), HIGHLIGHTS_MAX)


def _century(meta: dict) -> str:
    year = meta.get("begin_year")
    if year is None:
        return "Undated"
    if year <= 0:
        return "Before 1 CE"
    c = (year - 1) // 100 + 1
    suffix = "th" if 10 <= c % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(c % 10, "th")
    return f"{c}{suffix} century"


def _kind(meta: dict) -> str:
    classification = meta.get("classification") or ""
    return classification.split("|")[0].split("-")[0].strip() or "Unclassified"


def _breakdown(verdicts, key, limit: int = 10) -> list[dict]:
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for kept, meta in verdicts:
        tally[key(meta)][0] += kept
        tally[key(meta)][1] += 1
    rows = [{"name": k, "kept": kept, "seen": seen} for k, (kept, seen) in tally.items()]
    rows.sort(key=lambda r: (-r["seen"], r["name"]))
    return rows[:limit]


def summary(conn: sqlite3.Connection, open_rooms: list[int]) -> dict:
    verdicts = _verdicts(conn)
    room_name = lambda m: ROOMS.get(room_of(m) or 0, m.get("department") or "Unknown")  # noqa: E731
    artists = Counter(m.get("artist") for kept, m in verdicts if kept and m.get("artist"))
    weights = room_weights(conn, open_rooms)
    return {
        "seen": len(verdicts),
        "kept": sum(k for k, _ in verdicts),
        "rooms": _breakdown(verdicts, room_name),
        "centuries": _breakdown(verdicts, _century),
        "kinds": _breakdown(verdicts, _kind),
        "highlights": _breakdown(verdicts, lambda m: "Met highlights" if m.get("highlight") else "Everything else"),
        "artists": [{"name": a, "kept": n} for a, n in artists.most_common(8) if n > 1],
        "steering": {
            "rooms": sorted(
                ({"name": ROOMS[r], "share": round(w, 3)} for r, w in zip(open_rooms, weights)),
                key=lambda r: -r["share"],
            ),
            "highlights": round(highlight_share(conn), 3),
        },
        "spend": store.spend(conn),
    }
