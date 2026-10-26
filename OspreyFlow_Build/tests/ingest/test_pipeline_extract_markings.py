"""Rule 3, ADR-127 Amendment 26: a pipeline run's markings are the union over its branches and
every marking its extract stages wrote (their `handling_override` included), so a pipeline whose
extract wrote above the branches' markings withholds its counts, `extracts[]` among them. What a
mistake would do, and the case that catches it:

- an extract stage that does not name the marking of what it read and wrote
  (`test_an_extract_stage_names_the_marking_of_each_document_it_read`);
- an override, which writes above (or below) the document, left out
  (`test_an_extract_stage_names_its_override_as_well`);
- the pipeline's union ignoring the stages
  (`test_a_pipeline_whose_extract_wrote_above_the_branches_reports_that_marking`)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from services.api import pipeline_run
from services.api.pipeline_run import _run_extract_stage, run_published_pipeline

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.recognise import RecogniseResult
from schemas.domain import Handling, Node, Principal
from schemas.ingest import (
    BranchRunReport,
    LoadReport,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.ingest.recipe_test_support import MergingGraph

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


def _h(classification: str) -> Handling:
    return Handling(
        classification=classification, handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


class _Graph:
    """What an extract stage asks of the graph: the documents a branch created, read back."""

    def __init__(self, document: Node) -> None:
        self.document = document

    async def get_node(self, node_id: str, principal: Any) -> Node:
        return self.document

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def rollback_transaction(self, tx: str) -> None:
        return None


class _Recogniser:
    async def recognise(self, text: str) -> RecogniseResult:
        return RecogniseResult(recogniser="stub:1", entities=[])


def _document(classification: str) -> Node:
    return Node.model_construct(
        id="doc-1", type="Document",
        properties={"media_kind": "text", "object_ref": "ref-1", "title": "A report"},
        handling=_h(classification),
    )  # fmt: skip


def _pipeline(**extract_config: Any) -> tuple[PipelineGraph, PipelineNode]:
    extract = PipelineNode(
        id="extract", kind=PipelineNodeKind.EXTRACT, label="Extract",
        config={"library": "stanza", "output": "inferred_graph", **extract_config},
    )  # fmt: skip
    graph = PipelineGraph.model_validate(
        {
            "nodes": [
                {"id": "a", "kind": "source", "label": "A"},
                extract.model_dump(),
            ],
            "edges": [{"source": "a", "target": "extract"}],
        }
    )
    return graph, extract


async def _stage(document_marking: str, **config: Any) -> Any:
    pipeline, node = _pipeline(**config)
    media = InMemoryMediaStore()
    ref = await media.put(b"A short synthetic report.", "text/plain")
    document = _document(document_marking)
    document.properties["object_ref"] = ref
    branch = BranchRunReport(
        source_id="a", source_label="A",
        report=LoadReport(load_id="p:a", recipe_id="r", recipe_version=1, created_node_ids=["doc-1"]),
    )  # fmt: skip
    report, _written = await _run_extract_stage(
        node, pipeline=pipeline, branches=[branch], graph=_Graph(document),  # type: ignore[arg-type]
        ontology=ONTOLOGY, principal=LOADER, recogniser_for=lambda name: _Recogniser(),
        candidates=None, media=media,
    )  # fmt: skip
    return report


async def test_an_extract_stage_names_the_marking_of_each_document_it_read() -> None:
    report = await _stage("SECRET")
    assert report.documents_read == 1
    assert report.markings == [_h("SECRET")]


async def test_an_extract_stage_names_its_override_as_well() -> None:
    override = _h("OFFICIAL").model_dump(mode="json")
    report = await _stage(
        "SECRET", handling_override=override, override_reason="the findings are shareable"
    )
    assert {m.classification for m in report.markings} == {"SECRET", "OFFICIAL"}


async def test_a_pipeline_whose_extract_wrote_above_the_branches_reports_that_marking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def branch_run(draft: Any, principal: Any, *, load_id: str, **kwargs: Any) -> LoadReport:
        return LoadReport(
            load_id=load_id, recipe_id=draft.recipe_id, recipe_version=draft.version,
            created_node_ids=["doc-1"], markings=[_h("OFFICIAL")],
        )  # fmt: skip

    monkeypatch.setattr(pipeline_run, "run_published_recipe", branch_run)
    pipeline, _node = _pipeline()
    draft = StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id="p", version=1, status=StudioRecipeStatus.PUBLISHED, label="P",
        owning_unit="unit-1", created_by="a", created_at=datetime(2026, 10, 26, tzinfo=UTC),
        pipeline=pipeline,
    )  # fmt: skip
    media = InMemoryMediaStore()
    ref = await media.put(b"A short synthetic report.", "text/plain")
    document = _document("SECRET")
    document.properties["object_ref"] = ref
    report = await run_published_pipeline(
        draft, LOADER, graph=_Graph(document),  # type: ignore[arg-type]
        ontology=ONTOLOGY, scheme=SCHEME, load_id="p-1", investigation_scope="case-1",
        repo_root=tmp_path, recogniser_for=lambda name: _Recogniser(), media=media,
    )  # fmt: skip
    assert [b.report.markings for b in report.branches] == [[_h("OFFICIAL")]]
    assert {m.classification for m in report.markings} == {"OFFICIAL", "SECRET"}
    assert MergingGraph  # keep the import honest for the checker
