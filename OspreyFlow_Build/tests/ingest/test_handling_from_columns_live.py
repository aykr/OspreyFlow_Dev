"""ADR-127 decision 3 against the real stores: Brief 1's real report rows are loaded with their
handling read from the file's own six columns, and the markings are read back from the store; a
draft keeps what its source declares through a PATCH (real Postgres); and a held row is stored at
its own row's marking and hidden from a reader below it (real rule gate, held-row store, ArcadeDB).

What it adds to `test_handling_from_columns.py`, whose graph is a stand-in: the adapter's own
`upsert_nodes` accepts the per-row markings (`merge_handling`, `validate_properties`), and the
store's access filter (rule 3) then hides a SECRET row from an OFFICIAL reader and shows every row
to a SECRET one. Needs the dev stack's ArcadeDB, like the rest of `tests/ingest` (it runs under
`make test-all`; `make test` ignores the folder).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from services.api.config import PostgresConfig
from services.api.held_rows import HeldRowNotFoundError
from services.api.studio_recipes import SourceDeclarationsInvalidError, StudioRecipeStore

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from schemas.domain import Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_handling_from_columns import (
    FIELDS,
    LOADER,
    ONTOLOGY,
    SCHEME,
    _bound,
    _recipe,
    _run,
    real_rows,
)
from tests.ingest.test_typology_rules import (  # noqa: F401 (the fixtures)
    ANALYST,
    SECRET_LOADER,
    _deposits,
    _gate,
    _load,
    _Outage,
    _structuring,
    stores,
)
from tests.ingest.test_typology_rules import ONTOLOGY as DEPLOYMENT_ONTOLOGY
from tests.ingest.test_typology_rules import (
    RECIPE as LEDGER_RECIPE,
)


async def test_the_reports_files_own_markings_are_stored_and_enforced() -> None:
    rows = real_rows()
    plain = [r for r in rows if not r["action_code"] and not r["sanitisation_code"]][:2]
    s2 = next(r for r in rows if r["sanitisation_code"] == "S2")
    a1 = next(r for r in rows if r["action_code"] == "A1")
    secret = {**plain[0], "title": plain[0]["title"] + " (secret)", "classification": "SECRET"}
    loaded = [*plain, s2, a1, secret]
    units = sorted({r["originator"] for r in loaded} | {r["owning_unit"] for r in loaded})
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        report, _ = await _run(_recipe(_bound(*FIELDS), units=units), loaded, graph)  # type: ignore[arg-type]
        assert report.rejections == [], report.rejections
        secret_reader = Principal(id="reader-s", clearance="SECRET", org_unit=LOADER.org_unit)
        official_reader = Principal(id="reader-o", clearance="OFFICIAL", org_unit=LOADER.org_unit)
        for row in loaded:
            node = await graph.find_node("Document", "title", row["title"], secret_reader)
            assert node is not None, row["title"]
            marking = node.handling
            assert marking.classification == (row["classification"] or "OFFICIAL")
            assert marking.action_code == (row["action_code"] or None)
            assert marking.sanitisation_code == (row["sanitisation_code"] or None)
            assert (marking.originator, marking.owning_unit) == (
                row["originator"],
                row["owning_unit"],
            )
            seen = await graph.find_node("Document", "title", row["title"], official_reader)
            assert (seen is not None) == (marking.classification != "SECRET"), row["title"]


# --- the draft keeps its source's declarations through a PATCH (real Postgres) --------------------

AUTHOR = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_author"])
BASE = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


@pytest.fixture
async def recipe_store() -> AsyncIterator[StudioRecipeStore]:
    store = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()


async def test_a_patched_handling_keeps_the_units_and_columns_the_source_declared(
    recipe_store: StudioRecipeStore,
) -> None:
    declared = {"classification": "grade"}
    draft = await recipe_store.create_draft(
        AUTHOR,
        label="Declarations",
        connector_profile="generic-csv",
        source_location=None,
        handling={**BASE, "units": ["unit-1", "unit-2"], "handling_columns": declared},
        legal_basis=None,
    )
    patched = await recipe_store.update_draft(
        draft.recipe_id, AUTHOR, handling={**BASE, "classification": "OFFICIAL-SENSITIVE"}
    )
    read_back = await recipe_store.get(draft.recipe_id)
    for seen in (patched, read_back):
        assert seen.handling["classification"] == "OFFICIAL-SENSITIVE"
        assert seen.handling["units"] == ["unit-1", "unit-2"]
        assert seen.handling["handling_columns"] == declared
    cleared = await recipe_store.update_draft(
        draft.recipe_id, AUTHOR, handling={**BASE, "units": [], "handling_columns": {}}
    )
    assert cleared.handling["units"] == [] and cleared.handling["handling_columns"] == {}


async def test_a_patch_emptying_the_units_a_kept_unit_column_needs_is_refused_and_stores_nothing(
    recipe_store: StudioRecipeStore,
) -> None:
    draft = await recipe_store.create_draft(
        AUTHOR,
        label="Unit column",
        connector_profile="generic-csv",
        source_location=None,
        handling={**BASE, "units": ["unit-1"], "handling_columns": {"owning_unit": "unit"}},
        legal_basis=None,
    )
    with pytest.raises(SourceDeclarationsInvalidError, match="units"):
        await recipe_store.update_draft(draft.recipe_id, AUTHOR, handling={**BASE, "units": []})
    unchanged = await recipe_store.get(draft.recipe_id)
    assert unchanged.handling["units"] == ["unit-1"]
    assert unchanged.handling["handling_columns"] == {"owning_unit": "unit"}


# --- a held row is stored at its own row's marking (real rule gate and held-row store) ------------


def _ledger_with_a_bound_classification() -> Recipe:
    body: dict[str, Any] = LEDGER_RECIPE.model_dump(by_alias=True)
    bound = {"classification": {"field": "classification"}}
    # Connect declares the column, so every entity and link binds it: the link every row writes,
    # and the two accounts, which are matched by reference but created at their own marking on a
    # miss. (A matched account keeps the marking it has; binding it is harmless.)
    (link,) = body["row_template"]["edges"]
    link["handling"] = dict(bound)
    for entity in body["row_template"]["entities"]:
        entity["handling"] = dict(bound)
    body["defaults"]["handling_columns"] = {"classification": "classification"}
    return Recipe.model_validate(body)


def test_the_held_row_recipe_satisfies_the_declared_column_rule() -> None:
    """Pure: the recipe the held-row test loads is accepted by the rule that refuses a declared
    column an element the row writes does not bind, so that test exercises the hold, not the
    refusal."""
    from services.ingest.recipe_rules import recipe_rule_violations

    recipe = _ledger_with_a_bound_classification()
    assert (
        recipe_rule_violations(
            recipe.row_template,
            DEPLOYMENT_ONTOLOGY,
            declared_columns=recipe.defaults.handling_columns,
        )
        == []
    )


async def test_a_held_row_is_stored_at_its_rows_marking_and_hidden_from_an_official_reader(
    stores: dict[str, Any],  # noqa: F811
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
    rows = [
        {**row, "classification": cell}
        for row, cell in zip(_deposits("H"), ["", "SECRET", "", ""], strict=True)
    ]
    async with arcadedb_adapter(DEPLOYMENT_ONTOLOGY, SCHEME) as graph:
        # The analytics store is down, so the pre-commit rule cannot judge the rows and fails
        # closed: every row is held, none loaded (the same stand-in `test_typology_rules` uses).
        gate = _gate(stores, graph, _Outage(), [rule], case, loader=SECRET_LOADER)
        report = await _load(
            graph,
            _Outage(),  # type: ignore[arg-type]
            gate,
            rows,
            recipe=_ledger_with_a_bound_classification(),
            loader=SECRET_LOADER,
        )
        assert report.rows_held == 4 and report.nodes_created == 0
        held = await stores["held"].list_authorized(case, SECRET_LOADER)
        marks = {h.row_index: h.handling.classification for h in held}
        assert marks == {0: "OFFICIAL", 1: "SECRET", 2: "OFFICIAL", 3: "OFFICIAL"}
        # An OFFICIAL reader is not shown the SECRET row, in the list or by its id (rule 4).
        official_sees = {h.row_index for h in await stores["held"].list_authorized(case, ANALYST)}
        assert official_sees == {0, 2, 3}
        secret_row = next(h for h in held if h.row_index == 1)
        with pytest.raises(HeldRowNotFoundError):
            await stores["held"].get_authorized(secret_row.id, case, ANALYST)


async def test_the_resets_revert_then_rerun_of_a_content_load_is_readable_and_created() -> None:
    """ADR-127 Amendment 6 against the real store. The demo reset reverts a load that wrote a
    content `Document` (`content:<sha>`) and runs it again. In the store the revert hides the node,
    the rerun's write replaces it (it is live again, with the rerun's body), and
    `existing_node_ids` leaves it out, so the rerun records it as created and a second revert would
    take it back. The ledger and the analytics store are the stand-ins of `test_revert_load.py`."""
    from datetime import UTC, datetime

    from services.api.studio_publish import load_with_rules
    from services.ingest.load_ledger import load_record_from_report
    from services.ingest.load_revert import RevertDeps, revert

    from adapters.media_objectstore.testing import InMemoryMediaStore
    from tests.ingest.test_load_record_created_and_merged import _recipe as content_recipe
    from tests.ingest.test_revert_load import (
        Alerts,
        Analytics,
        Audit,
        Held,
        Ledger,
        Steps,
        WorkingSets,
        no_caches,
    )

    now = datetime(2026, 10, 25, tzinfo=UTC)
    reader = Principal(id="reader-s", clearance="SECRET", org_unit=LOADER.org_unit)

    async def load(graph: Any, load_id: str, day: int) -> Any:
        report, _events, _held = await load_with_rules(
            content_recipe(content=True),
            [
                {
                    "payer": f"SYN-{load_id}-1",
                    "payee": f"SYN-{load_id}-2",
                    "paid_at": f"2026-03-0{day}T09:00:00+00:00",
                    "memo": "the same note both times",
                }
            ],
            LOADER,
            graph=graph,
            ontology=ONTOLOGY,
            load_id=load_id,
            investigation_scope="case-1",
            source="private_cash.csv",
            media=InMemoryMediaStore(),
            rules=None,
            scheme=SCHEME,
        )
        assert report.rejections == [], report.rejections
        return report

    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        first = await load(graph, new_id(), 1)
        (document,) = [i for i in first.created_node_ids if i.startswith("content:")]
        assert [n.id for n in await graph.get_nodes([document], reader)] == [document]

        record = load_record_from_report(
            first, source="private_cash.csv", created_by=LOADER.id, started_at=now, now=now
        )
        steps = Steps()
        deps = RevertDeps(
            ledger=Ledger(record),
            graph=graph,  # type: ignore[arg-type]
            analytics=Analytics(steps),  # type: ignore[arg-type]
            held_rows=Held(steps),
            alerts=Alerts(steps),
            audit=Audit(steps),
            working_sets=WorkingSets(steps),
            invalidate_caches=no_caches,
        )
        await revert(record.load_id, reverted_by="operator-1", deps=deps, now=now)
        assert await graph.get_nodes([document], reader) == [], "hidden by the revert"
        assert await graph.existing_node_ids([document]) == set()

        second = await load(graph, new_id(), 2)
        assert document in second.created_node_ids and document not in second.merged_node_ids
        assert [n.id for n in await graph.get_nodes([document], reader)] == [document]
        assert second.merged_edge_ids == [], "the reverted links were not merged into"
