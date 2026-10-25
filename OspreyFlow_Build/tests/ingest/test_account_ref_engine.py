"""ADR-127 decision 4's own acceptance: three spellings of one account, in a recipe whose `Endpoint`
(kind `account`) is matched on the `account_ref` transform's output, give **one** `Endpoint`.

What a mistake would do: an adapter that did not canonicalise would leave the three spellings as
three nodes for one account, which no later query could tell are the same. The run is `load_with_rules`
against the shared graph stand-in (`recipe_test_support.py`), which refuses what the real store
refuses, so a recipe the ontology would not accept fails here too. The adapter's own cases are
`tests/knowledge_adapters/test_account_ref.py`."""

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

THREE_SPELLINGS = ["SYN-70417", " syn-70417 ", "Syn- 70417"]


def _recipe(transform: str | None = "account_ref") -> Recipe:
    value: dict[str, Any] = {"field": "account"}
    if transform:
        value["transform"] = transform
    return Recipe.model_validate(
        {
            "id": "prison-private-cash",
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
                "entities": [
                    {
                        "ref": "acct",
                        "pole_class": "object",
                        "type": "Endpoint",
                        "match_on": "value_normalised",
                        "on_match": "reference",
                        "properties": {
                            "value_normalised": value,
                            "value_raw": {"field": "account"},
                            "endpoint_kind": {"literal": "account"},
                        },
                    }
                ],
                "edges": [],
            },
        }
    )


async def _load(recipe: Recipe, spellings: list[str]) -> tuple[Any, ValidatingGraph]:
    graph = ValidatingGraph(ONTOLOGY)
    report, _events, _held = await load_with_rules(
        recipe,
        [{"account": s} for s in spellings],
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope="case-1",
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    return report, graph


def _endpoints(graph: ValidatingGraph) -> list[Any]:
    return [n for n in graph.committed_nodes if n.type == "Endpoint"]


async def test_three_spellings_of_one_account_give_one_endpoint() -> None:
    report, graph = await _load(_recipe(), THREE_SPELLINGS)
    assert report.rejections == [], report.rejections
    endpoints = _endpoints(graph)
    assert len(endpoints) == 1
    assert endpoints[0].properties["value_normalised"] == "SYN-70417"
    assert endpoints[0].properties["endpoint_kind"] == "account"


async def test_two_different_accounts_stay_two_endpoints() -> None:
    _report, graph = await _load(_recipe(), ["SYN-70417", "syn-00988", " SYN-70417"])
    assert sorted(n.properties["value_normalised"] for n in _endpoints(graph)) == [
        "SYN-00988",
        "SYN-70417",
    ]


async def test_a_value_the_adapter_refuses_rejects_its_row_and_loads_the_rest() -> None:
    report, graph = await _load(_recipe(), ["SYN-70417", "SYN#99"])
    assert len(report.rejections) == 1
    assert "SYN#99" not in str(report.rejections[0].reason)
    assert [n.properties["value_normalised"] for n in _endpoints(graph)] == ["SYN-70417"]


async def test_without_the_transform_the_spellings_are_not_one_account() -> None:
    # The control: the same rows with no canonicalising give the spellings as they were typed, so
    # the single Endpoint above is the adapter's doing and not the engine's.
    _report, graph = await _load(_recipe(transform=None), THREE_SPELLINGS)
    assert len(_endpoints(graph)) > 1
