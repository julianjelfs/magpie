"""What the verdicts say: keep rates by room, century and kind, and how picks are steered.

Steering works at three levels, each with a limit so the feed never closes in on one
corner of one museum.

- The room. A room's weight is its keep rate, smoothed towards the overall keep rate so
  that a room seen twice and kept once doesn't leap to the top. No open room falls below
  FLOOR of the picks.
- The piece within a room. A steered pick draws DRAWS pieces and chooses between them by
  score: how often you keep pieces with the same artist, century, kind, culture, school
  and subjects. A score is never below SCORE_MIN or above SCORE_MAX, so nothing is out of
  reach, and anything not seen before scores a neutral 1.
- The artist. An artist kept twice or more, at a better rate than you keep things in
  general, is followed: FOLLOW of picks go looking for more by one of them, in every
  source. An artist whose last DROP_AFTER pieces you passed is dropped.

EXPLORE of picks are open: a random piece from the room, taste ignored. Each piece
records how it was picked, so the taste page can show whether steering earns its place.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from . import store
from .met import HIGHLIGHT_SHARE, room_of
from .sources import ROOMS
from .wikidata import ARTISTS

# Pseudo-verdicts at the overall keep rate added to every group before comparing.
PRIOR_STRENGTH = 10
# Every open room gets at least this share of picks.
FLOOR = 0.05
# Bounds on the share of picks drawn from highlights.
HIGHLIGHTS_MIN, HIGHLIGHTS_MAX = 0.10, 0.40
# The share of picks that ignore taste within the room.
EXPLORE = 0.30
# The share of picks that look for more by a followed artist.
FOLLOW = 0.15
FOLLOWED_MAX = 20
# A followed artist is dropped once this many of their pieces in a row are passed.
DROP_AFTER = 8
# How many pieces a steered pick chooses between.
DRAWS = 3
# How far one trait (an artist, a century) can move a score, and how far a score can go.
FACTOR_MIN, FACTOR_MAX = 1 / 3, 3.0
SCORE_MIN, SCORE_MAX = 0.2, 5.0

PICKS = {"open": "Open picks", "steered": "Steered picks", "artist": "Followed artists"}
SOURCES = {"met": "The Met", "wikidata": "Wikimedia Commons", "cleveland": "Cleveland", "smk": "SMK Copenhagen"}
GROUP_OF_ARTIST = {a["name"]: a.get("group", "") for a in ARTISTS}


def _verdicts(conn: sqlite3.Connection) -> list[tuple[bool, dict]]:
    return [(v == "keep", json.loads(m)) for v, m in conn.execute("SELECT verdict, source_meta FROM decision ORDER BY decided_at")]


def _smoothed(kept: int, seen: int, base: float) -> float:
    return (kept + PRIOR_STRENGTH * base) / (seen + PRIOR_STRENGTH)


def _base(verdicts: list[tuple[bool, dict]]) -> float:
    if not verdicts:
        return 0.1
    # Never exactly zero, or every room would tie at nothing.
    return max(sum(k for k, _ in verdicts) / len(verdicts), 0.01)


def room_weights(conn: sqlite3.Connection, rooms: list[int]) -> list[float]:
    """One weight per room, in order, summing to 1, none below FLOOR."""
    return _room_weights(_verdicts(conn), rooms)


def _room_weights(verdicts: list[tuple[bool, dict]], rooms: list[int]) -> list[float]:
    if not rooms:
        return []
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
    return _highlight_share(_verdicts(conn))


def _highlight_share(verdicts: list[tuple[bool, dict]]) -> float:
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


def _artist(meta: dict) -> str:
    """The maker, if the record names a person rather than "Anonymous, French, 18th century"."""
    name = (meta.get("artist") or "").strip()
    return "" if name.lower().startswith(("anonymous", "unidentified", "unknown", "ubekendt")) else name


def traits(meta: dict) -> dict[str, list[str]]:
    """What a museum record says about a piece that taste might turn on."""
    artist = _artist(meta)
    out = {
        "artist": [artist],
        "century": [_century(meta)] if meta.get("begin_year") is not None else [],
        "kind": [_kind(meta)] if meta.get("classification") else [],
        "culture": [(meta.get("culture") or "").split(",")[0].strip()],
        "group": [meta.get("group") or GROUP_OF_ARTIST.get(artist, "")],
        "subject": list(meta.get("subjects") or []),
    }
    return {trait: [v for v in values if v] for trait, values in out.items()}


class Model:
    """Keep rates by trait, and a score for a piece not yet seen."""

    def __init__(self, verdicts: list[tuple[bool, dict]]):
        self.base = _base(verdicts)
        self.tally: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for kept, meta in verdicts:
            for trait, values in traits(meta).items():
                for value in values:
                    self.tally[(trait, value)][0] += kept
                    self.tally[(trait, value)][1] += 1

    def factor(self, trait: str, value: str) -> float:
        """How much more (or less) often than usual you keep pieces with this trait. 1 if unseen."""
        kept, seen = self.tally.get((trait, value), (0, 0))
        return min(max(_smoothed(kept, seen, self.base) / self.base, FACTOR_MIN), FACTOR_MAX)

    def score(self, meta: dict) -> float:
        """Above 1 for a piece like those you keep, below for one like those you pass."""
        log_score = 0.0
        for trait, values in traits(meta).items():
            if values:
                # Several subjects count as one trait, so a busy record isn't louder.
                log_score += sum(math.log(self.factor(trait, v)) for v in values) / len(values)
        return min(max(math.exp(log_score), SCORE_MIN), SCORE_MAX)


def followed(verdicts: list[tuple[bool, dict]]) -> list[str]:
    """Artists kept twice or more, and more often than you keep things in general, until
    their last DROP_AFTER pieces have all been passed. Verdicts come oldest first."""
    base = _base(verdicts)
    history: dict[str, list[bool]] = defaultdict(list)
    for kept, meta in verdicts:
        if artist := _artist(meta):
            history[artist].append(kept)
    names = [
        a
        for a, h in history.items()
        if sum(h) >= 2 and sum(h) / len(h) > base and any(h[-DROP_AFTER:])
    ]
    names.sort(key=lambda a: (-sum(history[a]), a))
    return names[:FOLLOWED_MAX]


def pick_kind(roll: float, following: bool) -> str:
    """How the next piece is picked, from a roll in [0, 1). Open picks come first, so
    nothing else can eat into their share."""
    if roll < EXPLORE:
        return "open"
    if following and roll < EXPLORE + FOLLOW:
        return "artist"
    return "steered"


@dataclass(frozen=True)
class Steer:
    """Everything the worker needs to pick the next piece, worked out from one read."""

    weights: list[float]
    highlight_share: float
    model: Model
    followed: list[str]


def steer(conn: sqlite3.Connection, rooms: list[int]) -> Steer:
    verdicts = _verdicts(conn)
    return Steer(_room_weights(verdicts, rooms), _highlight_share(verdicts), Model(verdicts), followed(verdicts))


def _breakdown(verdicts, key, limit: int = 10) -> list[dict]:
    """Keep counts by key(meta). A key may give several names (subjects) or none."""
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for kept, meta in verdicts:
        names = key(meta)
        for name in [names] if isinstance(names, str) else names:
            tally[name][0] += kept
            tally[name][1] += 1
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
        "subjects": _breakdown(verdicts, lambda m: m.get("subjects") or [], limit=12),
        "sources": _breakdown(verdicts, lambda m: SOURCES.get(m.get("source"), "Unknown")),
        # Only pieces picked since steering began say how they were picked.
        "picks": _breakdown(verdicts, lambda m: [PICKS[m["pick"]]] if m.get("pick") in PICKS else []),
        "artists": [{"name": a, "kept": n} for a, n in artists.most_common(8) if n > 1],
        "steering": {
            "rooms": sorted(
                ({"name": ROOMS[r], "share": round(w, 3)} for r, w in zip(open_rooms, weights)),
                key=lambda r: -r["share"],
            ),
            "highlights": round(highlight_share(conn), 3),
            "open": EXPLORE,
            "follow": FOLLOW,
            "followed": followed(verdicts),
        },
        "spend": store.spend(conn),
    }
