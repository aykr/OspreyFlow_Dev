"""Phase 7's exit pipeline as the Studio's drawers build it (ADR-140 Amendment 12):
`apps/workspace/keyboard/fixtures/visits_and_contacts_pipeline.json` is the "Visits and contacts"
pipeline, its steps as nodes, which the keyboard walk (`ingest-studio.spec.ts`) builds by keys and
`stagingSteps.test.ts` rebuilds through the Glass's own edits. This holds the fixture to the server's
own `pipeline_with_staging` of the exit recipe's steps, so the three cannot drift apart, and to the
exit recipe's steps exactly (`test_the_fixture_is_the_exit_recipe_s_steps`)."""

from __future__ import annotations

import json
from pathlib import Path

from services.ingest.pipeline import pipeline_with_staging, staging_from_pipeline

from schemas.ingest import PipelineEdge, PipelineGraph, PipelineNode, PipelineNodeKind
from tests.ingest.test_staged_run import RECIPE

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "OspreyFlow_Core/apps/workspace/keyboard/fixtures/visits_and_contacts_pipeline.json"
)


def base() -> PipelineGraph:
    """The harness's "Visits and contacts" draft before its steps: two sources, Map and Load."""
    return PipelineGraph(
        nodes=[
            PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model"),
            PipelineNode(id="visit_bookings", kind=PipelineNodeKind.SOURCE, label="Visit bookings"),
            PipelineNode(id="number_owners", kind=PipelineNodeKind.SOURCE, label="Number owners"),
            PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
            PipelineNode(id="load", kind=PipelineNodeKind.LOAD, label="Load"),
        ],
        edges=[
            PipelineEdge(source="domain", target="visit_bookings"),
            PipelineEdge(source="domain", target="number_owners"),
            PipelineEdge(source="visit_bookings", target="map"),
            PipelineEdge(source="map", target="load"),
        ],
    )


def built() -> dict[str, object]:
    assert RECIPE.staging
    graph = pipeline_with_staging(base(), RECIPE.staging)
    return {
        "base": base().model_dump(mode="json"),
        "pipeline": graph.model_dump(mode="json"),
        "row_template": RECIPE.row_template.model_dump(mode="json", by_alias=True, exclude_none=True),
    }


def test_the_fixture_is_what_the_server_builds() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == built()


def test_the_fixture_is_the_exit_recipe_s_steps() -> None:
    graph = PipelineGraph.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8"))["pipeline"])
    assert staging_from_pipeline(graph) == RECIPE.staging


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(built(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
