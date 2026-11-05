"""Invariant 5: a keep is never lost because tagging failed."""

from __future__ import annotations

import asyncio

from app import db, images, store
from app.schemas import Decision
from app.tagger import Tags, TagError
from app.worker import Worker

from .conftest import FakeSource, add_candidate, meta


class FailingTagger:
    async def tag(self, meta, jpeg, vocabulary):
        raise TagError("Claude returned an error (529).")


class WorkingTagger:
    def __init__(self):
        self.vocabularies = []

    async def tag(self, meta, jpeg, vocabulary):
        self.vocabularies.append(vocabulary)
        return Tags(tags={"movement": ["Ukiyo-e"], "subject": ["Birds"]}, note="Look at the diagonal.", model="m", cost_usd=0.01)


def test_invariant_5_a_keep_survives_failed_tagging_and_can_be_retried(conn):
    key = add_candidate(conn, 1)
    store.record_decisions(conn, [Decision(key=key, verdict="keep", decided_at="2026-11-05T10:00:00Z", meta=meta(1))])
    conn.commit()

    asyncio.run(Worker(FakeSource(), FailingTagger()).finish_hoard())

    with db.session() as c:
        [piece] = store.hoard(c)
        assert piece["key"] == key
        assert piece["image_status"] == "ready"
        assert piece["tag_status"] == "failed"
        assert "529" in piece["tag_error"]
        store.retry(c, key)

    asyncio.run(Worker(FakeSource(), WorkingTagger()).finish_hoard())

    with db.session() as c:
        [piece] = store.hoard(c)
        assert piece["tag_status"] == "tagged"
        assert piece["tags"]["movement"] == ["Ukiyo-e"]
        assert piece["note"] == "Look at the diagonal."


def test_a_kept_piece_whose_candidate_image_is_gone_is_fetched_again(conn):
    # Keeps made offline can arrive after the Pi has dropped the candidate.
    store.record_decisions(conn, [Decision(key="met-7", verdict="keep", decided_at="2026-11-05T10:00:00Z", meta=meta(7))])
    conn.commit()

    asyncio.run(Worker(FakeSource(), WorkingTagger()).finish_hoard())

    with db.session() as c:
        [piece] = store.hoard(c)
        assert piece["image_status"] == "ready"
        assert piece["tag_status"] == "tagged"


def test_the_worker_fills_the_candidate_buffer():
    worker = Worker(FakeSource(), None)
    asyncio.run(worker.top_up())
    with db.session() as c:
        assert store.unserved_count(c) >= 8


def test_invariant_7_a_kept_piece_whose_picture_is_lost_is_fetched_again(conn):
    # The backup holds the database, not the pictures. After a restore, every kept
    # piece must come back with its picture.
    key = add_candidate(conn, 1)
    store.record_decisions(conn, [Decision(key=key, verdict="keep", decided_at="2026-11-05T10:00:00Z", meta=meta(1))])
    conn.commit()
    asyncio.run(Worker(FakeSource(), WorkingTagger()).finish_hoard())
    images.hoard_path(key).unlink()

    with db.session() as c:
        assert store.heal_missing_images(c) == 1
    asyncio.run(Worker(FakeSource(), WorkingTagger()).finish_hoard())

    assert images.hoard_path(key).exists()
