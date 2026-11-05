"""The background loop: keep a few pieces ready, and finish off kept ones.

Kept pieces move through two steps, each recorded on the piece row so a restart picks up
where it left off: the image goes into the hoard (with a thumbnail), then Claude tags it.
A step that fails is marked failed and waits for the retry button, so a bad piece can't
burn API calls in a loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Protocol

from . import config, db, images, store
from .met import Draft
from .tagger import Tagger, TagError

log = logging.getLogger(__name__)


class Source(Protocol):
    async def random_draft(self, rooms: list[int], skip: set[str]) -> Draft | None: ...
    async def download(self, url: str) -> bytes: ...


def remove_files(paths) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


class Worker:
    def __init__(self, source: Source, tagger: Tagger | None, session: Callable = db.session):
        self.source = source
        self.tagger = tagger
        self.session = session
        self.wake = asyncio.Event()

    def poke(self) -> None:
        self.wake.set()

    async def run(self) -> None:
        while True:
            try:
                await self.finish_hoard()
                await self.top_up()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("worker pass failed")
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=60)
            except TimeoutError:
                pass
            self.wake.clear()

    # ------------------------------------------------------------ candidates

    async def top_up(self) -> None:
        misses = 0
        while misses < 3:
            with self.session() as conn:
                if store.unserved_count(conn) >= config.CANDIDATE_BUFFER:
                    return
                rooms = store.rooms(conn)
                skip = store.known_keys(conn)
            if await self.prepare_one(rooms, skip):
                misses = 0
            else:
                misses += 1
            # Finish kept pieces between candidates, so a keep never waits for a full buffer.
            await self.finish_hoard()

    async def prepare_one(self, rooms: list[int], skip: set[str]) -> bool:
        try:
            draft = await self.source.random_draft(rooms, skip)
            if not draft:
                return False
            raw = await self.source.download(draft.image_url)
            prepared = await asyncio.to_thread(images.prepare, raw)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("could not prepare a candidate: %s", e)
            return False
        images.write(images.candidate_path(draft.key), prepared.jpeg)
        with self.session() as conn:
            store.add_candidate(conn, draft.key, draft.meta, prepared)
        log.info("ready: %s %s", draft.key, draft.meta.get("title"))
        return True

    # ------------------------------------------------------------ the hoard

    async def finish_hoard(self) -> None:
        with self.session() as conn:
            need_image = [
                (r["piece_key"], json.loads(r["meta"]))
                for r in conn.execute("SELECT piece_key, meta FROM piece WHERE image_status = 'pending'")
            ]
        for key, meta in need_image:
            await self.store_image(key, meta)

        if not self.tagger:
            return
        with self.session() as conn:
            need_tags = [
                (r["piece_key"], json.loads(r["meta"]))
                for r in conn.execute(
                    "SELECT piece_key, meta FROM piece WHERE image_status = 'ready' AND tag_status = 'pending'"
                )
            ]
        for key, meta in need_tags:
            await self.tag(key, meta)

    async def store_image(self, key: str, meta: dict) -> None:
        target = images.hoard_path(key)
        try:
            candidate = images.candidate_path(key)
            if candidate.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                candidate.replace(target)
            elif not target.exists():
                raw = await self.source.download(meta["image_url"])
                prepared = await asyncio.to_thread(images.prepare, raw)
                images.write(target, prepared.jpeg)
            thumb = await asyncio.to_thread(images.resized, target, config.THUMB_EDGE, 78)
            images.write(images.thumb_path(key), thumb)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("could not store the image for %s: %s", key, e)
            with self.session() as conn:
                conn.execute(
                    "UPDATE piece SET image_status = 'failed', tag_error = ? WHERE piece_key = ?",
                    ("Couldn't fetch the image from the museum.", key),
                )
            return
        with self.session() as conn:
            # The piece may have been let go while the image was on its way.
            if conn.execute("UPDATE piece SET image_status = 'ready' WHERE piece_key = ?", (key,)).rowcount == 0:
                remove_files([target, images.thumb_path(key)])

    async def tag(self, key: str, meta: dict) -> None:
        assert self.tagger
        with self.session() as conn:
            vocabulary = store.vocabulary(conn)
        try:
            jpeg = await asyncio.to_thread(images.resized, images.hoard_path(key), config.CLAUDE_EDGE)
            result = await self.tagger.tag(meta, jpeg, vocabulary)
        except asyncio.CancelledError:
            raise
        except TagError as e:
            error = str(e)
        except Exception as e:
            log.exception("tagging %s failed", key)
            error = f"Tagging failed: {e}"
        else:
            with self.session() as conn:
                if store.piece(conn, key):
                    store.save_tags(conn, key, result.tags, result.note, result.model, result.cost_usd)
            log.info("tagged %s (%s)", key, result.cost_usd)
            return
        with self.session() as conn:
            conn.execute(
                "UPDATE piece SET tag_status = 'failed', tag_error = ? WHERE piece_key = ?", (error, key)
            )
