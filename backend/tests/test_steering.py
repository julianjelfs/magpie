"""Invariants 12 to 16: steering within a room, its limits, and the newer sources."""

from __future__ import annotations

import asyncio

from app import cleveland, smk, store, taste
from app.met import Draft
from app.worker import Worker


def verdict(kept: bool, **meta) -> tuple[bool, dict]:
    return kept, {"classification": "Prints", "begin_year": 1850, **meta}


# A keep rate of one in ten, with one artist always kept and one subject never.
HISTORY = (
    [verdict(True, artist="Hokusai", subjects=["Waves"]) for _ in range(40)]
    + [verdict(False, artist="Dull", subjects=["Trade cards"]) for _ in range(360)]
)


class CountingSource:
    def __init__(self):
        self.drawn = 0
        self.asked_for_artist = 0

    async def random_draft(self, rooms, skip, sculpture=False, weights=None, highlight_share=0.25):
        self.drawn += 1
        return Draft(key=f"met-{self.drawn}", meta={"room": rooms[0]}, image_url="")

    async def by_artist(self, name, rooms, skip, sculpture=False):
        self.asked_for_artist += 1
        return Draft(key="met-999", meta={"room": rooms[0], "artist": name}, image_url="")


def test_invariant_12_a_fixed_share_of_picks_ignores_taste():
    # Every roll below EXPLORE is an open pick, whether or not artists are followed.
    for roll in (0.0, taste.EXPLORE / 2, taste.EXPLORE - 1e-9):
        assert taste.pick_kind(roll, following=True) == "open"
        assert taste.pick_kind(roll, following=False) == "open"
    assert taste.EXPLORE >= 0.25

    # An open pick is one random draw: no choosing between pieces, no followed artist.
    source = CountingSource()
    steer = taste.Steer([1.0], 0.25, taste.Model(HISTORY), ["Hokusai"])
    draft = asyncio.run(Worker(source, None).pick([11], set(), False, steer, roll=0.0))

    assert draft.meta["pick"] == "open"
    assert (source.drawn, source.asked_for_artist) == (1, 0)


def test_invariant_13_no_piece_is_scored_out_of_reach_and_the_unfamiliar_is_not_marked_down():
    model = taste.Model(HISTORY)
    loved = model.score({"artist": "Hokusai", "subjects": ["Waves"]})
    loathed = model.score({"artist": "Dull", "subjects": ["Trade cards"]})
    new = model.score({"artist": "Never seen", "subjects": ["Volcanoes"], "culture": "Iceland"})

    assert loved > new > loathed
    assert new == 1.0
    assert taste.SCORE_MIN <= loathed and loved <= taste.SCORE_MAX
    # Three pieces are drawn, so the worst possible piece still wins against two of the best.
    assert taste.SCORE_MIN / (taste.SCORE_MIN + 2 * taste.SCORE_MAX) > 0.01


def test_invariant_14_followed_artists_keep_to_their_share_and_are_dropped_when_passed():
    assert taste.followed(HISTORY) == ["Hokusai"]
    # Kept once is not a pattern.
    assert taste.followed(HISTORY + [verdict(True, artist="Once")]) == ["Hokusai"]
    # Passing what following brings is enough to stop it, however many were kept before.
    passed = HISTORY + [verdict(False, artist="Hokusai") for _ in range(taste.DROP_AFTER)]
    assert taste.followed(passed) == []
    assert taste.followed(passed + [verdict(True, artist="Hokusai")]) == ["Hokusai"]

    rolls = [i / 1000 for i in range(1000)]
    share = sum(taste.pick_kind(r, following=True) == "artist" for r in rolls) / 1000
    assert abs(share - taste.FOLLOW) < 0.002 and taste.FOLLOW <= 0.2
    assert not any(taste.pick_kind(r, following=False) == "artist" for r in rolls)


def cleveland_record(**changes) -> dict:
    return {
        "id": 1,
        "type": "Drawing",
        "share_license_status": "CC0",
        "title": "Violette Heymann",
        "creators": [{"description": "Odilon Redon (French, 1840–1916)"}],
        "images": {"print": {"url": "https://cdn.example/1_print.jpg"}},
        **changes,
    }


def smk_record(**changes) -> dict:
    return {
        "id": "1170012495_object",
        "public_domain": True,
        "object_names": [{"name": "Radering"}, {"name": "Grafik"}],
        "image_iiif_id": "https://iip.example/a.jp2",
        "artist": ["Carl Bloch"],
        **changes,
    }


def test_invariant_15_cleveland_and_smk_offer_only_public_domain_pictures():
    draft = cleveland.describe(cleveland_record())
    assert (draft.key, draft.meta["artist"], draft.meta["artist_bio"]) == ("cma-1", "Odilon Redon", "French, 1840–1916")
    assert draft.meta["room"] == 202 and draft.meta["classification"] == "Drawings"
    assert not cleveland.describe(cleveland_record(share_license_status="Copyrighted"))
    assert not cleveland.describe(cleveland_record(type="Ceramic"))
    assert not cleveland.describe(cleveland_record(images={}))

    draft = smk.describe(smk_record())
    assert (draft.key, draft.meta["room"], draft.meta["artist"]) == ("smk-1170012495", 303, "Carl Bloch")
    assert not smk.describe(smk_record(public_domain=False))
    assert not smk.describe(smk_record(object_names=[{"name": "Statue"}]))
    assert not smk.describe(smk_record(image_iiif_id=None))


def test_invariant_16_new_rooms_open_without_reopening_a_room_you_closed(conn):
    # A choice saved before Cleveland and SMK existed: European Paintings only.
    conn.execute("INSERT INTO preference (key, value) VALUES ('rooms', '[11]')")

    rooms = store.rooms(conn)

    assert 11 in rooms and 9 not in rooms  # Drawings and Prints was closed, and stays closed
    assert {*cleveland.Cleveland.ROOMS, *smk.Smk.ROOMS} <= set(rooms)

    # Closing a new room sticks.
    store.set_rooms(conn, [11, 201])
    assert store.rooms(conn) == [11, 201]
