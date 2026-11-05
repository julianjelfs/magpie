"""The Metropolitan Museum of Art's open access API: where new pieces come from.

https://metmuseum.github.io/ — no key, about 80 requests a second allowed.

The paginated search (v1.1) stops at offset 10,000, so it cannot pick uniformly from a
department of 185,000 prints. Instead each department's full list of object IDs comes
from /objects?departmentIds=N, cached on disk for a week, and a random ID is drawn
from that. About a quarter of picks come from the Met's own highlights instead, so the
early days are not all ornament prints and trade cards.
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

HIGHLIGHT_SHARE = 0.25
LIST_MAX_AGE = 7 * 24 * 3600


@dataclass(frozen=True)
class Draft:
    """A museum object that has an image we are allowed to show and keep."""

    key: str
    meta: dict
    image_url: str


def piece_key(object_id: int) -> str:
    return f"met-{object_id}"


def describe(obj: dict) -> Draft | None:
    """Turn a Met object record into what Magpie keeps. None if it can't be used."""
    image = obj.get("primaryImage") or ""
    if not image or not obj.get("isPublicDomain"):
        return None
    classification = obj.get("classification") or ""
    # The Burdick collection alone is tens of thousands of trade and baseball cards.
    if "Ephemera" in classification:
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

    async def _cached_list(self, name: str, url: str, params: dict) -> list[int]:
        async with self._lock:
            now = time.time()
            held = self._lists.get(name)
            if held and now - held[0] < LIST_MAX_AGE:
                return held[1]
            path = self.cache_dir / f"{name}.json"
            if path.exists() and now - path.stat().st_mtime < LIST_MAX_AGE:
                ids = json.loads(path.read_text())
            else:
                response = await self.http.get(url, params=params)
                response.raise_for_status()
                ids = response.json().get("objectIDs") or []
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(ids))
                log.info("cached %d object ids for %s", len(ids), name)
            self._lists[name] = (now, ids)
            return ids

    async def room_ids(self, department: int) -> list[int]:
        return await self._cached_list(
            f"room-{department}", f"{API}/v1/objects", {"departmentIds": department}
        )

    async def highlight_ids(self, department: int) -> list[int]:
        return await self._cached_list(
            f"highlights-{department}",
            f"{API}/v1.1/search",
            {"q": "*", "departmentId": department, "isHighlight": "true", "hasImages": "true", "limit": 1000},
        )

    async def get_object(self, object_id: int) -> dict | None:
        response = await self.http.get(f"{API}/v1/objects/{object_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def random_draft(self, rooms: list[int], skip: set[str], attempts: int = 12) -> Draft | None:
        """A usable piece from one of the rooms, not in skip. None after too many misses."""
        if not rooms:
            return None
        for _ in range(attempts):
            room = random.choice(rooms)
            ids = await self.highlight_ids(room) if random.random() < HIGHLIGHT_SHARE else []
            if not ids:
                ids = await self.room_ids(room)
            if not ids:
                continue
            object_id = random.choice(ids)
            if piece_key(object_id) in skip:
                continue
            obj = await self.get_object(object_id)
            draft = describe(obj) if obj else None
            if draft:
                return draft
        return None

    async def download(self, url: str) -> bytes:
        response = await self.http.get(url, timeout=httpx.Timeout(120.0, connect=10.0))
        response.raise_for_status()
        return response.content
