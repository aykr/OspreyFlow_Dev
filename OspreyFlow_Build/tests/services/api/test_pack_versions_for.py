"""`pack_versions_for` (`06_DECISIONS.md` ADR-120 D10, Amendment 1): the map a publish stamps onto
the recipe, each pack its pipeline names or whose types its row template writes, at the version the
loaded ontology carries. Pure — no store.

What each test checks, and the violation that fails it:
- `test_pack_versions_for_pins_each_named_pack_at_the_loaded_version`: a pin taken from anywhere
  but the loaded ontology (a constant, or the pack file read afresh).
- `test_pack_versions_for_a_pipeline_naming_no_pack_is_empty`: a pack pinned that the recipe
  neither names nor writes, or the core pack pinned.
- `test_pack_versions_for_refuses_a_pack_the_ontology_lacks`: a pin silently dropped or invented
  for a pack that is not loaded, which would publish a recipe that can never run.
- `test_pack_versions_for_pins_a_pack_whose_types_are_written_under_the_core`: a recipe on the
  `pole` domain writing FIBO's `Account` publishing with no FIBO pin (the Ledger recipes' case).
"""

from __future__ import annotations

import pytest

from ontology.loader import load_default_ontology
from ontology.packs import load_deployment_ontology
from schemas.ingest import PipelineGraph, PipelineNode, PipelineNodeKind, RecipeEntity, RowTemplate

_NOTHING = RowTemplate(entities=[RecipeEntity(ref="e", pole_class="object", type="Endpoint")])
_WRITES_ACCOUNT = RowTemplate(entities=[RecipeEntity(ref="a", pole_class="object", type="Account")])


def _pipeline(*packs: str) -> PipelineGraph:
    return PipelineGraph(
        nodes=[
            PipelineNode(
                id=f"domain-{i}",
                kind=PipelineNodeKind.DOMAIN_MODEL,
                label=pack,
                config={"pack": pack},
            )
            for i, pack in enumerate(packs)
        ],
        edges=[],
    )


def test_pack_versions_for_pins_each_named_pack_at_the_loaded_version() -> None:
    from services.api.studio_publish import pack_versions_for

    assert pack_versions_for(_pipeline("niem"), _NOTHING, load_deployment_ontology()) == {"niem": 3}


def test_pack_versions_for_a_pipeline_naming_no_pack_is_empty() -> None:
    from services.api.studio_publish import pack_versions_for

    assert pack_versions_for(_pipeline("pole"), _NOTHING, load_deployment_ontology()) == {}
    assert pack_versions_for(None, _NOTHING, load_deployment_ontology()) == {}


def test_pack_versions_for_refuses_a_pack_the_ontology_lacks() -> None:
    from services.api.studio_publish import pack_versions_for

    with pytest.raises(ValueError, match="niem"):
        pack_versions_for(_pipeline("niem"), _NOTHING, load_default_ontology())


def test_pack_versions_for_pins_a_pack_whose_types_are_written_under_the_core() -> None:
    from services.api.studio_publish import pack_versions_for

    assert pack_versions_for(_pipeline("pole"), _WRITES_ACCOUNT, load_deployment_ontology()) == {
        "fibo": 1
    }
