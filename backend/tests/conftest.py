from __future__ import annotations

import io
import pytest
from PIL import Image

from app import db, images, store
from app.met import Draft


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGPIE_DATA_DIR", str(tmp_path))
    db.initialise()
    return tmp_path


@pytest.fixture
def conn():
    with db.session() as c:
        yield c


def jpeg(colour=(120, 60, 40), size=(300, 200)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, "JPEG")
    return out.getvalue()


def meta(n: int) -> dict:
    return {"source": "met", "source_id": n, "title": f"Piece {n}", "image_url": f"https://example.test/{n}.jpg"}


def add_candidate(conn, n: int) -> str:
    key = f"met-{n}"
    prepared = images.prepare(jpeg())
    images.write(images.candidate_path(key), prepared.jpeg)
    store.add_candidate(conn, key, meta(n), prepared)
    return key


class FakeSource:
    def __init__(self):
        self.n = 1000

    async def random_draft(self, rooms, skip, sculpture=False):
        self.n += 1
        return Draft(key=f"met-{self.n}", meta=meta(self.n), image_url=meta(self.n)["image_url"])

    async def download(self, url):
        return jpeg()

