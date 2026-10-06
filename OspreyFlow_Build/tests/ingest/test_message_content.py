"""ADR-094 step 1: a recipe marks a column as a link's message text, and each row's text becomes
readable on that link's event, exactly where an Enron email's excerpt is, so *Show messages*, the
reader and extraction work on it. What a mistake would do, and the case that catches it:

- the text written onto the graph link, where the ontology refuses an undeclared property and the
  graph would hold every message body (`test_the_text_is_on_the_event_and_never_on_the_link`);
- a long message stored whole with nothing said, or cut with nothing said
  (`test_a_long_message_is_cut_at_the_excerpt_length_and_says_so`);
- content on a link with no time, which has no event to carry it
  (`test_content_on_a_link_with_no_time_is_refused`).

The graph stand-in runs the ArcadeDB adapter's own `validate_properties` on every write (rule 15:
a fake refuses what the real store refuses)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from services.ingest.engine import run_recipe
from services.ingest.recipe_rules import recipe_rule_violations

from ontology.loader import load_default_ontology
from ontology.validation import validate_properties
from schemas.domain import EdgeWrite, NodeWrite, Principal
from schemas.ingest import Recipe

ONTOLOGY = load_default_ontology()
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1")


class RecordingGraph:
    def __init__(self) -> None:
        self.nodes: list[NodeWrite] = []
        self.edges: list[EdgeWrite] = []

    async def find_node(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: object) -> list[str]:
        for n in nodes:
            validate_properties(ONTOLOGY.entity_type(n.type), n.properties)  # type: ignore[arg-type]
        self.nodes.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: object) -> list[str]:
        for e in edges:
            validate_properties(ONTOLOGY.edge_type(e.type), e.properties)  # type: ignore[arg-type]
        self.edges.extend(edges)
        return [e.id for e in edges]


def sms_recipe(*, temporal: bool = True) -> Recipe:
    edge: dict[str, Any] = {
        "type": "COMMUNICATED_WITH",
        "from": "a",
        "to": "b",
        "content": {"kind": "message_text", "field": "text"},
        "properties": {"direction": {"literal": "outbound"}},
    }
    if temporal:
        edge["temporal"] = {"at": {"field": "sent_at", "transform": "datetime(tz=UTC)"}}

    def endpoint(ref: str, column: str) -> dict[str, Any]:
        return {
            "ref": ref,
            "pole_class": "object",
            "type": "Endpoint",
            "properties": {
                "value_raw": {"field": column},
                "value_normalised": {"field": column, "transform": "msisdn"},
                "endpoint_kind": {"literal": "msisdn"},
            },
        }

    return Recipe.model_validate(
        {
            "id": "sms",
            "version": 1,
            "label": "SMS",
            "connector": {"profile": "csv"},
            "ontology_version": ONTOLOGY.version,
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
                "entities": [endpoint("a", "from"), endpoint("b", "to")],
                "edges": [edge],
            },
        }
    )


def row(text: str) -> dict[str, str]:
    return {
        "from": "01621926368",
        "to": "07911123456",
        "sent_at": "2026-01-10T10:00:00Z",
        "text": text,
    }


async def _run(rows: list[dict[str, str]]) -> tuple[RecordingGraph, list[Any]]:
    graph = RecordingGraph()
    _, events = await run_recipe(
        sms_recipe(),
        iter(rows),
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx="tx-1",  # type: ignore[arg-type]
        principal=LOADER,
        load_id="load-1",
        investigation_scope="case-1",
        source="sms.csv",
    )
    return graph, events


async def test_the_text_is_on_the_event_and_never_on_the_link() -> None:
    graph, events = await _run([row("Meet at the yard at six.")])
    (event,) = events
    assert event.properties["excerpt"] == "Meet at the yard at six."
    assert event.properties["content_kind"] == "message_text"
    assert event.properties["truncated"] is False
    assert all("excerpt" not in e.properties and "text" not in e.properties for e in graph.edges)


async def test_a_long_message_is_kept_whole() -> None:
    """ADR-095 decision 5: a recipe's text is kept whole, as an email is; no 4,000-character cut."""
    _, events = await _run([row("x" * 41_000)])
    (event,) = events
    assert len(event.properties["excerpt"]) == 41_000
    assert event.properties["truncated"] is False


async def test_an_empty_message_carries_no_text() -> None:
    _, events = await _run([row("")])
    (event,) = events
    assert "excerpt" not in event.properties


def test_content_on_a_link_with_no_time_is_refused() -> None:
    (problem,) = recipe_rule_violations(sms_recipe(temporal=False).row_template, ONTOLOGY)
    assert "COMMUNICATED_WITH" in problem and "time" in problem


async def test_the_synthetic_sms_load_through_their_recipe_with_their_text() -> None:
    """The demo's own messages (ADR-094 decision 7), through the recipe the Studio would build."""
    from pathlib import Path

    from services.ingest.recipe_loader import load_recipe

    from demo_fixtures.sms import generate_sms_rows

    recipe = load_recipe(
        Path(__file__).resolve().parents[1] / "scenarios" / "fixtures" / "sms_recipe.yaml"
    )
    rows = generate_sms_rows()
    graph = RecordingGraph()
    report, events = await run_recipe(
        recipe,
        iter(rows),
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx="tx-1",  # type: ignore[arg-type]
        principal=LOADER,
        load_id="load-1",
        investigation_scope="case-1",
        source="sms.csv",
    )
    assert report.rejections == []
    assert len(events) == len(rows)
    assert {e.properties["excerpt"] for e in events} == {r["text"] for r in rows}
