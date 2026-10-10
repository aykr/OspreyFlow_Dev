"""The pipeline runner (`spec/06_DECISIONS.md` ADR-108 phase C), against a live Postgres
(`StudioRecipeStore`, `ExtractionCandidateStore`) and a live ArcadeDB (`GraphPort`) — the same
two-real-stores discipline `test_studio_publish_pipeline.py` set for the single-chain runner.

What a mistake would do, and the case that catches it:

- a second source branch silently not run, or run under the first branch's `load_id`, would make
  one branch unrevertible without the other
  (`test_two_source_branches_both_load_each_under_its_own_load_id`);
- an extract finding written `asserted`, or skipping the review queue, would be rule 5's automatic
  promotion (`test_extract_to_review_queue_queues_pending_with_the_documents_handling`,
  `test_extract_to_inferred_graph_writes_inferred_never_asserted`);
- a handling override applied quietly, or without its mandatory reason, would be ruling Q2
  violated (`test_extract_handling_override_is_loud_in_the_report`,
  `test_extract_handling_override_without_a_reason_is_refused`);
- a configured library the deployment cannot run, silently doing nothing, would be rule 2's
  silent truncation (`test_an_unwired_library_is_refused_in_words`);
- a document the principal cannot view, read into extraction anyway, would put access control
  outside the adapter (`test_a_document_above_the_loaders_clearance_is_not_extracted`);
- an enrich merge instead of a scored `SAME_AS` edge would violate rule 6
  (`test_enrich_matches_the_local_gazetteer_with_an_inferred_same_as`);
- an online geocode with no configured provider, or undisclosed, would be ruling Q5 violated
  (`test_enrich_online_without_a_provider_is_refused_in_words`,
  `test_enrich_online_allowlist_geocodes_discloses_and_persists`).
"""

from __future__ import annotations

import csv
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from adapters.recognise_spacy.adapter import RecogniseSpacyAdapter
from conduit_common.identity import new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    ExpandRequest,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.ingest import PipelineGraph, RowTemplate
from services.api.config import PostgresConfig
from services.api.pipeline_run import run_published_pipeline
from services.api.review import CandidateStatus, ExtractionCandidateStore
from services.api.studio_publish import build_recipe, write_and_commit_recipe
from services.api.studio_recipes import StudioRecipeStore

from tests.ingest.test_studio_run_geometries import RecordingAnalytics

AUTHOR = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_author"]
)
APPROVER = Principal(
    id="approver-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_approver"]
)
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["loader"])

_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}

#: spaCy's small English pipeline recognises these reliably; the text each endpoint "holds".
_NOTE_A = "Meeting notes: Amelia Burke travels to Birmingham on Friday."
_NOTE_B = "Second export: Victor Osei was seen near Walsall yesterday."


def _recognisers(name: str):
    return RecogniseSpacyAdapter() if name == "spacy" else None


def _endpoint_notes_template(*, entity_handling: dict | None = None) -> RowTemplate:
    return RowTemplate.model_validate(
        {
            "entities": [
                {
                    "ref": "phone",
                    "pole_class": "object",
                    "type": "Endpoint",
                    "match_on": "value_normalised",
                    "on_match": "reference",
                    "properties": {
                        "value_normalised": {"field": "a_party"},
                        "endpoint_kind": {"literal": "msisdn"},
                    },
                    **({"handling": entity_handling} if entity_handling else {}),
                    "content": {"kind": "document_text", "field": "notes"},
                }
            ]
        }
    )


def _location_template() -> RowTemplate:
    return RowTemplate.model_validate(
        {
            "entities": [
                {
                    "ref": "place",
                    "pole_class": "location",
                    "type": "Location",
                    "match_on": "name",
                    "on_match": "create",
                    "properties": {"name": {"field": "place"}},
                }
            ]
        }
    )


def _csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
async def store():
    s = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
async def candidates():
    s = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    return repo


async def _publish_pipeline(
    store: StudioRecipeStore,
    git_repo: Path,
    *,
    label: str,
    source_location: str,
    row_template: RowTemplate,
    pipeline: PipelineGraph,
    ontology_version: int,
):
    draft = await store.create_draft(
        AUTHOR,
        label=label,
        connector_profile="generic-csv",
        source_location=source_location,
        handling=_HANDLING,
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
    )
    draft = await store.update_row_template(
        draft.recipe_id, AUTHOR, row_template=row_template, unmapped_fields=[]
    )
    draft = await store.update_pipeline(draft.recipe_id, AUTHOR, pipeline=pipeline)
    await store.mark_verified(draft.recipe_id, draft.version, now=datetime.now(UTC))
    draft = await store.get(draft.recipe_id)
    built = build_recipe(
        draft, ontology_version=ontology_version, schedule_cron=None, schedule_watch=None
    )
    git_path = await write_and_commit_recipe(built, repo_root=git_repo)
    return await store.publish(
        draft.recipe_id,
        APPROVER,
        ontology_version=ontology_version,
        git_path=git_path,
        schedule_cron=None,
        schedule_watch=None,
        now=datetime.now(UTC),
    )


def _chain(extract_config: dict | None = None, *, enrich_config: dict | None = None,
           second_source: str | None = None) -> PipelineGraph:
    """One canonical branch, optionally a second source branch, an extract after the map, an
    enrich after the map — the shapes the Studio's own constructors build."""
    nodes = [
        {
            "id": "domain", "kind": "domain_model", "label": "Domain model",
            "config": {"pack": "pole"},
        },
        {"id": "source", "kind": "source", "label": "Export A", "config": {}},
        {"id": "profile", "kind": "profile", "label": "Profile", "config": {}},
        {"id": "map", "kind": "map", "label": "Map", "config": {}},
        {"id": "load", "kind": "load", "label": "Load", "config": {}},
    ]
    edges = [
        {"source": "domain", "target": "source"},
        {"source": "source", "target": "profile"},
        {"source": "profile", "target": "map"},
        {"source": "map", "target": "load"},
    ]
    if second_source is not None:
        nodes += [
            {"id": "source-b", "kind": "source", "label": "Export B",
             "config": {"source_location": second_source}},
            {"id": "source-b-profile", "kind": "profile", "label": "Profile", "config": {}},
            {"id": "source-b-map", "kind": "map", "label": "Map", "config": {}},
            {"id": "source-b-load", "kind": "load", "label": "Load", "config": {}},
        ]
        edges += [
            {"source": "domain", "target": "source-b"},
            {"source": "source-b", "target": "source-b-profile"},
            {"source": "source-b-profile", "target": "source-b-map"},
            {"source": "source-b-map", "target": "source-b-load"},
        ]
    if extract_config is not None:
        nodes += [
            {"id": "extract", "kind": "extract", "label": "Extract", "config": extract_config},
            {"id": "extract-load", "kind": "load", "label": "Load", "config": {}},
        ]
        edges += [
            {"source": "map", "target": "extract"},
            {"source": "extract", "target": "extract-load"},
        ]
    if enrich_config is not None:
        nodes += [
            {"id": "enrich", "kind": "enrich", "label": "Enrich", "config": enrich_config},
            {"id": "enrich-load", "kind": "load", "label": "Load", "config": {}},
        ]
        edges += [
            {"source": "map", "target": "enrich"},
            {"source": "enrich", "target": "enrich-load"},
        ]
    return PipelineGraph.model_validate({"nodes": nodes, "edges": edges})


async def _run(published, graph, *, git_repo: Path, candidates=None, media=None,
               analytics=None, online_geocode=None, load_id: str = "pipeline-load-1"):
    ontology = load_default_ontology()
    return await run_published_pipeline(
        published,
        LOADER,
        graph=graph,
        ontology=ontology,
        scheme=load_uk_le_scheme(),
        load_id=load_id,
        investigation_scope="case-1",
        repo_root=git_repo,
        recogniser_for=_recognisers,
        candidates=candidates,
        analytics=analytics,
        media=media,
        online_geocode=online_geocode,
    )


# --- Branches ---------------------------------------------------------------


async def test_two_source_branches_both_load_each_under_its_own_load_id(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "a.csv", ["a_party", "notes"], [{"a_party": "07960112001", "notes": _NOTE_A + " Case 0."}]
    )
    b = _csv(tmp_path / "b.csv", ["a_party", "notes"], [{"a_party": "07960112002", "notes": _NOTE_B}])
    published = await _publish_pipeline(
        store, git_repo, label="two branches", source_location=str(a),
        row_template=_endpoint_notes_template(),
        pipeline=_chain(second_source=str(b)), ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(published, graph, git_repo=git_repo, media=InMemoryMediaStore())
        assert len(report.branches) == 2
        load_ids = {branch.report.load_id for branch in report.branches}
        assert len(load_ids) == 2, "each branch must be independently revertible"
        assert report.rows_read == 2
        # Both branches' endpoints are in the graph, each stamped with its own branch load.
        for value, branch in zip(("07960112001", "07960112002"), report.branches, strict=True):
            node = await graph.find_node("Endpoint", "value_normalised", value, LOADER)
            assert node is not None
            assert node.audit.load_id == branch.report.load_id


# --- Extract ----------------------------------------------------------------


async def test_extract_to_review_queue_queues_pending_with_the_documents_handling(
    store: StudioRecipeStore, candidates: ExtractionCandidateStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "a.csv", ["a_party", "notes"], [{"a_party": "07960112003", "notes": _NOTE_A + " Case 1."}]
    )
    published = await _publish_pipeline(
        store, git_repo, label="extract queue", source_location=str(a),
        row_template=_endpoint_notes_template(),
        pipeline=_chain({"library": "spacy", "media": "text", "output": "review_queue"}),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(
            published, graph, git_repo=git_repo, candidates=candidates, media=InMemoryMediaStore()
        )
        (stage,) = report.extracts
        assert stage.refusals == []
        assert stage.documents_read == 1
        assert stage.candidates_queued >= 2  # Amelia Burke, Birmingham at least
        assert stage.nodes_written_inferred == 0

        document_id = next(
            node_id for branch in report.branches for node_id in branch.report.created_node_ids
            if node_id.startswith("content:")
        )
        queued = await candidates.list_for_document(document_id, LOADER)
        assert queued, "the findings must be in the review queue"
        assert {c.status for c in queued} == {CandidateStatus.PENDING}
        assert {c.handling.classification for c in queued} == {"OFFICIAL"}
        assert all(c.model.startswith("spacy:") for c in queued)
        # Rule 5: nothing reached the graph — a queued candidate is not a node.
        person = await graph.find_node("Person", "family_name", "Burke", LOADER)
        assert person is None


async def test_extract_to_inferred_graph_writes_inferred_never_asserted(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "a.csv", ["a_party", "notes"], [{"a_party": "07960112004", "notes": _NOTE_A + " Case 2."}]
    )
    published = await _publish_pipeline(
        store, git_repo, label="extract inferred", source_location=str(a),
        row_template=_endpoint_notes_template(),
        pipeline=_chain({"library": "spacy", "media": "text", "output": "inferred_graph"}),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(published, graph, git_repo=git_repo, media=InMemoryMediaStore())
        (stage,) = report.extracts
        assert stage.refusals == []
        assert stage.nodes_written_inferred >= 2
        assert stage.candidates_queued == 0
        person = await graph.find_node("Person", "family_name", "Burke", LOADER)
        assert person is not None
        assert person.provenance.state is ProvenanceState.INFERRED
        assert person.provenance.extracted_by is not None
        assert person.provenance.extracted_by.startswith("model:spacy:")


async def test_extract_handling_override_is_loud_in_the_report(
    store: StudioRecipeStore, candidates: ExtractionCandidateStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "a.csv", ["a_party", "notes"], [{"a_party": "07960112005", "notes": _NOTE_A + " Case 3."}]
    )
    override = {**_HANDLING, "handling_code": "D"}
    published = await _publish_pipeline(
        store, git_repo, label="extract override", source_location=str(a),
        row_template=_endpoint_notes_template(),
        pipeline=_chain({
            "library": "spacy", "media": "text", "output": "review_queue",
            "handling_override": override,
            "override_reason": "open-source press text; the source marking over-protects it",
        }),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(
            published, graph, git_repo=git_repo, candidates=candidates, media=InMemoryMediaStore()
        )
        (stage,) = report.extracts
        assert stage.refusals == []
        assert stage.handling_overridden == stage.candidates_queued > 0
        assert stage.override_reason is not None and "over-protects" in stage.override_reason
        document_id = next(
            node_id for branch in report.branches for node_id in branch.report.created_node_ids
            if node_id.startswith("content:")
        )
        queued = await candidates.list_for_document(document_id, LOADER)
        assert {c.handling.handling_code for c in queued} == {"D"}


async def test_extract_handling_override_without_a_reason_is_refused(
    store: StudioRecipeStore, candidates: ExtractionCandidateStore, tmp_path: Path, git_repo: Path
) -> None:
    """Belt and braces under the publish gate (which refuses this at publish): a committed recipe
    carrying an override with no reason still extracts nothing, in words."""
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "a.csv", ["a_party", "notes"], [{"a_party": "07960112006", "notes": _NOTE_A + " Case 4."}]
    )
    published = await _publish_pipeline(
        store, git_repo, label="override no reason", source_location=str(a),
        row_template=_endpoint_notes_template(),
        pipeline=_chain({
            "library": "spacy", "media": "text", "output": "review_queue",
            "handling_override": {**_HANDLING, "handling_code": "D"},
        }),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(
            published, graph, git_repo=git_repo, candidates=candidates, media=InMemoryMediaStore()
        )
        (stage,) = report.extracts
        assert stage.candidates_queued == 0 and stage.nodes_written_inferred == 0
        assert any("reason" in words for words in stage.refusals)


async def test_an_unwired_library_is_refused_in_words(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "a.csv", ["a_party", "notes"], [{"a_party": "07960112007", "notes": _NOTE_A + " Case 5."}]
    )
    published = await _publish_pipeline(
        store, git_repo, label="unwired library", source_location=str(a),
        row_template=_endpoint_notes_template(),
        pipeline=_chain({"library": "transformers", "media": "text", "output": "review_queue"}),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(published, graph, git_repo=git_repo, media=InMemoryMediaStore())
        (stage,) = report.extracts
        assert stage.candidates_queued == 0 and stage.nodes_written_inferred == 0
        assert any("transformers" in words for words in stage.refusals)
        # The branch load itself still happened — the refusal names the stage, not the run.
        assert report.rows_read == 1


async def test_a_document_above_the_loaders_clearance_is_not_extracted(
    store: StudioRecipeStore, candidates: ExtractionCandidateStore, tmp_path: Path, git_repo: Path
) -> None:
    """Access control stays in the adapter: the runner reads documents via `get_node` as the
    running principal, so a document above the loader's clearance never reaches the recogniser —
    and the report says the stage read nothing rather than quietly succeeding on nothing."""
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "a.csv", ["a_party", "notes"], [{"a_party": "07960112008", "notes": _NOTE_A + " Case 6."}]
    )
    published = await _publish_pipeline(
        store, git_repo, label="clearance extract", source_location=str(a),
        row_template=_endpoint_notes_template(
            entity_handling={**_HANDLING, "classification": "SECRET"}
        ),
        pipeline=_chain({"library": "spacy", "media": "text", "output": "review_queue"}),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(
            published, graph, git_repo=git_repo, candidates=candidates, media=InMemoryMediaStore()
        )
        (stage,) = report.extracts
        assert stage.documents_read == 0
        assert stage.candidates_queued == 0
        assert any("view" in words or "read" in words for words in stage.refusals)


# --- Enrich -----------------------------------------------------------------


def _gazetteer_location(name: str) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_node_id(),
        type="Location",
        properties={"name": name, "geometry_ref": f"gaz:{name}"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="gazetteer:fixture", locator=name, excerpt_hash="")],
            first_seen=now,
        ),
        handling=_HANDLING,
        created_by="seed",
        created_at=now,
    )


async def test_enrich_matches_the_local_gazetteer_with_an_inferred_same_as(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(tmp_path / "places.csv", ["place"], [{"place": "Walsall Market"}])
    published = await _publish_pipeline(
        store, git_repo, label="enrich local", source_location=str(a),
        row_template=_location_template(),
        pipeline=_chain(enrich_config={"geocoder": "local_gazetteer"}),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        tx = await graph.begin_transaction()
        (canonical_id,) = await graph.upsert_nodes([_gazetteer_location("Walsall Market")], tx)
        await graph.commit_transaction(tx)

        report = await _run(published, graph, git_repo=git_repo)
        (stage,) = report.enriches
        assert stage.refusals == []
        assert stage.locations_considered == 1
        assert stage.matched_local == 1
        assert stage.unmatched == 0
        mention_id = next(
            node_id for branch in report.branches for node_id in branch.report.created_node_ids
        )
        # Rule 6: never merged — the mention still exists, linked by a scored, inferred SAME_AS.
        mention = await graph.get_node(mention_id, LOADER)
        assert mention is not None
        around = await graph.expand(
            ExpandRequest(node_ids=[mention_id], depth=1, edge_types=["SAME_AS"]), LOADER
        )
        (same_as,) = [
            e for e in around.edges if {e.source, e.target} == {mention_id, canonical_id}
        ]
        assert same_as.provenance.state is ProvenanceState.INFERRED
        assert same_as.properties["score"] >= 0.8


async def test_enrich_online_without_a_provider_is_refused_in_words(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(tmp_path / "places.csv", ["place"], [{"place": "Nowhere Peculiar"}])
    published = await _publish_pipeline(
        store, git_repo, label="enrich no provider", source_location=str(a),
        row_template=_location_template(),
        pipeline=_chain(enrich_config={"geocoder": "online_allowlist"}),
        ontology_version=ontology.version,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(published, graph, git_repo=git_repo, online_geocode=None)
        (stage,) = report.enriches
        assert stage.matched_online == 0
        assert any("allow-list" in words or "provider" in words for words in stage.refusals)


async def test_enrich_online_allowlist_geocodes_discloses_and_persists(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    ontology = load_default_ontology()
    a = _csv(
        tmp_path / "places.csv", ["place"],
        [{"place": "Birmingham New Street"}, {"place": "Nowhere Peculiar"}],
    )
    published = await _publish_pipeline(
        store, git_repo, label="enrich online", source_location=str(a),
        row_template=_location_template(),
        pipeline=_chain(enrich_config={"geocoder": "online_allowlist"}),
        ontology_version=ontology.version,
    )

    asked: list[str] = []

    async def fake_provider(name: str) -> tuple[float, float] | None:
        # Rule 15: the fake models the real provider's refusals — an unknown name gets nothing,
        # not invented coordinates.
        asked.append(name)
        if name == "Birmingham New Street":
            return (-1.8984, 52.4778)
        return None

    analytics = RecordingAnalytics()
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        report = await _run(
            published, graph, git_repo=git_repo, analytics=analytics,
            online_geocode=fake_provider,
        )
        (stage,) = report.enriches
        assert stage.locations_considered == 2
        assert stage.matched_local == 0
        assert stage.matched_online == 1
        assert stage.unmatched == 1
        assert sorted(asked) == ["Birmingham New Street", "Nowhere Peculiar"]

        # The point is a row in the geometry partition, and the matched node's current revision
        # carries its ref — superseded, never edited in place (`01_DOMAIN_MODEL.md` §2.4).
        (geometry,) = analytics.geometries
        assert (geometry.lon, geometry.lat) == (-1.8984, 52.4778)
        current_names_to_refs: dict[str, str | None] = {}
        for branch in report.branches:
            for node_id in branch.report.created_node_ids:
                node = await graph.get_node(node_id, LOADER, include_superseded=True)
                assert node is not None
                if node.audit.superseded_by is not None:
                    node = await graph.get_node(node.audit.superseded_by, LOADER)
                    assert node is not None
                current_names_to_refs[node.properties["name"]] = node.properties.get(
                    "geometry_ref"
                )
        assert current_names_to_refs["Birmingham New Street"] == geometry.geometry_ref
        assert current_names_to_refs["Nowhere Peculiar"] is None


# --- Pack types at run time (ADR-108 Amendment 4) ----------------------------


def _fibo_template() -> RowTemplate:
    return RowTemplate.model_validate(
        {
            "entities": [
                {
                    "ref": "payer",
                    "pole_class": "object",
                    "type": "Account",
                    "match_on": "account_number",
                    "on_match": "reference",
                    "properties": {"account_number": {"field": "payer_iban"}},
                },
                {
                    "ref": "payee",
                    "pole_class": "object",
                    "type": "Account",
                    "match_on": "account_number",
                    "on_match": "reference",
                    "properties": {"account_number": {"field": "payee_iban"}},
                },
            ],
            "edges": [
                {
                    "type": "TRANSACTED",
                    "from": "payer",
                    "to": "payee",
                    "temporal": {"at": {"field": "at", "transform": "datetime"}},
                    "properties": {
                        "amount": {"field": "amount"},
                        "transaction_type": {"literal": "TRANSFER"},
                    },
                }
            ],
        }
    )


async def test_a_fibo_pipeline_loads_accounts_the_bare_core_refuses(
    store: StudioRecipeStore, tmp_path: Path, git_repo: Path
) -> None:
    """ADR-108 Amendment 4, both sides in one case: the same committed FIBO recipe is refused
    against the bare core (`Account` is no type of it — the state every run was in while
    `compose_with_packs` had no production caller) and loads cleanly against the deployment
    ontology, which composes every pack over the core at startup."""
    from ontology.packs import load_deployment_ontology

    rows = [
        {"payer_iban": "GB58 LOYD 3096 1700 7099 43", "payee_iban": "GB94 BARC 2003 5538 2998 12",
         "amount": "9400", "at": "2026-09-01T10:12:00Z"},
        {"payer_iban": "GB82 MONZ 0400 0412 8831 22", "payee_iban": "GB94 BARC 2003 5538 2998 12",
         "amount": "9750", "at": "2026-09-02T11:03:00Z"},
    ]
    a = _csv(tmp_path / "txns.csv", ["payer_iban", "payee_iban", "amount", "at"], rows)
    published = await _publish_pipeline(
        store, git_repo, label="fibo accounts", source_location=str(a),
        row_template=_fibo_template(),
        pipeline=_chain(),
        ontology_version=load_default_ontology().version,
    )

    core = load_default_ontology()
    deployed = load_deployment_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(core, scheme) as graph:
        with pytest.raises(Exception, match="Account"):
            await run_published_pipeline(
                published, LOADER, graph=graph, ontology=core, scheme=scheme,
                load_id="fibo-refused", investigation_scope="case-1", repo_root=git_repo,
                recogniser_for=_recognisers,
            )

    async with arcadedb_adapter(deployed, scheme) as graph:
        report = await _run(published, graph, git_repo=git_repo)
        assert report.rows_read == 2
        assert report.nodes_created == 3  # the three distinct accounts
        assert report.edges_created == 2
        payee = await graph.find_node(
            "Account", "account_number", "GB94 BARC 2003 5538 2998 12", LOADER
        )
        assert payee is not None
