"""Invariant 9: steering favours rooms you keep from, and never shuts any open room out."""

from __future__ import annotations

import json

from app import store, taste
from app.sources import ROOMS as DEPARTMENTS


def verdicts(conn, room: int, kept: int, passed: int, start: int) -> int:
    for i in range(kept + passed):
        meta = {"room": room, "department": DEPARTMENTS[room]}
        conn.execute(
            "INSERT INTO decision (piece_key, verdict, decided_at, source_meta) VALUES (?, ?, ?, ?)",
            (f"met-{start + i}", "keep" if i < kept else "pass", "2026-11-05T10:00:00Z", json.dumps(meta)),
        )
    return start + kept + passed


def test_invariant_9_steering_favours_kept_rooms_and_never_shuts_one_out(conn):
    n = verdicts(conn, 11, kept=20, passed=30, start=0)  # European Paintings: kept often
    n = verdicts(conn, 9, kept=5, passed=45, start=n)  # Drawings and Prints: sometimes
    verdicts(conn, 14, kept=0, passed=200, start=n)  # Islamic Art: never

    paintings, prints, islamic, unseen = taste.room_weights(conn, [11, 9, 14, 6])

    assert paintings > prints > islamic
    assert islamic >= taste.FLOOR - 1e-9
    assert unseen > islamic  # a room not yet tried isn't punished for it
    assert abs(paintings + prints + islamic + unseen - 1) < 1e-9


def test_older_pieces_are_matched_to_their_room_by_department_name(conn):
    # Records name the Lehman room without its "The"; switching rooms must not drop them.
    from app import images

    from .conftest import jpeg

    meta = {"department": "Robert Lehman Collection", "classification": "Drawings", "object_name": "Drawing"}
    store.add_candidate(conn, "met-1", meta, images.prepare(jpeg()))

    store.set_rooms(conn, [15, 11])

    assert [p["key"] for p in store.take_candidates(conn, 10, set())] == ["met-1"]


def test_invariant_11_what_tagging_cost_is_never_forgotten(conn):
    from app.schemas import Decision

    from .conftest import add_candidate, meta

    key = add_candidate(conn, 1)
    store.record_decisions(conn, [Decision(key=key, verdict="keep", decided_at="2026-11-05T10:00:00Z", meta=meta(1))])
    store.save_tags(conn, key, {}, "", "claude-opus-5-5", 0.02)
    store.save_tags(conn, key, {}, "", "claude-opus-5-5", 0.03)  # tagged again after a retry

    # Then let go: the piece goes, the money spent on it doesn't.
    store.record_decisions(conn, [Decision(key=key, verdict="pass", decided_at="2026-11-05T11:00:00Z", meta=meta(1))])

    assert store.hoard(conn) == []
    assert store.spend(conn)["total_usd"] == 0.05
