"""Modern painting from Wikidata and Wikimedia Commons.

Museums publish open images only of public-domain work, so modern art means artists dead
long enough. In the UK a painting is in copyright until the end of the 70th year after
its artist's death: someone who died in 1955 is public domain from 1 January 2026. That is
checked per artist, every time, from their year of death on Wikidata, so artists join on
their own each January.

The artists are a hand-picked list in artists.json (name, Wikidata ID, dates,
nationality). Wikidata's query service times out on broad questions ("every painting
from 1910") but answers per artist in a second or two, so each artist's paintings are
listed with one small query and cached for a week. A pick is a random artist, then a
random painting with an image on Commons.

The query service allows 60 seconds of query time a minute. Queries here are spaced two
seconds apart, and a 429 means resting for as long as Retry-After says.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

from .met import Draft

log = logging.getLogger(__name__)

MODERN = 100
ROOM_NAME = "Modern painting (Wikimedia Commons)"
USER_AGENT = "magpie/0.1 (a personal art library; https://magpie.julianjelfs.co.uk)"
SPARQL = "https://query.wikidata.org/sparql"
LIST_MAX_AGE = 7 * 24 * 3600
SPACING = 2.0
PAINTING = "Q3305213"

ARTISTS: list[dict] = json.loads((Path(__file__).parent / "artists.json").read_text())


class WikidataBusy(Exception):
    """The query service has asked us to wait."""


def public_domain(died: int, today: date | None = None) -> bool:
    """In the UK: from 1 January of the 71st year after the artist's death."""
    return died + 70 < (today or date.today()).year


def eligible_artists(today: date | None = None) -> list[dict]:
    return [a for a in ARTISTS if public_domain(a["died"], today)]


def piece_key(qid: str) -> str:
    return f"wd-{int(qid.lstrip('Q'))}"


def _query(qid: str) -> str:
    return f"""
SELECT ?p ?pLabel ?img ?made ?collLabel WHERE {{
  ?p wdt:P170 wd:{qid}; wdt:P31 wd:{PAINTING}; wdt:P18 ?img.
  OPTIONAL {{ ?p wdt:P571 ?made }}
  OPTIONAL {{ ?p wdt:P195 ?coll }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def paintings_from(rows: list[dict]) -> list[dict]:
    """One entry per painting from SPARQL rows (a painting with two collections comes twice)."""
    seen: dict[str, dict] = {}
    for r in rows:
        qid = r["p"]["value"].rsplit("/", 1)[1]
        if qid in seen:
            continue
        title = r.get("pLabel", {}).get("value", "")
        made = r.get("made", {}).get("value", "")
        collection = r.get("collLabel", {}).get("value", "")
        seen[qid] = {
            "qid": qid,
            # With no English title the label service falls back to the bare ID.
            "title": "" if title == qid else title,
            "file": unquote(r["img"]["value"].rsplit("/", 1)[1]),
            "year": int(made[:4]) if made[:4].lstrip("-").isdigit() else None,
            "collection": "" if collection.startswith("Q") and collection[1:].isdigit() else collection,
        }
    return list(seen.values())


def describe(artist: dict, painting: dict) -> Draft:
    file = painting["file"]
    image = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(file)}?width=2000"
    born = artist.get("born")
    life = f"{born}–{artist['died']}" if born else f"died {artist['died']}"
    year = painting.get("year")
    meta = {
        "source": "wikidata",
        "source_id": int(painting["qid"].lstrip("Q")),
        "title": painting["title"] or "Untitled",
        "artist": artist["name"],
        "artist_bio": ", ".join(x for x in (artist.get("nationality"), life) if x),
        "culture": "",
        "period": "",
        "date": str(year) if year else "",
        "begin_year": year,
        "end_year": year,
        "medium": "",
        "dimensions": "",
        "department": ROOM_NAME,
        "classification": "Paintings",
        "object_name": "Painting",
        "credit_line": painting.get("collection", ""),
        "museum_url": f"https://www.wikidata.org/wiki/{painting['qid']}",
        "image_url": image,
        "highlight": False,
        "room": MODERN,
    }
    return Draft(key=piece_key(painting["qid"]), meta=meta, image_url=image)


class Wikidata:
    def __init__(self, http: httpx.AsyncClient, cache_dir: Path):
        self.http = http
        self.cache_dir = cache_dir
        self._lists: dict[str, tuple[float, list[dict]]] = {}
        self._pace = asyncio.Lock()
        self._last = 0.0
        self._blocked_until = 0.0

    @classmethod
    def create(cls, cache_dir: Path) -> "Wikidata":
        http = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(60.0, connect=10.0),
            follow_redirects=True,
        )
        return cls(http, cache_dir)

    async def close(self) -> None:
        await self.http.aclose()

    async def _sparql(self, query: str) -> list[dict]:
        async with self._pace:
            if time.monotonic() < self._blocked_until:
                raise WikidataBusy("Wikidata asked us to wait")
            wait = self._last + SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
        response = await self.http.get(
            SPARQL, params={"query": query}, headers={"Accept": "application/sparql-results+json"}
        )
        if response.status_code == 429:
            pause = int(response.headers.get("retry-after") or 60)
            self._blocked_until = time.monotonic() + pause
            log.warning("Wikidata is rate limiting; pausing for %d seconds", pause)
            raise WikidataBusy("Wikidata asked us to wait")
        response.raise_for_status()
        return response.json()["results"]["bindings"]

    async def paintings(self, artist: dict) -> list[dict]:
        qid = artist["qid"]
        now = time.time()
        held = self._lists.get(qid)
        if held and now - held[0] < LIST_MAX_AGE:
            return held[1]
        path = self.cache_dir / f"wd-{qid}.json"
        if path.exists() and now - path.stat().st_mtime < LIST_MAX_AGE:
            paintings = json.loads(path.read_text())
        else:
            paintings = paintings_from(await self._sparql(_query(qid)))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(paintings))
            log.info("cached %d paintings by %s", len(paintings), artist["name"])
        self._lists[qid] = (now, paintings)
        return paintings

    async def random_draft(self, skip: set[str], attempts: int = 6) -> Draft | None:
        artists = eligible_artists()
        for _ in range(attempts):
            if not artists:
                return None
            artist = random.choice(artists)
            choices = [p for p in await self.paintings(artist) if piece_key(p["qid"]) not in skip]
            if choices:
                return describe(artist, random.choice(choices))
        return None

    async def download(self, url: str) -> bytes:
        response = await self.http.get(url, timeout=httpx.Timeout(120.0, connect=10.0))
        response.raise_for_status()
        return response.content
