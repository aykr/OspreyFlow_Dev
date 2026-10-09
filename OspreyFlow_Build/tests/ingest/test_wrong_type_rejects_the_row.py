"""A value the ontology refuses rejects its row; it does not abort the run (found 9 October 2026).

ADR-104 stopped one cause (a structured transform storing its whole result), not the class: any
property whose value does not fit its declared type raised `OntologyError` from the dry run, so
Verify answered 500 and showed nothing, where one bad row in a thousand should be one rejection.
The real load raised the same way, from the graph adapter, part-way through its transaction.

Both now refuse the row while resolving it, before anything is written, with a reason that names
the property and its type, never the value: a date of birth is a sensitive property, and rejection
reasons are shown to people who may not see it (ad39a15).
"""

from __future__ import annotations

import asyncio

from services.ingest.engine import dry_run_recipe, run_recipe

from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import (
    FieldBinding,
    Recipe,
    RecipeConnector,
    RecipeDefaults,
    RecipeEntity,
    RowTemplate,
)
from tests.ingest.test_message_content import LOADER, RecordingGraph

ONTOLOGY = load_default_ontology()
ROWS = [
    {"surname": "HARGREAVE", "born": "1981-04-02"},
    {"surname": "MALLORY", "born": "second of April"},
]


def _recipe() -> Recipe:
    return Recipe(
        id="people",
        version=1,
        label="people",
        connector=RecipeConnector(profile="generic-csv"),
        ontology_version=ONTOLOGY.version,
        defaults=RecipeDefaults(
            handling={
                "classification": "OFFICIAL",
                "handling_code": "P",
                "originator": "unit-1",
                "owning_unit": "unit-1",
            },
            provenance={},
        ),
        row_template=RowTemplate(
            entities=[
                RecipeEntity(
                    ref="p",
                    pole_class="person",
                    type="Person",
                    on_match="create",
                    properties={
                        "family_name": FieldBinding(field="surname"),
                        "date_of_birth": FieldBinding(field="born"),
                    },
                )
            ]
        ),
    )


class _NoGraph:
    async def find_node(self, *args: object, **kwargs: object) -> None:
        return None


def test_the_dry_run_rejects_the_row_and_keeps_the_rest() -> None:
    result = asyncio.run(
        dry_run_recipe(
            _recipe(),
            ROWS,
            graph=_NoGraph(),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            principal=Principal(id="a", clearance="OFFICIAL", org_unit="unit-1"),
            source="people.csv",
        )
    )
    assert [n.properties["family_name"] for n in result.nodes] == ["HARGREAVE"]
    (rejection,) = result.rejections
    assert rejection.row_index == 1
    assert "date_of_birth" in rejection.reason and "date" in rejection.reason
    assert "second of April" not in rejection.reason


def test_the_load_rejects_the_same_row_before_writing_it() -> None:
    graph = RecordingGraph()
    report, _ = asyncio.run(
        run_recipe(
            _recipe(),
            ROWS,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            tx="tx-1",
            principal=LOADER,
            load_id="load-1",
            investigation_scope="case-1",
            source="people.csv",
        )
    )
    assert [n.properties["family_name"] for n in graph.nodes] == ["HARGREAVE"]
    assert [r.row_index for r in report.rejections] == [1]
    assert "second of April" not in report.rejections[0].reason
