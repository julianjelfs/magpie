"""Invariants 1–4: what a verdict does, and what it must never do."""

from __future__ import annotations

from app import images, store
from app.schemas import Decision

from .conftest import add_candidate, meta


def verdict(key: str, v: str, at: str) -> Decision:
    return Decision(key=key, verdict=v, decided_at=at, meta=meta(int(key.split("-")[1])))


def test_invariant_1_a_piece_with_a_verdict_is_never_offered_again(conn):
    kept, passed, fresh = (add_candidate(conn, n) for n in (1, 2, 3))
    store.take_candidates(conn, 10, set())  # all three handed to a device once

    store.record_decisions(conn, [verdict(kept, "keep", "2026-11-05T10:00:00Z"), verdict(passed, "pass", "2026-11-05T10:00:01Z")])

    offered = [p["key"] for p in store.take_candidates(conn, 10, set())]
    assert offered == [fresh]
    # And the worker won't fetch them again either.
    assert {kept, passed} <= store.known_keys(conn)


def test_invariant_2_a_stale_verdict_never_undoes_a_newer_one(conn):
    key = add_candidate(conn, 1)
    store.record_decisions(conn, [verdict(key, "keep", "2026-11-05T12:00:00Z")])

    # A phone that was offline sends a pass it made an hour earlier.
    applied, _ = store.record_decisions(conn, [verdict(key, "pass", "2026-11-05T11:00:00+00:00")])

    assert applied == []
    assert [p["key"] for p in store.hoard(conn)] == [key]


def test_invariant_3_replaying_a_batch_changes_nothing(conn):
    key = add_candidate(conn, 1)
    batch = [verdict(key, "keep", "2026-11-05T10:00:00Z"), verdict("met-2", "pass", "2026-11-05T10:00:05Z")]

    store.record_decisions(conn, batch)
    before = store.hoard(conn)
    store.record_decisions(conn, batch)

    assert store.hoard(conn) == before
    assert conn.execute("SELECT count(*) FROM decision").fetchone()[0] == 2


def test_invariant_4_letting_go_removes_the_piece_and_its_files(conn):
    key = add_candidate(conn, 1)
    store.record_decisions(conn, [verdict(key, "keep", "2026-11-05T10:00:00Z")])
    for path in (images.hoard_path(key), images.thumb_path(key)):
        images.write(path, b"jpeg")

    _, unwanted = store.record_decisions(conn, [verdict(key, "pass", "2026-11-05T10:05:00Z")])

    assert store.hoard(conn) == []
    assert images.hoard_path(key) in unwanted and images.thumb_path(key) in unwanted
