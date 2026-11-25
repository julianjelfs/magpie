"""SMK, the National Gallery of Denmark. No key.

https://api.smk.dk/api/v1/ — filtered to `public_domain:true` and `has_image:true`, about
39,000 works: Danish Golden Age painting, and a large print room. Records are in Danish;
titles and materials are shown as the museum gives them. Images come from its IIIF server
at 2000px.
"""

from __future__ import annotations

from .met import Draft
from .openaccess import OffsetSource

API = "https://api.smk.dk/api/v1/art/search/"
MUSEUM = "SMK, National Gallery of Denmark"

# Room: (name in the app, the museum's object name, the kind as the Met would file it).
KINDS: dict[int, tuple[str, str, str]] = {
    301: ("SMK Copenhagen: paintings", "maleri", "Paintings"),
    302: ("SMK Copenhagen: drawings", "tegning", "Drawings"),
    303: ("SMK Copenhagen: prints", "grafik", "Prints"),
}
ROOM_OF_NAME = {name: room for room, (_, name, _) in KINDS.items()}

NATIONALITIES = {
    "Dansk": "Danish", "Italiensk": "Italian", "Fransk": "French", "Tysk": "German",
    "Hollandsk": "Dutch", "Nederlandsk": "Netherlandish", "Flamsk": "Flemish", "Svensk": "Swedish",
    "Norsk": "Norwegian", "Engelsk": "English", "Britisk": "British", "Spansk": "Spanish",
}  # fmt: skip


def _year(stamp: str | None) -> int | None:
    return int(stamp[:4]) if stamp and stamp[:4].isdigit() else None


def describe(obj: dict) -> Draft | None:
    names = [(n.get("name") or "").lower() for n in obj.get("object_names") or []]
    room = next((ROOM_OF_NAME[n] for n in names if n in ROOM_OF_NAME), None)
    iiif = obj.get("image_iiif_id") or ""
    number = (obj.get("id") or "").split("_")[0]
    if room is None or not iiif or not obj.get("public_domain") or not number.isdigit():
        return None
    image = f"{iiif}/full/!2000,2000/0/default.jpg"
    maker = (obj.get("production") or [{}])[0]
    nationality = maker.get("creator_nationality") or ""
    born, died = _year(maker.get("creator_date_of_birth")), _year(maker.get("creator_date_of_death"))
    life = f"{born}–{died}" if born and died else ""
    made = (obj.get("production_date") or [{}])[0]
    kind = KINDS[room][2]
    meta = {
        "source": "smk",
        "source_id": int(number),
        "title": ((obj.get("titles") or [{}])[0].get("title") or "Untitled").strip(),
        "artist": ((obj.get("artist") or [""])[0] or "").strip(),
        "artist_bio": ", ".join(x for x in (NATIONALITIES.get(nationality, nationality), life) if x),
        "culture": "",
        "period": "",
        "date": made.get("period") or "",
        "begin_year": _year(made.get("start")),
        "end_year": _year(made.get("end")),
        "medium": ", ".join(obj.get("techniques") or obj.get("materials") or []),
        "dimensions": "",
        "department": MUSEUM,
        "classification": kind,
        "object_name": kind[:-1],
        "credit_line": "",
        "museum_url": obj.get("frontend_url") or "",
        "image_url": image,
        "highlight": False,
        "subjects": [],
        "room": room,
    }
    return Draft(key=f"smk-{number}", meta=meta, image_url=image)


class Smk(OffsetSource):
    ROOMS = {room: name for room, (name, _, _) in KINDS.items()}

    async def _page(self, room, offset, rows, artist=None):
        filters = ["[public_domain:true]", "[has_image:true]"]
        if room is not None:
            filters.append(f"[object_names:{KINDS[room][1]}]")
        if artist:
            filters.append(f"[artist:{artist}]")
        data = await self._get(API, {"keys": "*", "filters": ",".join(filters), "offset": offset, "rows": rows})
        return data["found"], data["items"]

    def describe(self, obj):
        return describe(obj)
