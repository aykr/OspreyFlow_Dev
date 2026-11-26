"""SE9f (security): an accepted extraction candidate never sets a Document's `object_ref` or
`media_kind`. The owner's rule (SE9e (a), `RULINGS.md` 26 November 2026): only the engine's own
writes set them. `object_ref` names a file in the media store and the reader serves that file to
whoever can see the Document, so a caller who sets it picks which file their Document serves.

What a mistake here would do, and the case that catches it (each planted at `accept_candidate`'s own
merge, or at the route that reaches it; rule 15):

- today's merge, a caller's `properties_override` written as given:
  `test_the_extract_route_to_the_written_node_refuses_an_overridden_object_ref` (case 1);
- the check reading the override alone, so the model's own extracted `object_ref` is written:
  `test_the_models_own_extracted_object_ref_is_refused` (case 2);
- a check of `object_ref` alone: the `media_kind` cases (case 3);
- the check applied to every type: `test_another_entity_types_properties_are_accepted_as_before`
  (case 4);
- the check made in one route, or a route answering it another way: the five route cases (case 5);
- the file's reference, dataset or marking in the words: every refusal is compared whole (case 6).

Five routes reach `accept_candidate`: the review queue's, the document reader's one and bulk, a
question's and an email's. The bulk one reports a refusal for its item, in the same words, and goes
on with the rest (ADR-108 ruling Q1, `03_CONDUIT_MIDDLEWARE.md` §3.4); the other four answer 422
`engine_only_property`.

Pure: the real routes and services over the fakes the service tests keep. The graph fake refuses
what the adapter refuses (every property is checked against the ontology), and sits under the
stamping graph the app uses. The store-backed accept paths are the server's and the live step's.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_document_content,
    get_email_extraction,
    get_extraction_candidates,
    get_graph,
    get_investigations,
    get_model,
    get_ontology,
    get_principal,
    get_questions,
    get_valkey,
)
from services.api.dataset_scope import stamping
from services.api.email_extraction import email_document_id
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.review import CandidateStatus, ExtractionCandidate

from adapters.media_objectstore import reference_for
from conduit_common.identity import new_id
from ontology.validation import validate_properties
from schemas.domain import EdgeWrite, NodeWrite, OntologySchema, Principal, TxId

from .test_document_content import _service as _document_service
from .test_email_extraction import HANDLING, ONTOLOGY, FixedModel, InMemoryCandidates, WritingGraph
from .test_email_extraction import _build as _email_service
from .test_questions import _service as _questions_service

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
OTHER_UNIT = Principal(id="analyst-9", clearance="OFFICIAL", org_unit="unit-9", roles=["analyst"])
BASE = "/v1/investigations/inv-1"

#: Another file's reference, shaped as the media store shapes one. Synthetic (rule 9).
OTHER_FILE = reference_for(b"synthetic: another person's file", "image/png")
TITLE = "Statement"
TEXT = f"{TITLE} of Dana MERCER."


def _words(*names: str) -> str:
    """The whole refusal: the entity type and the properties, and nothing of any file."""
    return (
        f"only the platform sets {' and '.join(names)} on a Document, "
        "so this finding cannot be accepted"
    )


def _refusal(*names: str) -> dict[str, str]:
    return {"error": "engine_only_property", "detail": _words(*names)}


#: What a caller or a model may try to set, and the properties the refusal then names.
ATTEMPTS = [
    pytest.param({"object_ref": OTHER_FILE}, ("object_ref",), id="object_ref"),
    pytest.param({"media_kind": "image"}, ("media_kind",), id="media_kind"),
    pytest.param(
        {"media_kind": "image", "object_ref": OTHER_FILE},
        ("object_ref", "media_kind"),
        id="both",
    ),
]


@dataclass
class _Writes:
    """Every write the graph was asked for, whether or not it was later rolled back: refused means
    refused before anything is written."""

    nodes: list[NodeWrite] = field(default_factory=list)
    edges: list[EdgeWrite] = field(default_factory=list)


def _watch(graph: WritingGraph, monkeypatch: pytest.MonkeyPatch) -> _Writes:
    asked = _Writes()
    upsert_nodes, upsert_edges = graph.upsert_nodes, graph.upsert_edges

    async def nodes(writes: Sequence[NodeWrite], tx: TxId) -> list[str]:
        asked.nodes.extend(writes)
        return await upsert_nodes(writes, tx)

    async def edges(writes: Sequence[EdgeWrite], tx: TxId) -> list[str]:
        asked.edges.extend(writes)
        return await upsert_edges(writes, tx)

    monkeypatch.setattr(graph, "upsert_nodes", nodes)
    monkeypatch.setattr(graph, "upsert_edges", edges)
    return asked


class _Audit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: Any) -> None:
        self.actions.append(kwargs["action"])


class _OneCase:
    """`inv-1`, which only unit-1 can see, refused as the case store refuses."""

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        if investigation_id != "inv-1" or principal.org_unit != "unit-1":
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(
            id="inv-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="analyst-1",
            owning_unit="unit-1",
        )


class _Valkey:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append(channel)
        return 0


@dataclass
class _App:
    client: TestClient
    audit: _Audit
    valkey: _Valkey

    def serve(self, **dependencies: Any) -> None:
        keys = {
            "candidates": get_extraction_candidates,
            "graph": get_graph,
            "model": get_model,
            "documents": get_document_content,
            "emails": get_email_extraction,
            "questions": get_questions,
        }
        for name, value in dependencies.items():
            app.dependency_overrides[keys[name]] = _giving(value)


def _giving(value: Any) -> Any:
    """A dependency answering `value`, with no parameter for FastAPI to read from the request."""
    return lambda: value


@pytest.fixture
def served() -> Iterator[_App]:
    audit, valkey = _Audit(), _Valkey()
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_investigations] = lambda: _OneCase()
    app.dependency_overrides[get_ontology] = lambda: ONTOLOGY
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_valkey] = lambda: valkey
    try:
        yield _App(TestClient(app), audit, valkey)
    finally:
        app.dependency_overrides.clear()


async def _pending(
    store: InMemoryCandidates, entity_type: str, properties: dict[str, Any], document_id: str
) -> str:
    """A pending finding, as the extract route stores one."""
    (record,) = await store.store(
        [
            ExtractionCandidate(
                id=new_id(),
                document_id=document_id,
                entity_type=entity_type,
                properties=properties,
                confidence=0.9,
                model="local-model",
                locator="char span 0-9",
                excerpt_hash="h",
                handling=HANDLING,
            )
        ],
        ANALYST,
    )
    return record.id


def _extract_a_document(served: _App, model_says: dict[str, Any]) -> str:
    """The review queue's own extract route, with `Document` among the types the caller chose. The
    model answers one Document holding `model_says`. Returns the pending finding's id."""
    served.serve(model=FixedModel({"Document": [{"title": TITLE, **model_says, "confidence": 0.9}]}))
    response = served.client.post(
        f"{BASE}/ingest/extract",
        json={
            "document_id": "doc-1",
            "text": TEXT,
            "profile": {"entity_types": ["Document"]},
            "handling": HANDLING.model_dump(),
            "model": "local-model",
        },
    )
    assert response.status_code == 200, response.text
    (finding,) = response.json()
    assert (finding["entity_type"], finding["status"]) == ("Document", "pending")
    assert finding["properties"] == {"title": TITLE, **model_says}
    return str(finding["id"])


def _review_queue(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> tuple[InMemoryCandidates, WritingGraph, _Writes]:
    candidates, graph = InMemoryCandidates(), WritingGraph()
    asked = _watch(graph, monkeypatch)
    served.serve(candidates=candidates, graph=stamping(graph))
    return candidates, graph, asked


def _accept(served: _App, finding: str, override: dict[str, Any] | None) -> Any:
    return served.client.post(
        f"{BASE}/ingest/candidates/{finding}/accept", json={"properties_override": override}
    )


# --- case 1: the caller's override ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "named"),
    [*ATTEMPTS[:1], pytest.param({"object_ref": None}, ("object_ref",), id="object_ref-null")],
)
async def test_the_extract_route_to_the_written_node_refuses_an_overridden_object_ref(
    served: _App,
    monkeypatch: pytest.MonkeyPatch,
    override: dict[str, Any],
    named: tuple[str, ...],
) -> None:
    candidates, graph, asked = _review_queue(served, monkeypatch)
    finding = _extract_a_document(served, {})

    response = _accept(served, finding, override)

    written = [n.properties for n in graph.nodes.values()]
    assert (response.status_code, written) == (422, [])
    assert response.json() == _refusal(*named)
    assert asked == _Writes()
    assert candidates.records[finding].status is CandidateStatus.PENDING
    assert "accept_extraction_candidate" not in served.audit.actions

    # Refused, not spent: the finding is still there to accept without the override.
    again = _accept(served, finding, None)
    assert again.status_code == 200, again.text
    assert [n.properties for n in graph.nodes.values()] == [{"title": TITLE}]


# --- cases 2 and 3: the model's own properties, and `media_kind` --------------------------------


@pytest.mark.parametrize(("model_says", "named"), ATTEMPTS)
async def test_the_models_own_extracted_object_ref_is_refused(
    served: _App,
    monkeypatch: pytest.MonkeyPatch,
    model_says: dict[str, Any],
    named: tuple[str, ...],
) -> None:
    candidates, graph, asked = _review_queue(served, monkeypatch)
    finding = _extract_a_document(served, model_says)

    # An override of something else does not clear what the model set.
    response = _accept(served, finding, {"title": "Another title"})

    assert (response.status_code, graph.nodes) == (422, {})
    assert response.json() == _refusal(*named)
    assert asked == _Writes()
    assert candidates.records[finding].status is CandidateStatus.PENDING


@pytest.mark.parametrize(("override", "named"), ATTEMPTS[1:])
async def test_an_overridden_media_kind_is_refused(
    served: _App,
    monkeypatch: pytest.MonkeyPatch,
    override: dict[str, Any],
    named: tuple[str, ...],
) -> None:
    candidates, graph, asked = _review_queue(served, monkeypatch)
    finding = _extract_a_document(served, {})

    response = _accept(served, finding, override)

    assert (response.status_code, graph.nodes) == (422, {})
    assert response.json() == _refusal(*named)
    assert asked == _Writes()
    assert candidates.records[finding].status is CandidateStatus.PENDING


# --- case 4: nothing else changes ----------------------------------------------------------------


async def test_a_documents_other_properties_are_accepted_as_before(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Document` stays a type a caller may extract: only the two properties are refused."""
    _, graph, _ = _review_queue(served, monkeypatch)
    finding = _extract_a_document(served, {})

    response = _accept(served, finding, {"title": "Another title"})

    assert response.status_code == 200, response.text
    assert [n.properties for n in graph.nodes.values()] == [{"title": "Another title"}]


def _where_a_person_has_those_properties_too() -> OntologySchema:
    """A model in which another type declares `object_ref` and `media_kind`, as a pack may. The
    shipped ontology gives them to `Document` alone, and the graph refuses an undeclared one."""
    document = ONTOLOGY.entity_type("Document")
    assert document is not None
    theirs = [p for p in document.properties if p.name in ("object_ref", "media_kind")]
    assert len(theirs) == 2
    return ONTOLOGY.model_copy(
        update={
            "entity_types": [
                t.model_copy(update={"properties": [*t.properties, *theirs]})
                if t.name == "Person"
                else t
                for t in ONTOLOGY.entity_types
            ]
        }
    )


class _GraphOf(WritingGraph):
    """`WritingGraph`, checking against the ontology it is given."""

    def __init__(self, ontology: OntologySchema) -> None:
        super().__init__()
        self.ontology = ontology

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[str]:
        for write in nodes:
            entity_type = self.ontology.entity_type(write.type)
            assert entity_type is not None, write.type
            validate_properties(entity_type, write.properties)
        self._pending_nodes[tx].extend(nodes)
        return [n.id for n in nodes]


async def test_another_entity_types_properties_are_accepted_as_before(served: _App) -> None:
    candidates = InMemoryCandidates()
    graph = _GraphOf(_where_a_person_has_those_properties_too())
    served.serve(candidates=candidates, graph=stamping(graph))
    finding = await _pending(
        candidates, "Person", {"family_name": "MERCER", "media_kind": "text"}, "doc-1"
    )

    response = _accept(served, finding, {"given_names": "Dana", "object_ref": OTHER_FILE})

    assert response.status_code == 200, response.text
    assert [n.properties for n in graph.nodes.values()] == [
        {
            "family_name": "MERCER",
            "given_names": "Dana",
            "media_kind": "text",
            "object_ref": OTHER_FILE,
        }
    ]
    assert candidates.records[finding].status is CandidateStatus.ACCEPTED


# --- case 5: every route that accepts -------------------------------------------------------------


async def test_the_review_queues_accept_route_refuses(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates, graph, asked = _review_queue(served, monkeypatch)
    finding = await _pending(
        candidates, "Document", {"title": TITLE, "object_ref": OTHER_FILE}, "doc-1"
    )

    response = _accept(served, finding, None)

    assert (response.status_code, graph.nodes) == (422, {})
    assert response.json() == _refusal("object_ref")
    assert asked == _Writes()
    assert candidates.records[finding].status is CandidateStatus.PENDING
    assert served.audit.actions == []


async def test_the_document_readers_accept_route_refuses(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, _, candidates, graph, _ = await _document_service()
    asked = _watch(graph, monkeypatch)
    served.serve(documents=service)
    finding = await _pending(
        candidates, "Document", {"title": TITLE, "object_ref": OTHER_FILE}, "text-1"
    )

    response = served.client.post(f"{BASE}/documents/text-1/candidates/{finding}/accept")

    assert (response.status_code, graph.nodes) == (422, {})
    assert response.json() == _refusal("object_ref")
    assert asked == _Writes()
    assert candidates.records[finding].status is CandidateStatus.PENDING
    assert served.audit.actions == [] and served.valkey.published == []


async def test_the_document_readers_bulk_accept_refuses_that_item_and_goes_on(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, _, candidates, graph, _ = await _document_service()
    asked = _watch(graph, monkeypatch)
    served.serve(documents=service)
    refused = await _pending(
        candidates, "Document", {"title": TITLE, "object_ref": OTHER_FILE}, "text-1"
    )
    person = await _pending(candidates, "Person", {"family_name": "MERCER"}, "text-1")

    response = served.client.post(
        f"{BASE}/documents/text-1/candidates/accept",
        json={"candidate_ids": [refused, person]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refusals"] == [{"candidate_id": refused, "words": _words("object_ref")}]
    (accepted,) = body["accepted"]
    # Nothing of the refused finding was asked of the graph: the person and its one link alone.
    assert [(n.id, n.type) for n in asked.nodes] == [(accepted["node_id"], "Person")]
    assert [e.source for e in asked.edges] == [accepted["node_id"]]
    assert candidates.records[refused].status is CandidateStatus.PENDING
    assert candidates.records[person].status is CandidateStatus.ACCEPTED


async def test_a_questions_accept_route_refuses(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, candidates, graph, _ = await _questions_service()
    asked = _watch(graph, monkeypatch)
    served.serve(questions=service)
    finding = await _pending(
        candidates,
        "Document",
        {"title": TITLE, "object_ref": OTHER_FILE},
        email_document_id("ev-1"),
    )

    response = served.client.post(f"{BASE}/questions/candidates/{finding}/accept")

    assert (response.status_code, graph.nodes) == (422, {})
    assert response.json() == _refusal("object_ref")
    assert asked == _Writes()
    assert candidates.records[finding].status is CandidateStatus.PENDING
    assert served.audit.actions == [] and served.valkey.published == []


async def test_an_emails_accept_route_refuses(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, graph, _, candidates, _ = await _email_service()
    asked = _watch(graph, monkeypatch)
    served.serve(emails=service)
    finding = await _pending(
        candidates,
        "Document",
        {"title": TITLE, "object_ref": OTHER_FILE},
        email_document_id("ev-1"),
    )

    response = served.client.post(f"{BASE}/links/e1/events/ev-1/candidates/{finding}/accept")

    assert (response.status_code, graph.nodes) == (422, {})
    assert response.json() == _refusal("object_ref")
    assert asked == _Writes()
    assert candidates.records[finding].status is CandidateStatus.PENDING
    assert served.audit.actions == [] and served.valkey.published == []


# --- rules 3 and 4: the refusal tells nobody anything about a finding they may not read ----------


async def test_another_units_finding_is_not_found_whatever_the_override_holds(
    served: _App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Green before the rule and after it: a check made before the finding is read as this caller
    would answer 422 here, where there must be no difference from a finding that does not exist."""
    candidates, _, asked = _review_queue(served, monkeypatch)
    finding = await _pending(candidates, "Document", {"title": TITLE}, "doc-1")
    app.dependency_overrides[get_principal] = lambda: OTHER_UNIT
    app.dependency_overrides[get_investigations] = lambda: _AnyonesCase()

    theirs = _accept(served, finding, {"object_ref": OTHER_FILE})
    missing = _accept(served, "no-such-finding", {"object_ref": OTHER_FILE})

    assert (theirs.status_code, theirs.json()) == (404, missing.json())
    assert theirs.json()["error"] == "extraction_candidate_not_found"
    assert asked == _Writes()


class _AnyonesCase(_OneCase):
    """Lets the other unit into the case, so the finding's own refusal is the one answered."""

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        return await super().get_authorized(investigation_id, ANALYST)
