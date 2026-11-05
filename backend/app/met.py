"""The Metropolitan Museum of Art's open access API: where new pieces come from.

https://metmuseum.github.io/ — no key. The docs allow 80 requests a second, but the
Imperva firewall in front of it blocks the house IP for a few minutes after as few as
seventy at three a second. So requests go one a second, and a 403 means five minutes'
rest. The laptop shares that IP: hammering the API from it starves the Pi too.

The search's isPublicDomain filter is ignored, and most modern art is in copyright, so
some rooms miss often. Every object fetched and found unusable is remembered in
cache/rejected.json and never fetched again.

Magpie offers pictures: paintings, drawings, prints, photographs, manuscript pages and
calligraphy, plus sculpture if it is switched on. How a room's object IDs are listed
depends on the room:

- Drawings and Prints, European Paintings and Photographs hold almost nothing but
  pictures. Their full ID list comes from /objects?departmentIds=N.
- Every other room is mostly objects (ceramics, metalwork, frames). Its list is built
  from v1.1 searches filtered by type (`medium=Paintings` and so on), paged 500 at a
  time. The v1.1 search stops at offset 10,000, which is fine for these rooms.

Lists are cached on disk for a week. Every fetched object is still checked against the
picture types before its image is downloaded. About a quarter of picks come from the
Met's own highlights instead, so the early days are not all ornament prints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

API = "https://collectionapi.metmuseum.org/public/collection"
USER_AGENT = "magpie/0.1 (a personal art library)"

# The Met's departments, as /v1/departments lists them. "Rooms" in the app.
DEPARTMENTS: dict[int, str] = {
    1: "American Wing",
    3: "Ancient West Asian Art",
    4: "Arms and Armor",
    5: "Arts of Africa, Oceania, and the Americas",
    6: "Asian Art",
    7: "The Cloisters",
    8: "The Costume Institute",
    9: "Drawings and Prints",
    10: "Egyptian Art",
    11: "European Paintings",
    12: "European Sculpture and Decorative Arts",
    13: "Greek and Roman Art",
    14: "Islamic Art",
    15: "The Robert Lehman Collection",
    17: "Medieval Art",
    19: "Photographs",
    21: "Modern and Contemporary Art",
}

# Pictures first: these are the rooms most likely to hold something worth sketching.
DEFAULT_ROOMS = [11, 9, 6, 21, 15, 14, 19]

# Rooms that hold pictures and little else, listed whole.
PICTURE_ROOMS = {9, 11, 19}

# The type filters searched in every other room. Islamic paintings are mostly folios
# from manuscripts, which the Met files as Codices.
PICTURE_TYPES = ["Paintings", "Drawings", "Prints", "Photographs", "Codices", "Calligraphy", "Miniatures"]
SCULPTURE_TYPES = ["Sculpture"]

# Words in a record's classification or object name that make it a picture.
PICTURE_WORDS = (
    "painting", "drawing", "print", "photograph", "codex", "codices", "calligraph", "miniature",
    "manuscript", "album", "illustrated book", "folio", "works on paper", "pastel", "watercolor",
    "collage", "scroll",
)
SCULPTURE_WORDS = ("sculpture", "statue", "statuette", "bust", "relief")
# Classifications that are objects whatever their name says ("Textiles-Printed").
OBJECT_WORDS = ("ephemera", "textile", "ceramic", "frame", "furniture", "metalwork", "glass", "jewelry", "costume")

HIGHLIGHT_SHARE = 0.25
LIST_MAX_AGE = 7 * 24 * 3600
PAGE = 500
OFFSET_LIMIT = 10_000
SPACING = 1.0  # seconds between requests to the Met
BLOCKED_PAUSE = 300  # after a 403 from the firewall, leave the Met alone this long


class MetBusy(Exception):
    """The Met's firewall is refusing us for now."""


@dataclass(frozen=True)
class Draft:
    """A museum object that has an image we are allowed to show and keep."""

    key: str
    meta: dict
    image_url: str


def piece_key(object_id: int) -> str:
    return f"met-{object_id}"


def is_picture(classification: str, object_name: str, sculpture: bool = False) -> bool:
    """A painting, drawing, print or the like; or sculpture, if that is switched on."""
    # Ephemera: the Burdick collection alone is tens of thousands of trade and baseball cards.
    if any(word in classification.lower() for word in OBJECT_WORDS):
        return False
    text = f"{classification} {object_name}".lower()
    if any(word in text for word in PICTURE_WORDS):
        return True
    return sculpture and any(word in text for word in SCULPTURE_WORDS)


def describe(obj: dict, sculpture: bool = False) -> Draft | None:
    """Turn a Met object record into what Magpie keeps. None if it can't be used."""
    image = obj.get("primaryImage") or ""
    if not image or not obj.get("isPublicDomain"):
        return None
    classification = obj.get("classification") or ""
    object_name = obj.get("objectName") or ""
    if not is_picture(classification, object_name, sculpture):
        return None
    artist = (obj.get("artistDisplayName") or "").strip()
    meta = {
        "source": "met",
        "source_id": obj["objectID"],
        "title": (obj.get("title") or "Untitled").strip(),
        "artist": artist,
        "artist_bio": (obj.get("artistDisplayBio") or "").strip(),
        "culture": (obj.get("culture") or "").strip(),
        "period": (obj.get("period") or "").strip(),
        "date": (obj.get("objectDate") or "").strip(),
        "begin_year": obj.get("objectBeginDate"),
        "end_year": obj.get("objectEndDate"),
        "medium": (obj.get("medium") or "").strip(),
        "dimensions": (obj.get("dimensions") or "").strip(),
        "department": obj.get("department") or "",
        "classification": classification,
        "object_name": object_name,
        "credit_line": (obj.get("creditLine") or "").strip(),
        "museum_url": obj.get("objectURL") or "",
        "image_url": image,
        "highlight": bool(obj.get("isHighlight")),
    }
    return Draft(key=piece_key(obj["objectID"]), meta=meta, image_url=image)


class Met:
    def __init__(self, http: httpx.AsyncClient, cache_dir: Path):
        self.http = http
        self.cache_dir = cache_dir
        self._lists: dict[str, tuple[float, list[int]]] = {}
        self._lock = asyncio.Lock()
        self._pace_lock = asyncio.Lock()
        self._last = 0.0
        self._blocked_until = 0.0
        self._rejected_path = cache_dir / "rejected.json"
        try:
            self.rejected: set[int] = set(json.loads(self._rejected_path.read_text()))
        except (OSError, ValueError):
            self.rejected = set()

    @classmethod
    def create(cls, cache_dir: Path) -> "Met":
        http = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        return cls(http, cache_dir)

    async def close(self) -> None:
        await self.http.aclose()

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """A GET to the Met, never sooner than SPACING after the last one."""
        async with self._pace_lock:
            if time.monotonic() < self._blocked_until:
                raise MetBusy("the Met's firewall is refusing requests; waiting")
            wait = self._last + SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
        response = await self.http.get(url, **kwargs)
        if response.status_code == 403:
            self._blocked_until = time.monotonic() + BLOCKED_PAUSE
            log.warning("the Met's firewall refused a request; pausing for %d seconds", BLOCKED_PAUSE)
            raise MetBusy("the Met's firewall refused a request")
        return response

    def _reject(self, object_id: int) -> None:
        self.rejected.add(object_id)
        try:
            self._rejected_path.parent.mkdir(parents=True, exist_ok=True)
            self._rejected_path.write_text(json.dumps(sorted(self.rejected)))
        except OSError:
            pass

    async def _cached_list(self, name: str, fetch) -> list[int]:
        async with self._lock:
            now = time.time()
            held = self._lists.get(name)
            if held and now - held[0] < LIST_MAX_AGE:
                return held[1]
            path = self.cache_dir / f"{name}.json"
            if path.exists() and now - path.stat().st_mtime < LIST_MAX_AGE:
                ids = json.loads(path.read_text())
            else:
                ids = await fetch()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(ids))
                log.info("cached %d object ids for %s", len(ids), name)
            self._lists[name] = (now, ids)
            return ids

    async def _search_all(self, params: dict) -> list[int]:
        ids: list[int] = []
        offset = 0
        while offset < OFFSET_LIMIT:
            response = await self._get(
                f"{API}/v1.1/search", params={"q": "*", **params, "limit": PAGE, "offset": offset}
            )
            response.raise_for_status()
            page = response.json().get("objectIDs") or []
            ids += page
            if len(page) < PAGE:
                break
            offset += PAGE
        return ids

    async def _department(self, department: int) -> list[int]:
        response = await self._get(f"{API}/v1/objects", params={"departmentIds": department})
        response.raise_for_status()
        return response.json().get("objectIDs") or []

    async def room_ids(self, department: int, sculpture: bool = False) -> list[int]:
        if department in PICTURE_ROOMS:
            return await self._cached_list(f"room-{department}", lambda: self._department(department))
        kinds = PICTURE_TYPES + (SCULPTURE_TYPES if sculpture else [])
        ids: list[int] = []
        for kind in kinds:
            ids += await self._cached_list(
                f"room-{department}-{kind.lower()}",
                lambda kind=kind: self._search_all({"departmentId": department, "hasImages": "true", "medium": kind}),
            )
        return list(dict.fromkeys(ids))

    async def highlight_ids(self, department: int) -> list[int]:
        return await self._cached_list(
            f"highlights-{department}",
            lambda: self._search_all({"departmentId": department, "isHighlight": "true", "hasImages": "true"}),
        )

    async def get_object(self, object_id: int) -> dict | None:
        response = await self._get(f"{API}/v1/objects/{object_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def random_draft(
        self, rooms: list[int], skip: set[str], sculpture: bool = False, attempts: int = 12
    ) -> Draft | None:
        """A usable piece from one of the rooms, not in skip. None after too many misses."""
        if not rooms:
            return None
        for _ in range(attempts):
            room = random.choice(rooms)
            ids = await self.highlight_ids(room) if random.random() < HIGHLIGHT_SHARE else []
            if not ids:
                ids = await self.room_ids(room, sculpture)
            if not ids:
                continue
            object_id = random.choice(ids)
            if piece_key(object_id) in skip or object_id in self.rejected:
                continue
            obj = await self.get_object(object_id)
            draft = describe(obj, sculpture) if obj else None
            if draft:
                return draft
            # Sculpture may be switched on later, so only remember what can never be used.
            if not obj or describe(obj, sculpture=True) is None:
                self._reject(object_id)
        return None

    async def download(self, url: str) -> bytes:
        # Images come from a CDN, not the API behind the firewall, so no pacing.
        response = await self.http.get(url, timeout=httpx.Timeout(120.0, connect=10.0))
        response.raise_for_status()
        return response.content
