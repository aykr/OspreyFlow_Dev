"""ADR-109 Amendment 11 (L2.8c): the pipeline runner gives its enrich stage the alerts' repoint
journal, the alert store the run is given (`recipe_run` passes its own). The stage's own use of it, an online point's
supersede recording each cloned link, is proved live in
`tests/ingest/test_repoint_journal_callers_live.py`; this proves the runner hands it over."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from services.api import pipeline_run

from schemas.domain import Principal
from schemas.ingest import EnrichStageReport, PipelineGraph

READER = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1")


async def test_the_runner_gives_its_enrich_stage_the_alert_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Violation caught: `run_published_pipeline` running an enrich stage without the alert store
    (`alerts=None`), so an online point's supersede clones links no journal records and an alert
    citing one is withheld for good. Red with the runner's `alerts=` argument removed."""
    alert_store = object()
    given: list[Any] = []

    async def enrich(node: Any, **kwargs: Any) -> tuple[EnrichStageReport, list[str]]:
        given.append(kwargs.get("alerts"))
        return EnrichStageReport(node_id=node.id, geocoder="online_allowlist"), []

    pipeline = PipelineGraph.model_validate(
        {"nodes": [{"id": "enrich", "kind": "enrich", "label": "Geocode"}], "edges": []}
    )
    monkeypatch.setattr(pipeline_run, "pipeline_of", lambda draft, root: pipeline)
    monkeypatch.setattr(pipeline_run, "_run_enrich_stage", enrich)
    draft = SimpleNamespace(recipe_id="r", version=1)
    await pipeline_run.run_published_pipeline(
        draft,  # type: ignore[arg-type]
        READER,
        graph=object(),  # type: ignore[arg-type]
        ontology=object(),  # type: ignore[arg-type]
        scheme=object(),  # type: ignore[arg-type]
        load_id="l",
        investigation_scope="case-1",
        repo_root=None,  # type: ignore[arg-type]
        recogniser_for=lambda name: None,
        alerts=alert_store,  # type: ignore[arg-type]
    )
    assert given == [alert_store]


class _Stop(Exception):
    """Raised by a stand-in once it has seen what it was handed."""


async def test_a_recipe_run_hands_the_runner_its_alert_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """The review's round 2, item 3(a): `recipe_run` passes its own `deps.alerts_store` to the
    pipeline runner, whatever its rule gate. Red with `recipe_run`'s `alerts=` removed: the runner
    was handed `None`."""
    from services.api import recipe_run

    alert_store = object()
    given: dict[str, Any] = {}

    async def runner(*_args: Any, **kwargs: Any) -> Any:
        given.update(kwargs)
        raise _Stop

    async def no_gate(*_args: Any, **_kwargs: Any) -> None:
        return None

    class Deps:
        alerts_store = alert_store

        def __getattr__(self, name: str) -> Any:
            return None

    monkeypatch.setattr(recipe_run, "run_published_pipeline", runner)
    monkeypatch.setattr(recipe_run, "_rule_gate", no_gate)
    recipe = SimpleNamespace(pipeline=object(), recipe_id="r")
    with pytest.raises(_Stop):
        await recipe_run._execute_recipe_run(
            Deps(),  # type: ignore[arg-type]
            principal=READER,
            recipe=recipe,  # type: ignore[arg-type]
            investigation_id="case-1",
            source_location=None,
            trigger="manual",  # type: ignore[arg-type]
            sink=None,  # type: ignore[arg-type]
        )
    assert given["alerts"] is alert_store


async def test_the_conduits_graph_passes_each_clone_report_to_the_adapter() -> None:
    """The review's round 2, item 3(b): the routes and the runner write through the dataset-stamping
    graph (`dataset_scope.stamping`), which must hand `on_link_cloned` to the adapter, or every
    clone a correction makes through the Conduit goes unrecorded. Red with the wrapper's
    `on_link_cloned=` removed: the adapter was handed `None`."""
    from services.api.dataset_scope import stamping

    from schemas.domain import Node, NodeWrite

    given: list[Any] = []

    class Adapter:
        async def get_nodes(self, ids: Any, reader: Any) -> list[Node]:
            return []

        async def supersede_node(self, node_id: str, replacement: NodeWrite, tx: Any, *,
                                 on_link_cloned: Any = None) -> str:  # fmt: skip
            given.append(on_link_cloned)
            return replacement.id

    async def report(old: str, new: str, old_type: str) -> None:
        return None

    graph = stamping(Adapter(), dataset="dataset-1")  # type: ignore[arg-type]
    replacement = NodeWrite.model_validate({
        "id": "n-2", "type": "Person", "properties": {}, "created_by": "t", "created_at": "2026-11-08T00:00:00Z",
        "provenance": {"state": "asserted", "first_seen": "2026-11-08T00:00:00Z",
                       "sources": [{"document_id": "d", "locator": "l", "excerpt_hash": ""}]},
        "handling": {"classification": "OFFICIAL", "handling_code": "P", "originator": "u", "owning_unit": "u"},
    })  # fmt: skip
    await graph.supersede_node("n-1", replacement, "tx", on_link_cloned=report)
    assert given == [report]
