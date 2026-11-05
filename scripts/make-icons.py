"""Render the glint mark to PNG app icons, matching favicon.svg and Mark.svelte.

Usage: uv run --project backend python scripts/make-icons.py frontend/public
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

WALL = (0x2B, 0x32, 0x36)
PAPER = (0xF8, 0xF8, 0xF5)
SHEEN = (0x7C, 0xC3, 0xCF)


def glint(cx, cy, r, pinch=0.13, steps=40):
    """A four-pointed star with concave sides, centred on (cx, cy)."""
    points = []
    tips = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    for i, (x0, y0) in enumerate(tips):
        x2, y2 = tips[(i + 1) % 4]
        # Quadratic curve pulled in towards the centre.
        qx, qy = cx + (x0 + x2 - 2 * cx) * pinch, cy + (y0 + y2 - 2 * cy) * pinch
        for s in range(steps):
            t = s / steps
            points.append(((1 - t) ** 2 * x0 + 2 * (1 - t) * t * qx + t * t * x2,
                           (1 - t) ** 2 * y0 + 2 * (1 - t) * t * qy + t * t * y2))
    return points


def render(size: int, mark: float) -> Image.Image:
    scale = 4
    big = size * scale
    img = Image.new("RGB", (big, big), WALL)
    draw = ImageDraw.Draw(img)
    unit = big * mark / 24
    ox = oy = (big - 24 * unit) / 2
    draw.polygon(glint(ox + 10 * unit, oy + 10 * unit, 8.5 * unit), fill=PAPER)
    draw.polygon(glint(ox + 19 * unit, oy + 18 * unit, 4 * unit), fill=SHEEN)
    return img.resize((size, size), Image.LANCZOS)


out = Path(sys.argv[1])
# Maskable icons keep the mark inside the middle 80%.
render(192, 0.62).save(out / "icon-192.png")
render(512, 0.62).save(out / "icon-512.png")
render(180, 0.66).save(out / "apple-touch-icon.png")
print("wrote icons to", out)
