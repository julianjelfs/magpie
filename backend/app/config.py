"""Where things live, and the knobs worth turning. All overridable from the environment."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    override = os.environ.get("MAGPIE_DATA_DIR")
    return Path(override) if override else BACKEND_DIR


def database_path() -> Path:
    override = os.environ.get("MAGPIE_DB_PATH")
    return Path(override) if override else data_dir() / "magpie.db"


def images_dir() -> Path:
    return data_dir() / "images"


def cache_dir() -> Path:
    return data_dir() / "cache"


def ui_dir() -> Path:
    override = os.environ.get("MAGPIE_UI_DIR")
    return Path(override) if override else BACKEND_DIR.parent / "frontend" / "dist"


# Claude tags each kept piece. Opus at low effort: tagging is quick work, but
# naming a movement from a picture rewards the stronger model.
TAG_MODEL = os.environ.get("MAGPIE_TAG_MODEL", "claude-opus-5-5")
TAG_EFFORT = os.environ.get("MAGPIE_TAG_EFFORT", "low")

# How many prepared pieces to keep waiting that no device has seen yet.
CANDIDATE_BUFFER = int(os.environ.get("MAGPIE_CANDIDATE_BUFFER", "8"))

# Long edge, in pixels, of the copy shown on the wall and kept in the hoard. Seen on the
# web and zoomed a little at most, so sharp at full height on most screens and no more:
# a few hundred KB a piece.
DISPLAY_EDGE = 1600
DISPLAY_QUALITY = 80
THUMB_EDGE = 480
# Claude reads images at up to about this size; anything larger is resized on their side.
CLAUDE_EDGE = 1568
