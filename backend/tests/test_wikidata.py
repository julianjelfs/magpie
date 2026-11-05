"""Invariant 10: a modern painting is offered only once its artist is out of copyright."""

from __future__ import annotations

import asyncio
from datetime import date

from app import wikidata
from app.wikidata import Wikidata, paintings_from, public_domain


def test_invariant_10_only_artists_dead_more_than_70_years_are_offered(monkeypatch, tmp_path):
    # UK: public domain from 1 January of the 71st year after death.
    assert public_domain(1955, date(2026, 1, 1))
    assert not public_domain(1956, date(2026, 12, 31))
    assert public_domain(1956, date(2027, 1, 1))

    monkeypatch.setattr(
        wikidata,
        "ARTISTS",
        [
            {"name": "Old", "qid": "Q1", "born": 1860, "died": 1920, "nationality": "", "group": ""},
            {"name": "Recent", "qid": "Q2", "born": 1900, "died": 1990, "nationality": "", "group": ""},
        ],
    )

    class Fake(Wikidata):
        async def paintings(self, artist):
            return [{"qid": f"Q{artist['qid'][1:]}0", "title": "A painting", "file": "a.jpg", "year": 1910, "collection": ""}]

    drafts = {asyncio.run(Fake(None, tmp_path).random_draft(set())).meta["artist"] for _ in range(20)}

    assert drafts == {"Old"}


def test_paintings_without_an_english_title_are_untitled_not_a_bare_id():
    rows = [
        {
            "p": {"value": "http://www.wikidata.org/entity/Q42"},
            "pLabel": {"value": "Q42"},
            "img": {"value": "http://commons.wikimedia.org/wiki/Special:FilePath/A%20b.jpg"},
            "made": {"value": "1912-01-01T00:00:00Z"},
        }
    ]
    [p] = paintings_from(rows)
    assert p["title"] == "" and p["file"] == "A b.jpg" and p["year"] == 1912
