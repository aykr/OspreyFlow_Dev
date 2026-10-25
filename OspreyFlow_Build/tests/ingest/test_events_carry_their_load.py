"""ADR-127 decision 6: every analytics event a Studio run writes carries the `load_id` of the run,
so a reverted load's events can be retracted (`AnalyticsPort.retract_load`). What a mistake would
do: an event with no load id could never be found by a revert, and would go on moving a trend for
links the graph no longer holds.

The run is `load_with_rules` against the shared graph stand-in (`recipe_test_support.py`); the
events are what it hands back to be persisted. A held row released later goes through the same
function with the release's own load id, and is stamped the same way."""

from __future__ import annotations

from typing import Any

from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    ValidatingGraph,
    local_staging,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


def _endpoint(ref: str, column: str) -> dict[str, Any]:
    return {
        "ref": ref,
        "pole_class": "object",
        "type": "Endpoint",
        "match_on": "value_normalised",
        "on_match": "reference",
        "properties": {
            "value_normalised": {"field": column},
            "endpoint_kind": {"literal": "account"},
        },
    }


RECIPE = Recipe.model_validate(
    {
        "id": "private-cash",
        "version": 1,
        "label": "Private cash",
        "connector": {"profile": "csv"},
        "ontology_version": ONTOLOGY.version,
        "pack_versions": {},
        "defaults": {
            "provenance": {"state": "asserted"},
            "handling": {
                "classification": "OFFICIAL",
                "handling_code": "P",
                "originator": "unit-1",
                "owning_unit": "unit-1",
            },
        },
        "row_template": {
            "entities": [_endpoint("from", "payer"), _endpoint("to", "payee")],
            "edges": [
                {
                    "type": "TRANSACTED",
                    "from": "from",
                    "to": "to",
                    "temporal": {"at": {"field": "paid_at", "transform": "datetime"}},
                }
            ],
        },
    }
)

ROWS = [
    {"payer": "SYN-1", "payee": "SYN-2", "paid_at": "2026-03-02T09:00:00+00:00"},
    {"payer": "SYN-1", "payee": "SYN-3", "paid_at": "2026-03-03T09:00:00+00:00"},
    {"payer": "SYN-4", "payee": "SYN-2", "paid_at": "2026-03-04T09:00:00+00:00"},
]


async def _run(load_id: str) -> list[Any]:
    graph = ValidatingGraph(ONTOLOGY)
    report, events, _held = await load_with_rules(
        RECIPE,
        ROWS,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope="case-1",
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    assert report.rejections == [], report.rejections
    return list(events)


async def test_every_event_a_run_emits_carries_the_runs_load_id() -> None:
    events = await _run("load-7")
    assert len(events) == 3
    assert {e.load_id for e in events} == {"load-7"}


async def test_two_runs_stamp_their_own_ids_and_not_each_others() -> None:
    first = await _run("load-7")
    second = await _run("load-8")
    assert {e.load_id for e in first} == {"load-7"}
    assert {e.load_id for e in second} == {"load-8"}
