"""ADR-109 Amendment 11 (L2.8c): the pipeline runner gives its enrich stage the alerts' repoint
journal, the alert store of the run's rule gate. The stage's own use of it, an online point's
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


async def test_the_runner_gives_its_enrich_stage_the_rule_gates_alert_store(
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
        rules=SimpleNamespace(alert_store=alert_store),  # type: ignore[arg-type]
    )
    assert given == [alert_store]
