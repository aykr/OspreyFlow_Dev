"""ADR-127 Amendment 37 against the real ArcadeDB adapter: a load that references a report by its
`message_id` finds the report an earlier load wrote, and makes none of its own.

Found live on the owner's deployment (Amendment 36): the report incidents (R17) reference R9's reports
with `match_on: message_id`, and `find_node` looks a reference up only by a type's identifiers and its
indexed properties. `Document.message_id` was neither, so every lookup missed and R17 made 253 empty
reports. The engine's other tests resolve references in a stand-in graph that matches on any property,
which is why nothing caught it (rule 15): this one runs in the store. Needs the dev stack's ArcadeDB,
like the rest of `tests/ingest`.
"""

from __future__ import annotations

from typing import Any

from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_document_holds_its_own_text import (
    ONTOLOGY,
    _document,
    _recipe,
    _run,
    _seeded,
    real_report_rows,
)


def _report_written_with_its_id() -> dict[str, Any]:
    """R9's report: its own text, its title and its id (`message_id`, bound to `report_ref`)."""
    document = _document()
    document["properties"]["message_id"] = {"field": "report_ref"}
    return document


def _report_referenced_by_its_id() -> dict[str, Any]:
    """R17's report: found by `message_id`, never written."""
    return {
        "ref": "report",
        "pole_class": "object",
        "type": "Document",
        "match_on": "message_id",
        "on_match": "reference",
        "properties": {"message_id": {"field": "report_ref"}},
    }


async def test_a_second_load_finds_each_report_by_its_id_and_makes_no_report_of_its_own() -> None:
    reports = real_report_rows()
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        await _seeded(reports, graph)
        written = await _run(
            graph,
            _recipe([_report_written_with_its_id()], []),
            reports,
            media=InMemoryMediaStore(),
            load_id="live-r9",
        )
        assert written.rejections == [], written.rejections
        assert written.nodes_created == len(reports)

        referenced = await _run(
            graph, _recipe([_report_referenced_by_its_id()], []), reports, load_id="live-r17"
        )
        assert referenced.nodes_created == 0, "a report found by its id is never made again"
        assert referenced.nodes_referenced == len(reports)
