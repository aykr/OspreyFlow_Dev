"""ADR-127 Amendment 23 (B2-10a), "The recipes", "What it refuses first": the seed's method on
`StudioRecipeStore` enters a committed recipe as published only after the checks a publish and a run
make. They are pure, so they are asserted here with a store that has no connection at all: a method
that reached the database before refusing would fail on the missing pool, never on the refusal.

What a mistake would do, and the case that catches it:

- a recipe the rules refuse entered anyway
  (`test_a_recipe_the_rules_refuse_is_refused_before_anything_is_written`);
- an element that loosens the source's marking entered anyway
  (`test_a_recipe_that_loosens_the_sources_marking_is_refused`);
- a pin that is not the ontology's, entered anyway
  (`test_a_recipe_pinned_to_another_pack_version_is_refused`,
  `test_a_recipe_with_no_pins_for_the_packs_it_writes_is_refused`);
- a pin the recipe's own types do not call for (`test_pins_that_differ_from_the_packs_it_writes_are_refused`);
- a recipe made against another ontology (`test_a_recipe_made_against_another_ontology_is_refused`);
- the committed recipes themselves failing a refusal they must pass
  (`test_every_committed_pid_recipe_but_the_reports_passes_every_refusal`)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from services.api.studio_map import HandlingLoosenedError
from services.api.studio_recipes import (
    SeededRecipeNoLegalBasis,
    SeededRecipePinsDiffer,
    StudioRecipeStore,
    check_seeded_recipe,
)
from services.ingest.engine import StaleRecipeError
from services.ingest.recipe_loader import load_recipe
from services.ingest.recipe_rules import RecipeRuleError

from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    Recipe,
)

FIXTURES = Path(__file__).resolve().parents[4] / "OspreyFlow_Core/packages/demo_fixtures"
ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 26, 9, tzinfo=UTC)
#: Every committed PID recipe the seed enters; the reports recipe is entered by the fallback command.
SEEDED = sorted(
    p.name for p in FIXTURES.glob("pid_*_recipe.yaml") if p.name != "pid_intel_reports_recipe.yaml"
)


def recipe(name: str = "pid_conflicts_recipe.yaml") -> Recipe:
    return load_recipe(FIXTURES / name)


def offline_store() -> StudioRecipeStore:
    """A store with no pool: any use of the database raises `AttributeError`."""
    return StudioRecipeStore(None)  # type: ignore[arg-type]


async def enter(rec: Recipe) -> Any:
    return await offline_store().enter_published_for_seed(
        rec, source_location="uploaded/prison-intelligence/x.csv", git_path="recipes/x.yaml",
        dataset_id="prison-intelligence", owning_unit="verify", published_by="pid-seed-worker",
        now=NOW, ontology=ONTOLOGY, scheme=SCHEME,
    )  # fmt: skip


def test_the_committed_recipes_are_the_seventeen_less_the_reports_recipe() -> None:
    assert len(SEEDED) == 16 and "pid_report_incidents_recipe.yaml" in SEEDED


@pytest.mark.parametrize("name", SEEDED)
def test_every_committed_pid_recipe_but_the_reports_passes_every_refusal(name: str) -> None:
    check_seeded_recipe(recipe(name), ONTOLOGY, SCHEME)


async def test_a_recipe_the_rules_refuse_is_refused_before_anything_is_written() -> None:
    rec = recipe()
    broken = rec.model_copy(deep=True)
    broken.row_template.edges[0].type = "NO_SUCH_LINK"
    with pytest.raises(RecipeRuleError):
        await enter(broken)


async def test_a_recipe_that_loosens_the_sources_marking_is_refused() -> None:
    rec = recipe()
    loosened = rec.model_copy(deep=True)
    assert loosened.defaults.handling["classification"] == "OFFICIAL"
    loosened.row_template.entities[0].handling = {"classification": "PUBLIC"}
    with pytest.raises(HandlingLoosenedError):
        await enter(loosened)


async def test_a_recipe_pinned_to_another_pack_version_is_refused() -> None:
    rec = recipe()
    assert rec.pack_versions == {"niem": ONTOLOGY.packs["niem"]}
    stale = rec.model_copy(update={"pack_versions": {"niem": ONTOLOGY.packs["niem"] + 1}})
    with pytest.raises(StaleRecipeError):
        await enter(stale)


async def test_a_recipe_with_no_pins_for_the_packs_it_writes_is_refused() -> None:
    with pytest.raises(StaleRecipeError):
        await enter(recipe().model_copy(update={"pack_versions": None}))
    with pytest.raises(StaleRecipeError):
        await enter(recipe().model_copy(update={"pack_versions": {}}))


async def test_pins_that_differ_from_the_packs_it_writes_are_refused() -> None:
    """A pin the engine ignores (a pack the recipe neither names nor writes) is still a pin the
    publish would never have stamped: the pins are exactly `pack_versions_for`."""
    rec = recipe()
    extra = rec.model_copy(update={"pack_versions": {**(rec.pack_versions or {}), "fibo": 1}})
    with pytest.raises(SeededRecipePinsDiffer) as refused:
        await enter(extra)
    assert rec.id in str(refused.value)


async def test_a_recipe_made_against_another_ontology_is_refused() -> None:
    other = recipe().model_copy(update={"ontology_version": ONTOLOGY.version + 1})
    with pytest.raises(StaleRecipeError):
        await enter(other)


async def test_a_recipe_with_no_legal_basis_is_refused() -> None:
    """Connect requires one, and a row without it is not `ready_for_profile` (Amendment 25)."""
    rec = recipe()
    assert rec.defaults.legal_basis
    for blank in (None, "", "   "):
        stripped = rec.model_copy(deep=True)
        stripped.defaults.legal_basis = blank
        with pytest.raises(SeededRecipeNoLegalBasis):
            await enter(stripped)


async def test_a_recipe_that_passes_gets_as_far_as_the_database() -> None:
    """The control for every case above: with nothing refused, the method does reach the pool, which
    this store does not have. Without it, a method that refused everything would pass them all."""
    with pytest.raises(AttributeError):
        await enter(recipe())


# --- `restore_to_draft` writes the pipeline it is given (ADR-127 Amendment 25) ----------------------
# Pure: a connection stand-in records the statements. The rows, the status flips and the transaction
# are proved live in `test_studio_recipes_store.py`.


class _Tx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


class _RestoreConn:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def transaction(self) -> _Tx:
        return _Tx()

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append((sql, args))

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any]:
        return self.row


class _RestorePool:
    def __init__(self, conn: _RestoreConn) -> None:
        self.conn = conn

    def acquire(self) -> _Tx:
        conn = self.conn

        class _Acquired(_Tx):
            async def __aenter__(self) -> Any:  # type: ignore[override]
                return conn

        return _Acquired()


def _previous_row(pipeline: Any) -> dict[str, Any]:
    import json

    entered = recipe()
    return {
        "recipe_id": "r9", "version": 3, "status": "published", "label": "Reports",
        "content": json.dumps({
            "connector_profile": "generic-csv", "source_location": "uploaded/x.csv",
            "handling": {"classification": "OFFICIAL", "handling_code": "P",
                         "originator": "u", "owning_unit": "u"},
            "legal_basis": "Synthetic demonstration data",
            "row_template": entered.row_template.model_dump(by_alias=True),
            "unmapped_fields": [], "pipeline": pipeline, "deduplicate": None,
        }),
        "owning_unit": "u", "created_by": "a", "created_at": NOW, "verified_at": NOW,
        "ontology_version": 16, "pack_versions": None, "git_path": "recipes/r9.yaml",
        "published_by": "a", "published_at": NOW, "schedule_cron": None, "schedule_watch": None,
        "dataset_id": "prison-intelligence",
    }  # fmt: skip


def _starting() -> PipelineGraph:
    return PipelineGraph(
        nodes=[
            PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model",
                         config={"pack": "niem"}),
            PipelineNode(id="source", kind=PipelineNodeKind.SOURCE, label="Reports",
                         config={"connector_profile": "generic-csv", "source_location": "x.csv"}),
        ],
        edges=[PipelineEdge(source="domain", target="source")],
    )  # fmt: skip


def test_restore_to_draft_takes_the_pipeline_as_a_required_argument() -> None:
    import inspect

    parameter = inspect.signature(StudioRecipeStore.restore_to_draft).parameters["pipeline"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("previous", [None, "other"], ids=["none-before", "another-before"])
async def test_the_restored_draft_is_written_with_the_given_pipeline_and_never_the_previous(
    previous: str | None,
) -> None:
    import json

    other = None if previous is None else _starting().model_copy(deep=True)
    if other is not None:
        other.nodes[1].config["source_location"] = "elsewhere.csv"
    conn = _RestoreConn(
        _previous_row(None if other is None else other.model_dump(by_alias=True, mode="json"))
    )
    store = StudioRecipeStore(_RestorePool(conn))  # type: ignore[arg-type]
    await store.restore_to_draft(
        "r9", created_by="w", owning_unit="verify", now=NOW, pipeline=_starting()
    )
    inserts = [a for sql, a in conn.executed if sql.startswith("INSERT")]
    assert len(inserts) == 1
    content = json.loads(inserts[0][4])
    assert content["pipeline"] == _starting().model_dump(by_alias=True)
    assert content["row_template"] is None and content["unmapped_fields"] == []
    assert content["deduplicate"] is None
    assert inserts[0][1] == 4, "the next version"
    assert any("superseded" in str(a) or "superseded" in sql for sql, a in conn.executed)


# --- "the same content" is the whole row (ADR-127 Amendment 26) -------------------------------------


def _row_as_entered() -> dict[str, Any]:
    import json

    from services.api.studio_recipes import _seeded_content

    rec = recipe()
    return {
        "label": rec.label,
        "content": json.dumps(_seeded_content(rec, "x.csv")),
        "pack_versions": json.dumps(rec.pack_versions or {}),
        "ontology_version": rec.ontology_version,
        "dataset_id": "prison-intelligence",
        "owning_unit": "verify",
        "git_path": "recipes/x.yaml",
        "status": "published",
    }


def _differences(row: dict[str, Any]) -> list[str]:
    from services.api.studio_recipes import _seeded_content, _seeded_row_differences

    rec = recipe()
    return _seeded_row_differences(
        row,  # type: ignore[arg-type]
        label=rec.label, content=_seeded_content(rec, "x.csv"), pack_versions=rec.pack_versions or {},
        ontology_version=rec.ontology_version, dataset_id="prison-intelligence",
        owning_unit="verify", git_path="recipes/x.yaml",
    )  # fmt: skip


def test_a_row_that_is_what_entering_writes_differs_in_nothing() -> None:
    assert _differences(_row_as_entered()) == []


@pytest.mark.parametrize(
    ("column", "stale"),
    [
        ("label", "Another label"),
        ("content", "{}"),
        ("pack_versions", '{"niem": 2}'),
        ("ontology_version", 15),
        ("dataset_id", "another-dataset"),
        ("owning_unit", "another-unit"),
        ("git_path", "recipes/elsewhere.yaml"),
        ("status", "flagged"),
    ],
)
def test_a_row_stale_in_any_one_column_is_named(column: str, stale: Any) -> None:
    assert _differences({**_row_as_entered(), column: stale}) == [column]
