"""Museums whose search API pages by offset: Cleveland and SMK.

Both filter server-side to public-domain pictures with an image, so a random piece is one
request: a random offset into the filtered list. Nothing is listed or cached ahead except
how long each list is.
"""

from __future__ import annotations

import asyncio
import random
import time

import httpx

from .met import Draft

USER_AGENT = "magpie/0.1 (a personal art library)"
SPACING = 1.0  # seconds between requests to one museum
TOTAL_MAX_AGE = 7 * 24 * 3600
ARTIST_MAX_AGE = 24 * 3600
ARTIST_ROWS = 100


def same_artist(a: str, b: str) -> bool:
    return bool(a) and a.strip().casefold() == b.strip().casefold()


class OffsetSource:
    """One museum. Subclasses say what its rooms are, how to ask, and how to read a record."""

    ROOMS: dict[int, str] = {}

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self._totals: dict[int, tuple[float, int]] = {}
        self._artists: dict[str, tuple[float, list[Draft]]] = {}
        self._pace = asyncio.Lock()
        self._last = 0.0

    @classmethod
    def create(cls):
        http = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        return cls(http)

    async def close(self) -> None:
        await self.http.aclose()

    async def _get(self, url: str, params: dict) -> dict:
        async with self._pace:
            wait = self._last + SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
        response = await self.http.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def _page(self, room: int | None, offset: int, rows: int, artist: str | None = None) -> tuple[int, list[dict]]:
        """How many records match, and the ones at offset. room None means every room."""
        raise NotImplementedError

    def describe(self, obj: dict) -> Draft | None:
        """What Magpie keeps of a record, with its room. None if it can't be offered."""
        raise NotImplementedError

    async def _total(self, room: int) -> int:
        held = self._totals.get(room)
        if held and time.time() - held[0] < TOTAL_MAX_AGE:
            return held[1]
        total, _ = await self._page(room, 0, 1)
        self._totals[room] = (time.time(), total)
        return total

    async def random_draft(self, room: int, skip: set[str], attempts: int = 4) -> Draft | None:
        total = await self._total(room)
        for _ in range(attempts):
            if not total:
                return None
            _, records = await self._page(room, random.randrange(total), 1)
            for obj in records:
                draft = self.describe(obj)
                if draft and draft.key not in skip:
                    return draft
        return None

    async def by_artist(self, name: str, rooms: list[int], skip: set[str]) -> Draft | None:
        """Another piece by this artist from an open room, if the museum has one."""
        if not any(r in self.ROOMS for r in rooms):
            return None
        held = self._artists.get(name)
        if not held or time.time() - held[0] > ARTIST_MAX_AGE:
            _, records = await self._page(None, 0, ARTIST_ROWS, artist=name)
            drafts = [d for d in map(self.describe, records) if d and same_artist(d.meta["artist"], name)]
            held = self._artists[name] = (time.time(), drafts)
        choices = [d for d in held[1] if d.meta["room"] in rooms and d.key not in skip]
        return random.choice(choices) if choices else None
