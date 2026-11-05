"""Image handling: shrink museum originals, pick a wall colour, and know where files live."""

from __future__ import annotations

import colorsys
import io
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from . import config

# Met originals run to 80 megapixels and more. They are trusted, and draft mode keeps
# memory down, so the decompression-bomb guard only gets in the way.
Image.MAX_IMAGE_PIXELS = None

KEY_PATTERN = re.compile(r"^[a-z]+-\d+$")


@dataclass(frozen=True)
class Prepared:
    jpeg: bytes
    width: int
    height: int
    wall_colour: str


def valid_key(key: str) -> bool:
    return bool(KEY_PATTERN.match(key))


def candidate_path(key: str) -> Path:
    return config.images_dir() / "candidates" / f"{key}.jpg"


def hoard_path(key: str) -> Path:
    return config.images_dir() / "hoard" / f"{key}.jpg"


def thumb_path(key: str) -> Path:
    return config.images_dir() / "hoard" / f"{key}-thumb.jpg"


def _open(raw: bytes, edge: int) -> Image.Image:
    img = Image.open(io.BytesIO(raw))
    # For JPEGs, decode at a reduced scale straight away: a fraction of the time and
    # memory of decoding 80 megapixels and then throwing most of them away.
    img.draft("RGB", (edge, edge))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((edge, edge), Image.LANCZOS)
    return img


def _jpeg(img: Image.Image, quality: int = 84) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def prepare(raw: bytes, edge: int = config.DISPLAY_EDGE) -> Prepared:
    img = _open(raw, edge)
    return Prepared(jpeg=_jpeg(img), width=img.width, height=img.height, wall_colour=wall_colour(img))


def resized(path: Path, edge: int, quality: int = 82) -> bytes:
    return _jpeg(_open(path.read_bytes(), edge), quality)


def wall_colour(img: Image.Image) -> str:
    """A wall to hang the piece on, the way a curator would paint one.

    Takes the piece's commonest colour, mutes it, and darkens it. A dark piece gets a
    lighter wall so its edges don't vanish into it. Either way the wall stays dark
    enough for light text on top.
    """
    small = img.copy()
    small.thumbnail((96, 96))
    quantised = small.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    palette = quantised.getpalette() or []
    counts = sorted(quantised.getcolors() or [], reverse=True)

    def rgb(index: int) -> tuple[float, float, float]:
        r, g, b = palette[index * 3 : index * 3 + 3]
        return r / 255, g / 255, b / 255

    total = sum(c for c, _ in counts) or 1
    mean_light = sum(c * colorsys.rgb_to_hls(*rgb(i))[1] for c, i in counts) / total

    # Prefer a colour with some hue in it over the commonest grey, if it is common enough.
    best = counts[0][1]
    best_score = -1.0
    for count, index in counts:
        _, light, sat = colorsys.rgb_to_hls(*rgb(index))
        score = (count / total) * (0.35 + sat) * (1 - abs(light - 0.5))
        if score > best_score:
            best, best_score = index, score

    hue, _, sat = colorsys.rgb_to_hls(*rgb(best))
    light = 0.36 if mean_light < 0.3 else 0.19
    sat = min(sat, 0.32) * 0.85
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
