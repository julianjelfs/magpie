"""Everything Magpie reads and writes in SQLite: candidates, verdicts, the hoard, rooms."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import images
from .met import is_picture, room_of
from .sources import DEFAULT_ROOMS, ROOMS
from .schemas import Decision

FACETS = ["period", "movement", "region", "medium", "technique", "subject"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- rooms


def rooms(conn: sqlite3.Connection) -> list[int]:
    row = conn.execute("SELECT value FROM preference WHERE key = 'rooms'").fetchone()
    if not row:
        return list(DEFAULT_ROOMS)
    return [r for r in json.loads(row["value"]) if r in ROOMS]


def sculpture(conn: sqlite3.Connection) -> bool:
    """Whether sculpture is offered alongside pictures. Off unless switched on."""
    row = conn.execute("SELECT value FROM preference WHERE key = 'sculpture'").fetchone()
    return bool(row and json.loads(row["value"]))


def _set(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO preference (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def set_rooms(conn: sqlite3.Connection, enabled: list[int], with_sculpture: bool | None = None) -> list[Path]:
    """Save what to draw from. Drops waiting candidates that no longer fit."""
    _set(conn, "rooms", [r for r in dict.fromkeys(enabled) if r in ROOMS])
    if with_sculpture is not None:
        _set(conn, "sculpture", with_sculpture)
    return prune_candidates(conn)


def prune_candidates(conn: sqlite3.Connection) -> list[Path]:
    """Drop waiting candidates from closed rooms, or that aren't pictures. Returns their files."""
    open_rooms = set(rooms(conn))
    with_sculpture = sculpture(conn)
    stale = []
    for row in conn.execute("SELECT piece_key, meta FROM candidate WHERE served_at IS NULL").fetchall():
        meta = json.loads(row["meta"])
        fits = is_picture(meta.get("classification", ""), meta.get("object_name", ""), with_sculpture)
        if room_of(meta) not in open_rooms or not fits:
            stale.append(row["piece_key"])
    for key in stale:
        conn.execute("DELETE FROM candidate WHERE piece_key = ?", (key,))
    return [images.candidate_path(k) for k in stale]


# ---------------------------------------------------------------- candidates


def known_keys(conn: sqlite3.Connection) -> set[str]:
    """Keys that must not be prepared again: decided, or already waiting."""
    decided = {r[0] for r in conn.execute("SELECT piece_key FROM decision")}
    waiting = {r[0] for r in conn.execute("SELECT piece_key FROM candidate")}
    return decided | waiting


def unserved_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT count(*) FROM candidate WHERE served_at IS NULL").fetchone()[0]


def add_candidate(conn: sqlite3.Connection, key: str, meta: dict, prepared: images.Prepared) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO candidate (piece_key, meta, wall_colour, width, height, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (key, json.dumps(meta), prepared.wall_colour, prepared.width, prepared.height, now_iso()),
    )


def _candidate_out(row: sqlite3.Row) -> dict:
    return {
        "key": row["piece_key"],
        **json.loads(row["meta"]),
        "wall_colour": row["wall_colour"],
        "width": row["width"],
        "height": row["height"],
        "image": f"/api/art/{row['piece_key']}/image",
    }


def take_candidates(conn: sqlite3.Connection, count: int, exclude: set[str]) -> list[dict]:
    """Hand out up to count waiting pieces, never one with a verdict or in exclude.

    Unseen pieces first. A piece handed out before but never decided (a device lost
    its queue) comes round again once the unseen ones run out.
    """
    rows = conn.execute(
        """
        SELECT c.* FROM candidate c
        LEFT JOIN decision d ON d.piece_key = c.piece_key
        WHERE d.piece_key IS NULL
        ORDER BY c.served_at IS NOT NULL, c.served_at, c.created_at
        """
    ).fetchall()
    chosen = [r for r in rows if r["piece_key"] not in exclude][:count]
    stamp = now_iso()
    for row in chosen:
        conn.execute("UPDATE candidate SET served_at = ? WHERE piece_key = ?", (stamp, row["piece_key"]))
    return [_candidate_out(r) for r in chosen]


# ---------------------------------------------------------------- verdicts


def record_decisions(conn: sqlite3.Connection, decisions: list[Decision]) -> tuple[list[str], list[Path]]:
    """Store verdicts from a device. Returns the keys applied and files now unwanted.

    Safe to replay: a device that lost its connection mid-send sends the same batch
    again. Last write wins by the time the verdict was given, not the time it arrived,
    so a stale verdict queued on a device that was offline can't undo a newer one.
    """
    applied: list[str] = []
    unwanted: list[Path] = []
    for d in decisions:
        if not images.valid_key(d.key):
            continue
        existing = conn.execute(
            "SELECT verdict, decided_at FROM decision WHERE piece_key = ?", (d.key,)
        ).fetchone()
        if existing and _instant(existing["decided_at"]) > _instant(d.decided_at):
            continue

        candidate = conn.execute("SELECT * FROM candidate WHERE piece_key = ?", (d.key,)).fetchone()
        meta = json.loads(candidate["meta"]) if candidate else dict(d.meta)
        conn.execute(
            "INSERT INTO decision (piece_key, verdict, decided_at, source_meta) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (piece_key) DO UPDATE SET verdict = excluded.verdict, "
            "decided_at = excluded.decided_at, source_meta = excluded.source_meta",
            (d.key, d.verdict, d.decided_at, json.dumps(meta)),
        )

        if d.verdict == "keep":
            conn.execute(
                "INSERT OR IGNORE INTO piece (piece_key, meta, wall_colour, width, height, kept_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    d.key,
                    json.dumps(meta),
                    candidate["wall_colour"] if candidate else (d.wall_colour or "#2b3033"),
                    candidate["width"] if candidate else d.width,
                    candidate["height"] if candidate else d.height,
                    d.decided_at,
                ),
            )
            # The candidate image stays on disk; the worker moves it into the hoard.
        else:
            if conn.execute("DELETE FROM piece WHERE piece_key = ?", (d.key,)).rowcount:
                unwanted += [images.hoard_path(d.key), images.thumb_path(d.key)]
            unwanted.append(images.candidate_path(d.key))
        conn.execute("DELETE FROM candidate WHERE piece_key = ?", (d.key,))
        applied.append(d.key)
    return applied, unwanted


# ---------------------------------------------------------------- the hoard


def _piece_out(row: sqlite3.Row, tags: dict[str, list[str]]) -> dict:
    key = row["piece_key"]
    return {
        "key": key,
        **json.loads(row["meta"]),
        "wall_colour": row["wall_colour"],
        "width": row["width"],
        "height": row["height"],
        "kept_at": row["kept_at"],
        "image_status": row["image_status"],
        "tag_status": row["tag_status"],
        "tag_error": row["tag_error"],
        "note": row["note"],
        "tags": {f: tags.get(f, []) for f in FACETS},
        "image": f"/api/art/{key}/image",
        "thumb": f"/api/art/{key}/thumb",
    }


def hoard(conn: sqlite3.Connection) -> list[dict]:
    tags: dict[str, dict[str, list[str]]] = {}
    for t in conn.execute("SELECT piece_key, facet, value FROM tag ORDER BY rowid"):
        tags.setdefault(t["piece_key"], {}).setdefault(t["facet"], []).append(t["value"])
    rows = conn.execute("SELECT * FROM piece ORDER BY kept_at DESC").fetchall()
    return [_piece_out(r, tags.get(r["piece_key"], {})) for r in rows]


def piece(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM piece WHERE piece_key = ?", (key,)).fetchone()


def vocabulary(conn: sqlite3.Connection, per_facet: int = 80) -> dict[str, list[str]]:
    """The tags already in use, commonest first, so Claude reuses them."""
    out: dict[str, list[str]] = {f: [] for f in FACETS}
    for row in conn.execute(
        "SELECT facet, value, count(*) AS n FROM tag GROUP BY facet, value ORDER BY n DESC, value"
    ):
        if row["facet"] in out and len(out[row["facet"]]) < per_facet:
            out[row["facet"]].append(row["value"])
    return out


def save_tags(
    conn: sqlite3.Connection, key: str, tags: dict[str, list[str]], note: str, model: str, cost: float | None
) -> None:
    conn.execute("DELETE FROM tag WHERE piece_key = ?", (key,))
    for facet in FACETS:
        for value in dict.fromkeys(v.strip() for v in tags.get(facet, []) if v.strip()):
            conn.execute("INSERT OR IGNORE INTO tag (piece_key, facet, value) VALUES (?, ?, ?)", (key, facet, value))
    conn.execute(
        "UPDATE piece SET tag_status = 'tagged', tag_error = NULL, note = ?, tag_model = ?, tag_cost_usd = ? "
        "WHERE piece_key = ?",
        (note, model, cost, key),
    )


def retry(conn: sqlite3.Connection, key: str) -> bool:
    row = piece(conn, key)
    if not row:
        return False
    conn.execute(
        "UPDATE piece SET "
        "image_status = CASE image_status WHEN 'failed' THEN 'pending' ELSE image_status END, "
        "tag_status = CASE tag_status WHEN 'failed' THEN 'pending' ELSE tag_status END, "
        "tag_error = NULL WHERE piece_key = ?",
        (key,),
    )
    return True


def heal_missing_images(conn: sqlite3.Connection) -> int:
    """Send pieces whose picture has gone from disk back to be fetched again.

    The nightly backup holds the database, not the pictures: after a restore onto a new
    card, every kept piece is re-fetched from the museum this way.
    """
    lost = [
        r["piece_key"]
        for r in conn.execute("SELECT piece_key FROM piece WHERE image_status = 'ready'")
        if not images.hoard_path(r["piece_key"]).exists()
    ]
    for key in lost:
        conn.execute("UPDATE piece SET image_status = 'pending' WHERE piece_key = ?", (key,))
    return len(lost)
