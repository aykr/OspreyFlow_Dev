"""`profile_m9.py` (platform's M9 profiler, used by v0.6.0 stage 2's `run.sh profile`) renders every
variant offline against the deployment's ontology, so a change to `SearchNodesBuilder` or
`match_any_field` breaks this test rather than the next profile on the server (rule 15: ADR-124
Amendment 21 broke it silently, found only by stage 2's rehearsal, 15 November 2026)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology

PROFILE = (
    Path(__file__).resolve().parents[1]
    / "process" / "lanes" / "platform" / "v052-measure" / "profile_m9.py"
)  # fmt: skip


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("profile_m9", PROFILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _NoClient:
    """Nothing is sent: `variants` only renders."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"variants sent {name} to the store")


def _adapter() -> GraphArcadeDBAdapter:
    adapter = GraphArcadeDBAdapter(_NoClient(), load_uk_le_scheme())  # type: ignore[arg-type]
    adapter.use_schema(load_deployment_ontology())
    return adapter


def test_every_variant_renders_from_the_query_before_amendment_21() -> None:
    profile = _module()
    adapter = _adapter()
    found = profile.variants(adapter, "Tomasz Kellly")
    assert set(found) == {"before_am21", "no_access", "limit_20", "count", "by_label"}
    before = found["before_am21"]
    assert before == profile.before_am21(adapter, "Tomasz Kellly")
    # The whole-store shape Amendment 21 replaced, with the access filter, at the fallback's depth.
    assert before.startswith("g.V().or(") and "'Tomasz Kellly'" in before
    has_access = adapter._access.gremlin_has_step(profile.MEASURE)
    assert f".{has_access}.dedup().limit({profile.ONE_PAST}).elementMap()" in before
    assert has_access not in found["no_access"] and found["count"].endswith(".count()")
    assert ".limit(20)." in found["limit_20"] and found["by_label"].startswith("g.inject(1).union(")


@pytest.mark.asyncio
async def test_shipping_is_the_adapter_s_own_search_nodes() -> None:
    """The arm every other is compared with is `GraphPort.search_nodes` as built, not a copy."""
    profile = _module()
    adapter = _adapter()
    asked: list[tuple[str, Any, int]] = []

    class _Node:
        id = "n-1"

    async def search_nodes(query: str, principal: Any, *, limit: int = 20) -> list[Any]:
        asked.append((query, principal, limit))
        return [_Node()]

    adapter.search_nodes = search_nodes  # type: ignore[method-assign]
    took, ids = await profile._shipping(adapter, "Tomasz Kellly")
    assert ids == {"n-1"} and took >= 0
    assert asked == [("Tomasz Kellly", profile.MEASURE, profile.ONE_PAST)]
