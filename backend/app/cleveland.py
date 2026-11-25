"""The Cleveland Museum of Art's open access API. No key.

https://openaccess-api.clevelandart.org/ — `cc0=1&has_image=1` leaves only works the
museum has released under CC0, and `type` splits them into rooms. About 18,000 pictures.
"""

from __future__ import annotations

from .met import Draft
from .openaccess import OffsetSource

API = "https://openaccess-api.clevelandart.org/api/artworks/"
MUSEUM = "Cleveland Museum of Art"

# Room: (name in the app, the API's type, the kind as the Met would file it).
TYPES: dict[int, tuple[str, str, str]] = {
    201: ("Cleveland: paintings", "Painting", "Paintings"),
    202: ("Cleveland: drawings", "Drawing", "Drawings"),
    203: ("Cleveland: prints", "Print", "Prints"),
    204: ("Cleveland: photographs", "Photograph", "Photographs"),
}
ROOM_OF_TYPE = {api_type: room for room, (_, api_type, _) in TYPES.items()}


def _maker(obj: dict) -> tuple[str, str]:
    """Name and life details from "Odilon Redon (French, 1840–1916)"."""
    creators = obj.get("creators") or []
    described = (creators[0].get("description") or "") if creators else ""
    name, _, rest = described.partition(" (")
    return name.strip(), rest.rstrip(")").strip()


def describe(obj: dict) -> Draft | None:
    room = ROOM_OF_TYPE.get(obj.get("type") or "")
    images = obj.get("images") or {}
    image = (images.get("print") or images.get("web") or {}).get("url") or ""
    if room is None or not image or obj.get("share_license_status") != "CC0":
        return None
    artist, bio = _maker(obj)
    kind = TYPES[room][2]
    meta = {
        "source": "cleveland",
        "source_id": obj["id"],
        "title": (obj.get("title") or "Untitled").strip(),
        "artist": artist,
        "artist_bio": bio,
        "culture": ((obj.get("culture") or [""])[0] or "").strip(),
        "period": "",
        "date": (obj.get("creation_date") or "").strip(),
        "begin_year": obj.get("creation_date_earliest"),
        "end_year": obj.get("creation_date_latest"),
        "medium": (obj.get("technique") or "").strip(),
        "dimensions": (obj.get("measurements") or "").strip(),
        "department": f"{MUSEUM}, {obj.get('department') or kind}",
        "classification": kind,
        "object_name": obj.get("type") or "",
        "credit_line": (obj.get("creditline") or "").strip(),
        "museum_url": obj.get("url") or "",
        "image_url": image,
        "highlight": bool(obj.get("is_highlight")),
        "subjects": [],
        "room": room,
    }
    return Draft(key=f"cma-{obj['id']}", meta=meta, image_url=image)


class Cleveland(OffsetSource):
    ROOMS = {room: name for room, (name, _, _) in TYPES.items()}

    async def _page(self, room, offset, rows, artist=None):
        params = {"cc0": 1, "has_image": 1, "skip": offset, "limit": rows}
        if room is not None:
            params["type"] = TYPES[room][1]
        if artist:
            params["artists"] = artist
        data = await self._get(API, params)
        return data["info"]["total"], data["data"]

    def describe(self, obj):
        return describe(obj)
