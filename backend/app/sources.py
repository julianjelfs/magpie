"""Where new pieces come from: the Met's departments, and modern painting from Wikidata.

Each source is a room. Steering picks the room; the room's source picks the piece.
"""

from __future__ import annotations

import random

from .met import DEFAULT_ROOMS as MET_DEFAULT_ROOMS
from .met import DEPARTMENTS, HIGHLIGHT_SHARE, Draft, Met
from .wikidata import MODERN, ROOM_NAME, Wikidata

ROOMS: dict[int, str] = {**DEPARTMENTS, MODERN: ROOM_NAME}
DEFAULT_ROOMS = [*MET_DEFAULT_ROOMS, MODERN]


class Sources:
    def __init__(self, met: Met, wikidata: Wikidata):
        self.met = met
        self.wikidata = wikidata

    async def random_draft(
        self,
        rooms: list[int],
        skip: set[str],
        sculpture: bool = False,
        weights: list[float] | None = None,
        highlight_share: float = HIGHLIGHT_SHARE,
    ) -> Draft | None:
        if not rooms:
            return None
        room = random.choices(rooms, weights=weights)[0]
        if room == MODERN:
            return await self.wikidata.random_draft(skip)
        return await self.met.random_draft([room], skip, sculpture, highlight_share=highlight_share)

    async def download(self, url: str) -> bytes:
        if "wikimedia.org" in url:
            return await self.wikidata.download(url)
        return await self.met.download(url)

    async def close(self) -> None:
        await self.met.close()
        await self.wikidata.close()
