"""SQLite connection handling and schema management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
-- Every verdict ever given, keep or pass. A piece with a row here is never
-- offered again. source_meta is the museum's description at the time, kept
-- for passes too so they can steer what comes next one day.
CREATE TABLE IF NOT EXISTS decision (
    piece_key   TEXT PRIMARY KEY,           -- e.g. met-436535
    verdict     TEXT NOT NULL CHECK (verdict IN ('keep', 'pass')),
    decided_at  TEXT NOT NULL,              -- ISO 8601 UTC, from the device
    source_meta TEXT NOT NULL               -- JSON
);

-- The hoard: one row per kept piece.
CREATE TABLE IF NOT EXISTS piece (
    piece_key     TEXT PRIMARY KEY REFERENCES decision(piece_key) ON DELETE CASCADE,
    meta          TEXT NOT NULL,            -- JSON, the museum's description
    wall_colour   TEXT NOT NULL,
    width         INTEGER,
    height        INTEGER,
    kept_at       TEXT NOT NULL,
    image_status  TEXT NOT NULL DEFAULT 'pending' CHECK (image_status IN ('pending', 'ready', 'failed')),
    tag_status    TEXT NOT NULL DEFAULT 'pending' CHECK (tag_status IN ('pending', 'tagged', 'failed')),
    tag_error     TEXT,
    note          TEXT,                     -- what Claude says is worth looking at
    tag_model     TEXT,
    tag_cost_usd  REAL
);

CREATE TABLE IF NOT EXISTS tag (
    piece_key TEXT NOT NULL REFERENCES piece(piece_key) ON DELETE CASCADE,
    facet     TEXT NOT NULL,
    value     TEXT NOT NULL,
    PRIMARY KEY (piece_key, facet, value)
);
CREATE INDEX IF NOT EXISTS tag_by_facet ON tag (facet, value);

-- Pieces fetched and prepared ahead of time, so the next one is instant.
-- served_at is set once a device has been handed the piece.
CREATE TABLE IF NOT EXISTS candidate (
    piece_key   TEXT PRIMARY KEY,
    meta        TEXT NOT NULL,
    wall_colour TEXT NOT NULL,
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    served_at   TEXT
);

-- One row per preference. A missing key means the default.
CREATE TABLE IF NOT EXISTS preference (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or config.database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI runs sync endpoints on a threadpool, and not always on the same
    # thread, so the same-thread guard has to come off. Each request still gets
    # its own connection, used by one thread at a time.
    conn = sqlite3.connect(target, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialise(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Transactional connection; commits on success, rolls back on error."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
