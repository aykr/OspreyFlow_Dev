"""Verify's dry run (`spec/09_INGEST_STUDIO.md` §5) —
`services/ingest/engine.py`'s `dry_run_recipe`, against a live ArcadeDB the
same way `test_recipe_engine_end_to_end.py` exercises `run_recipe`.

The load-bearing property under test throughout: **no persistent write ever
happens**, and an `on_match: reference` lookup goes through the ordinary
`GraphPort.find_node` under the *requesting* principal — so a principal who
cannot see a matching node gets exactly the same `None` any other read would
give them, and the dry run reports that entity as "would create," never as
evidence that a higher-classification match exists.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from services.ingest.connectors.csv_connector import read_csv
from services.ingest.engine import dry_run_recipe, run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.errors import OntologyError
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import (
    FieldBinding,
    Recipe,
    RecipeConnector,
    RecipeDefaults,
    RecipeEdge,
    RecipeEntity,
    RowTemplate,
)

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

_ENDPOINT_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


def _endpoint_recipe(*, classification: str = "OFFICIAL", ontology_version: int) -> Recipe:
    return Recipe(
        id="recipe-verify-1",
        version=1,
        label="Endpoint seed",
        connector=RecipeConnector(profile="generic-csv"),
        ontology_version=ontology_version,
        defaults=RecipeDefaults(handling={**_ENDPOINT_HANDLING, "classification": classification}),
        row_template=RowTemplate(
            entities=[
                RecipeEntity(
                    ref="a",
                    pole_class="object",
                    type="Endpoint",
                    match_on="value_normalised",
                    on_match="reference",
                    properties={
                        "value_raw": FieldBinding(field="a_party"),
                        "value_normalised": FieldBinding(field="a_party", transform="msisdn"),
                        "endpoint_kind": FieldBinding(literal="msisdn"),
                    },
                )
            ]
        ),
    )


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


async def test_dry_run_matches_the_real_loads_own_counts_but_writes_nothing(
    tmp_path: Path,
) -> None:
    """Same fixture, same expected numbers as
    `test_recipe_engine_end_to_end.py`'s `test_cdr_fixture_loads_through_a_
    hand_written_recipe` — a dry run against a fresh graph resolves
    identically to a real load (in-sample references still count as
    "referenced", exactly like `_write_entity`'s own `local_index` cache),
    except that nothing lands in the graph afterwards."""
    from tests.scenarios.fixtures.cdr import generate_cdr_rows

    rows = generate_cdr_rows()
    csv_path = _write_csv(tmp_path / "cdr.csv", rows)
    recipe = load_recipe(FIXTURES / "cdr_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        result = await dry_run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            principal=CLEARED,
            source=str(csv_path),
        )

        assert result.rows_read == 10
        assert result.rows_deduplicated == 4
        assert len(result.rejections) == 1
        assert "datetime" in result.rejections[0].reason

        assert result.entities_by_type["Endpoint"].created == 2
        assert result.entities_by_type["Endpoint"].referenced == 8
        (edge,) = result.edges
        assert edge.occurrences == 5

        # The actual "no persistent writes" guarantee: nothing this dry run
        # resolved is retrievable afterwards.
        assert (
            await graph.find_node("Endpoint", "value_normalised", "+441621926368", CLEARED)
            is None
        )


async def test_a_lower_clearance_principals_dry_run_never_sees_a_higher_classification_match(
    tmp_path: Path,
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    high = Principal(id="analyst-high", clearance="SECRET", org_unit="unit-1")
    low = Principal(id="analyst-low", clearance="OFFICIAL", org_unit="unit-1")

    seed_csv = _write_csv(tmp_path / "seed.csv", [{"a_party": "+447911123456"}])

    async with arcadedb_adapter(ontology, scheme) as graph:
        seed_recipe = _endpoint_recipe(classification="SECRET", ontology_version=ontology.version)
        tx = await graph.begin_transaction()
        await run_recipe(
            seed_recipe,
            read_csv(seed_csv),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=high,
            load_id="seed-load",
            investigation_scope="case-verify-acl",
            source=str(seed_csv),
        )
        await graph.commit_transaction(tx)
        real_node = await graph.find_node("Endpoint", "value_normalised", "+447911123456", high)
        assert real_node is not None

        # The low-clearance principal's dry run must show "would create" —
        # never "referenced" — and must never return the real node's id.
        low_result = await dry_run_recipe(
            seed_recipe,
            read_csv(seed_csv),
            graph=graph,
            ontology=ontology,
            principal=low,
            source=str(seed_csv),
        )
        assert low_result.entities_by_type["Endpoint"].created == 1
        assert low_result.entities_by_type["Endpoint"].referenced == 0
        (low_node,) = low_result.nodes
        assert low_node.id != real_node.id
        assert low_node.id in low_result.created_node_ids

        # Control: the high-clearance principal's own dry run correctly
        # references the real node it can see.
        high_result = await dry_run_recipe(
            seed_recipe,
            read_csv(seed_csv),
            graph=graph,
            ontology=ontology,
            principal=high,
            source=str(seed_csv),
        )
        assert high_result.entities_by_type["Endpoint"].created == 0
        assert high_result.entities_by_type["Endpoint"].referenced == 1
        (high_node,) = high_result.nodes
        assert high_node.id == real_node.id
        assert high_node.id not in high_result.created_node_ids


async def test_dry_run_merges_same_pair_edges_and_counts_occurrences(tmp_path: Path) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    csv_path = _write_csv(
        tmp_path / "pairs.csv",
        [
            {"a_party": "+447911123456", "b_party": "+442071234567"},
            {"a_party": "+447911123456", "b_party": "+442071234567"},
            {"a_party": "+447911123456", "b_party": "+442071234567"},
        ],
    )
    recipe = Recipe(
        id="recipe-verify-2",
        version=1,
        label="Pair seed",
        connector=RecipeConnector(profile="generic-csv"),
        ontology_version=ontology.version,
        defaults=RecipeDefaults(handling=_ENDPOINT_HANDLING),
        row_template=RowTemplate(
            entities=[
                RecipeEntity(
                    ref="a",
                    pole_class="object",
                    type="Endpoint",
                    match_on="value_normalised",
                    on_match="reference",
                    properties={
                        "value_normalised": FieldBinding(field="a_party", transform="msisdn"),
                    },
                ),
                RecipeEntity(
                    ref="b",
                    pole_class="object",
                    type="Endpoint",
                    match_on="value_normalised",
                    on_match="reference",
                    properties={
                        "value_normalised": FieldBinding(field="b_party", transform="msisdn"),
                    },
                ),
            ],
            edges=[
                RecipeEdge.model_validate({"type": "COMMUNICATED_WITH", "from": "a", "to": "b"})
            ],
        ),
    )

    async with arcadedb_adapter(ontology, scheme) as graph:
        result = await dry_run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            principal=CLEARED,
            source=str(csv_path),
        )
        assert result.edges_by_type["COMMUNICATED_WITH"].created == 1
        (edge,) = result.edges
        assert edge.occurrences == 3


async def test_dry_run_rejects_an_undeclared_entity_type_the_same_way_a_real_load_would(
    tmp_path: Path,
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    csv_path = _write_csv(tmp_path / "bad.csv", [{"a_party": "+447911123456"}])
    recipe = Recipe(
        id="recipe-verify-3",
        version=1,
        label="Bad type",
        connector=RecipeConnector(profile="generic-csv"),
        ontology_version=ontology.version,
        defaults=RecipeDefaults(handling=_ENDPOINT_HANDLING),
        row_template=RowTemplate(
            entities=[
                RecipeEntity(
                    ref="a",
                    pole_class="object",
                    type="NoSuchType",
                    properties={"value_normalised": FieldBinding(field="a_party")},
                )
            ]
        ),
    )

    async with arcadedb_adapter(ontology, scheme) as graph:
        with pytest.raises(OntologyError):
            await dry_run_recipe(
                recipe,
                read_csv(csv_path),
                graph=graph,
                ontology=ontology,
                principal=CLEARED,
                source=str(csv_path),
            )
