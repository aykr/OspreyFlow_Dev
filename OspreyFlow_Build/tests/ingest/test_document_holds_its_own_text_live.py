"""ADR-127 decision 1 against the real ArcadeDB adapter: three real report rows are loaded through
the engine's run path, and the Documents are read back from the store.

What it adds to `test_document_holds_its_own_text.py`, whose graph is a stand-in: the real adapter's
`upsert_nodes` and `upsert_edges` accept a `Document` written with `object_ref` and `media_kind`
and a `MENTIONED_IN` link to it from a `Person` and from a `Location` (the ontology's own checks,
run in the store), and the Documents come back by title with their text readable from the media
store and the links in. Needs the dev stack's ArcadeDB, like the rest of `tests/ingest` (it runs
under `make test-all`, which names the whole folder; `make test` ignores the folder).
"""

from __future__ import annotations

from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from schemas.domain import ExpandRequest
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_document_holds_its_own_text import (
    LOADER,
    ONTOLOGY,
    _mentions,
    _named,
    _recipe,
    _report_entities,
    _run,
    _seeded,
    real_report_rows,
)


async def test_three_report_rows_load_as_documents_that_hold_their_text_and_are_linked() -> None:
    reports = real_report_rows()
    media = InMemoryMediaStore()
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        await _seeded(reports, graph)
        report = await _run(
            graph, _recipe(_report_entities(), _mentions()), reports, media=media, load_id="live-1"
        )
        assert report.rejections == [], report.rejections
        for row in reports:
            document = await graph.find_node("Document", "title", row["title"], LOADER)
            assert document is not None, row["title"]
            assert document.properties["media_kind"] == "text"
            text = await media.get(str(document.properties["object_ref"]))
            assert text.decode() == row["report_text"]
            around = await graph.expand(
                ExpandRequest(node_ids=[document.id], depth=1, direction="in"), LOADER
            )
            by_id = {n.id: n for n in around.nodes}
            mentions = [e for e in around.edges if e.type == "MENTIONED_IN"]
            assert [e for e in around.edges if e.type == "HOLDS"] == []
            people = sorted(
                str(by_id[e.source].properties["prison_number"])
                for e in mentions
                if by_id[e.source].type == "Person"
            )
            areas = [
                str(by_id[e.source].properties["site_ref"])
                for e in mentions
                if by_id[e.source].type == "Location"
            ]
            assert people == sorted(_named(row))
            assert areas == [row["area_ref"]]
