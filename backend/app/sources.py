"""Where new pieces come from: the Met, Wikidata, Cleveland and SMK.

Each source has rooms. Steering picks the room; the room's source picks the piece.
"""

from __future__ import annotations

import asyncio
import logging
import random

from .cleveland import Cleveland
from .met import DEFAULT_ROOMS as MET_DEFAULT_ROOMS
from .met import DEPARTMENTS, HIGHLIGHT_SHARE, Draft, Met, subjects_of
from .smk import Smk
from .wikidata import MODERN, ROOM_NAME, Wikidata

log = logging.getLogger(__name__)

# The rooms there were before Cleveland and SMK. A saved choice of rooms that doesn't say
# which rooms it knew about knew these.
FIRST_ROOMS = [*DEPARTMENTS, MODERN]

ROOMS: dict[int, str] = {**DEPARTMENTS, MODERN: ROOM_NAME, **Cleveland.ROOMS, **Smk.ROOMS}
DEFAULT_ROOMS = [*MET_DEFAULT_ROOMS, MODERN, *Cleveland.ROOMS, *Smk.ROOMS]


class Sources:
    def __init__(self, met: Met, wikidata: Wikidata, cleveland: Cleveland, smk: Smk):
        self.met = met
        self.wikidata = wikidata
        self.others = [cleveland, smk]

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
        for other in self.others:
            if room in other.ROOMS:
                return await other.random_draft(room, skip)
        return await self.met.random_draft([room], skip, sculpture, highlight_share=highlight_share)

    async def by_artist(self, name: str, rooms: list[int], skip: set[str], sculpture: bool = False) -> Draft | None:
        """Another piece by an artist, from whichever source has one. Sources are tried in
        random order, so an artist first met in one museum turns up from the others too."""
        asks = [
            lambda: self.met.by_artist(name, rooms, skip, sculpture),
            lambda: self.wikidata.by_artist(name, rooms, skip),
            *(lambda other=other: other.by_artist(name, rooms, skip) for other in self.others),
        ]
        random.shuffle(asks)
        for ask in asks:
            try:
                if draft := await ask():
                    return draft
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("could not look for more by %s: %s", name, e)
        return None

    async def subjects(self, key: str) -> list[str]:
        """What a piece shows, by the museum's own subject terms. Only the Met has them."""
        source, _, number = key.partition("-")
        if source != "met":
            return []
        obj = await self.met.get_object(int(number))
        return subjects_of(obj or {})

    async def download(self, url: str) -> bytes:
        if "wikimedia.org" in url:
            return await self.wikidata.download(url)
        return await self.met.download(url)

    async def close(self) -> None:
        await self.met.close()
        await self.wikidata.close()
        for other in self.others:
            await other.close()
