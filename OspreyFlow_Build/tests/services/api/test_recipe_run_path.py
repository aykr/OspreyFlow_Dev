"""ADR-110 decision 1: one run path. The run route and the scheduler both call `run_recipe_as`,
with the same dependencies — so a scheduled load is judged by the case's rules, published to the
change stream, checked against watches and resolved exactly as a manual run is. No second loader.

The scheduler gets its dependencies from the application's state, the route from FastAPI; the
first case fails if the two ever name different things."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Any

import pytest
import services.api.app as app_module
from services.api.app import RecipeRunDeps, run_studio_recipe

#: The state attribute each run dependency is read from, as the route's own getters read it.
STATE_NAMES = {
    "recipe_repo_root": "recipes_repo_root",
    "recogniser_for": "pipeline_recogniser_for",
}


def test_the_scheduler_reads_every_run_dependency_from_where_the_route_does() -> None:
    fields = [f.name for f in dataclasses.fields(RecipeRunDeps)]
    state = SimpleNamespace(**{STATE_NAMES.get(name, name): object() for name in fields})
    deps = RecipeRunDeps.from_state(state)
    for name in fields:
        assert getattr(deps, name) is getattr(state, STATE_NAMES.get(name, name)), name


async def test_the_run_route_runs_through_run_recipe_as_as_a_manual_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_run(deps: RecipeRunDeps, **kwargs: Any) -> str:
        calls.append({"deps": deps, **kwargs})
        return "report"

    monkeypatch.setattr(app_module, "run_recipe_as", fake_run)
    names = [f.name for f in dataclasses.fields(RecipeRunDeps)]
    given = {name: object() for name in names}
    route_args = {
        "graph": given["graph"], "ontology": given["ontology"], "analytics": given["analytics"],
        "media": given["media"], "repo_root": given["recipe_repo_root"], "audit": given["audit"],
        "jobs": given["jobs"], "valkey": given["valkey"],
        "handling_scheme": given["handling_scheme"], "config": given["config"],
        "hotlists_store": given["hotlists_store"], "monitors_store": given["monitors_store"],
        "patterns_store": given["patterns_store"], "alerts_store": given["alerts_store"],
        "principal_resolver": given["principal_resolver"],
        "extraction_candidates": given["extraction_candidates"],
        "recogniser_for": given["recogniser_for"], "online_geocode": given["online_geocode"],
        "typology_rules": given["typology_rules"], "held_rows": given["held_rows"],
        "screening_lists": given["screening_lists"], "compute": given["compute"],
        "kyc_expiries": given["kyc_expiries"],
        "recipe_runs": given["recipe_runs"],
    }
    investigation, recipe, principal = SimpleNamespace(id="case-1"), object(), object()
    result = await run_studio_recipe(
        investigation=investigation,  # type: ignore[arg-type]
        recipe=recipe,  # type: ignore[arg-type]
        principal=principal,  # type: ignore[arg-type]
        body=SimpleNamespace(source_location="file.csv"),  # type: ignore[arg-type]
        **route_args,
    )
    assert result == "report"
    (call,) = calls
    assert call["principal"] is principal and call["recipe"] is recipe
    assert call["investigation_id"] == "case-1" and call["source_location"] == "file.csv"
    assert call["trigger"] == "manual"
    for name in names:
        assert getattr(call["deps"], name) is given[name], name
