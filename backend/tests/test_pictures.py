"""Invariant 8: Magpie offers pictures, and sculpture only when it is switched on."""

from __future__ import annotations

from app import images, store
from app.met import describe

from .conftest import jpeg


def record(classification: str, object_name: str) -> dict:
    return {
        "objectID": 1,
        "primaryImage": "https://images.example/1.jpg",
        "isPublicDomain": True,
        "classification": classification,
        "objectName": object_name,
        "title": "A piece",
    }


def test_invariant_8_only_pictures_are_offered_and_sculpture_only_when_on():
    assert describe(record("Paintings", "Hanging scroll"))
    assert describe(record("Codices", "Folio from a Shahnama"))
    assert describe(record("Prints", "Print"))

    assert not describe(record("Frames", "Frame"))
    assert not describe(record("Ceramics", "Dish"))
    assert not describe(record("Prints|Ephemera", "Trade card"))
    assert not describe(record("Textiles-Printed", "Panel"))

    assert not describe(record("Sculpture", "Statue"))
    assert describe(record("Sculpture", "Statue"), sculpture=True)


def test_switching_sculpture_off_drops_waiting_sculpture(conn):
    store.set_rooms(conn, store.rooms(conn), with_sculpture=True)
    prepared = images.prepare(jpeg())
    statue = {"department": "Asian Art", "classification": "Sculpture", "object_name": "Figure"}
    painting = {"department": "Asian Art", "classification": "Paintings", "object_name": "Hanging scroll"}
    store.add_candidate(conn, "met-1", statue, prepared)
    store.add_candidate(conn, "met-2", painting, prepared)

    store.set_rooms(conn, store.rooms(conn), with_sculpture=False)

    assert [p["key"] for p in store.take_candidates(conn, 10, set())] == ["met-2"]
