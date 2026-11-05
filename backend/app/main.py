"""Magpie API: serves new pieces, records verdicts, and serves the hoard and the built UI."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, images, store
from .met import DEPARTMENTS, Met
from .schemas import DecisionBatch, Rooms
from .tagger import ClaudeTagger
from .worker import Worker, remove_files

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("magpie")

# Not in every platform's table, and browsers want the right type before they will
# offer to install the app.
mimetypes.add_type("application/manifest+json", ".webmanifest")


def make_worker() -> Worker:
    tagger = ClaudeTagger() if os.environ.get("ANTHROPIC_API_KEY") else None
    if not tagger:
        log.warning("ANTHROPIC_API_KEY is not set: kept pieces will wait, untagged")
    return Worker(Met.create(config.cache_dir()), tagger)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.initialise()
    with db.session() as conn:
        if lost := store.heal_missing_images(conn):
            log.warning("%d kept pictures were missing; fetching them again", lost)
        stale = store.prune_candidates(conn)
    remove_files(stale)
    worker: Worker | None = getattr(app.state, "worker", None)
    task = None
    if worker is None and os.environ.get("MAGPIE_NO_WORKER") != "1":
        worker = make_worker()
        task = asyncio.create_task(worker.run())
    app.state.worker = worker
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Magpie", version="0.1.0", lifespan=lifespan)


def poke() -> None:
    worker = getattr(app.state, "worker", None)
    if worker:
        worker.poke()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/next")
async def next_pieces(count: int = Query(3, ge=1, le=10), exclude: str = "") -> dict:
    """Up to count pieces to look at. Waits a few seconds if none are ready yet."""
    skip = {k for k in exclude.split(",") if k}
    for attempt in range(20):
        with db.session() as conn:
            pieces = store.take_candidates(conn, count, skip)
        poke()
        if pieces or attempt == 19:
            return {"pieces": pieces}
        await asyncio.sleep(0.5)
    return {"pieces": []}


@app.post("/api/decisions")
def decide(batch: DecisionBatch) -> dict:
    with db.session() as conn:
        applied, unwanted = store.record_decisions(conn, batch.decisions)
    remove_files(unwanted)
    poke()
    return {"applied": applied}


@app.get("/api/hoard")
def hoard() -> dict:
    with db.session() as conn:
        return {"pieces": store.hoard(conn)}


@app.post("/api/hoard/{key}/retry")
def retry(key: str) -> dict:
    with db.session() as conn:
        if not store.retry(conn, key):
            raise HTTPException(404, "That piece isn't in the hoard.")
    poke()
    return {"ok": True}


@app.get("/api/rooms")
def get_rooms() -> dict:
    with db.session() as conn:
        enabled = set(store.rooms(conn))
        with_sculpture = store.sculpture(conn)
    return {
        "rooms": [{"id": i, "name": n, "enabled": i in enabled} for i, n in sorted(DEPARTMENTS.items(), key=lambda x: x[1])],
        "sculpture": with_sculpture,
    }


@app.put("/api/rooms")
def put_rooms(body: Rooms) -> dict:
    with db.session() as conn:
        stale = store.set_rooms(conn, body.enabled, body.sculpture)
    remove_files(stale)
    poke()
    return get_rooms()


IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


@app.get("/api/art/{key}/{kind}")
def art_image(key: str, kind: str) -> FileResponse:
    """A piece's image. Keys never change their picture, so browsers may keep them forever."""
    if not images.valid_key(key) or kind not in ("image", "thumb"):
        raise HTTPException(404)
    if kind == "thumb":
        options = [images.thumb_path(key), images.hoard_path(key)]
    else:
        options = [images.hoard_path(key), images.candidate_path(key)]
    for path in options:
        if path.exists():
            return FileResponse(path, media_type="image/jpeg", headers=IMMUTABLE)
    raise HTTPException(404)


class UiFiles(StaticFiles):
    """Static files with cache headers that survive a rebuild.

    Vite fingerprints the filenames under assets/, so those can be cached forever.
    Everything else keeps its name across rebuilds (the entry HTML, the icons, the
    manifest, the service worker) and must be revalidated every time.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        path = Path(str(args[0])) if args else Path()
        if "assets" in path.parts:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


# Mounted last so every /api route above still wins. Missing in a checkout that has not
# been built yet, which is fine: run the Vite dev server instead.
_ui = config.ui_dir()
if _ui.is_dir():
    app.mount("/", UiFiles(directory=_ui, html=True), name="ui")
