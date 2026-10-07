"""`POST .../ingest/extract`, `GET .../ingest/candidates`, `POST .../candidates/{id}/accept`,
`POST .../candidates/{id}/reject`, `POST /v1/nodes/{id}/confirm`, `POST /v1/nodes/{id}/retract`
route wiring — `spec/09_INGEST_STUDIO.md` §4/§7, `spec/01_DOMAIN_MODEL.md` §2.1. The underlying
logic is proven in `tests/services/api/test_review.py`/`test_review_store.py` and
`tests/extract/test_writer.py`; this file proves each route calls it with the right arguments,
audits, and denies a principal without access.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_extraction_candidates,
    get_graph,
    get_investigations,
    get_judgements_store,
    get_model,
    get_ontology,
    get_principal,
)
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.review import (
    CandidateStatus,
    DocumentNotFoundError,
    ExtractionCandidateNotFoundError,
    ExtractionCandidateRecord,
)

from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.model import ExtractionRequest, ExtractionResult

ONTOLOGY = load_default_ontology()
PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_UNIT_PRINCIPAL = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")


def _record(
    candidate_id: str = "cand-1", status: CandidateStatus = CandidateStatus.PENDING
) -> ExtractionCandidateRecord:
    return ExtractionCandidateRecord(
        id=candidate_id,
        document_id="doc-1",
        entity_type="Person",
        properties={"family_name": "MERCER"},
        confidence=0.9,
        model="m",
        locator="char span 0-6",
        excerpt_hash="h",
        handling=_handling(),
        status=status,
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _node(node_id: str, state: ProvenanceState, owning_unit: str = "unit-1") -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={"family_name": "MERCER"},
        provenance=Provenance(
            state=state,
            sources=[SourceRef(document_id="doc-1", locator="char span 0-6", excerpt_hash="h")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            extraction_confidence=0.9 if state is not ProvenanceState.ASSERTED else None,
        ),
        handling=Handling(
            classification="OFFICIAL",
            handling_code="P",
            originator="u",
            owning_unit=owning_unit,
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="model:m"),
    )


class _FakeModelPort:
    def __init__(self) -> None:
        self.data = {"Person": [{"family_name": "MERCER", "confidence": 0.9}]}

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        return ExtractionResult(document_id=req.document_id, model=req.model, data=self.data)


class _FakeExtractionCandidates:
    def __init__(self) -> None:
        self.records: dict[str, ExtractionCandidateRecord] = {}
        self.list_calls: list[tuple[str, Principal]] = []
        self.document_texts: dict[str, tuple[str, str]] = {}  # document_id -> (text, owning_unit)

    async def store_document_text(
        self, document_id: str, text: str, principal: Principal
    ) -> None:
        self.document_texts[document_id] = (text, principal.org_unit)

    async def get_document_text(self, document_id: str, principal: Principal) -> str:
        stored = self.document_texts.get(document_id)
        if stored is None or stored[1] != principal.org_unit:
            raise DocumentNotFoundError(document_id)
        return stored[0]

    async def store(
        self, candidates: list, principal: Principal
    ) -> list[ExtractionCandidateRecord]:
        stored = []
        for candidate in candidates:
            record = ExtractionCandidateRecord(
                **candidate.model_dump(),
                status=CandidateStatus.PENDING,
                owning_unit=principal.org_unit,
                created_by=principal.id,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            self.records[record.id] = record
            stored.append(record)
        return stored

    async def list_for_document(
        self, document_id: str, principal: Principal
    ) -> list[ExtractionCandidateRecord]:
        self.list_calls.append((document_id, principal))
        return [
            r
            for r in self.records.values()
            if r.owning_unit == principal.org_unit and r.document_id == document_id
        ]

    async def get_authorized(
        self, candidate_id: str, principal: Principal
    ) -> ExtractionCandidateRecord:
        record = self.records.get(candidate_id)
        if record is None or record.owning_unit != principal.org_unit:
            raise ExtractionCandidateNotFoundError(candidate_id)
        return record

    async def mark_reviewed(
        self,
        candidate_id: str,
        principal: Principal,
        *,
        status: CandidateStatus,
        node_id: str | None,
    ) -> None:
        record = self.records[candidate_id]
        self.records[candidate_id] = record.model_copy(
            update={"status": status, "reviewed_by": principal.id, "node_id": node_id}
        )


class _FakeGraphPort:
    def __init__(self, nodes: dict[str, Node] | None = None) -> None:
        self.nodes = nodes or {}
        self.upserted: list[NodeWrite] = []
        self.superseded: list[tuple[str, NodeWrite]] = []
        self._next_tx = 0

    async def begin_transaction(self) -> str:
        self._next_tx += 1
        return f"tx-{self._next_tx}"

    async def commit_transaction(self, tx: str) -> None:
        pass

    async def rollback_transaction(self, tx: str) -> None:
        pass

    async def upsert_nodes(self, nodes: list[NodeWrite], tx: str) -> list[str]:
        self.upserted.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: list[EdgeWrite], tx: str) -> list[str]:
        raise AssertionError("not exercised by these tests")

    async def get_node(
        self, node_id: str, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        node = self.nodes.get(node_id)
        if node is None or node.handling.owning_unit != principal.org_unit:
            return None
        return node

    async def supersede_node(self, node_id: str, replacement: NodeWrite, tx: str) -> str:
        self.superseded.append((node_id, replacement))
        return replacement.id


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _FakeJudgements:
    """`services/api/assessments.py::flag_judgements_citing_superseded_node`'s own store
    interface — `confirm_node_route`/`retract_node_route` now call it on every supersede, so this
    file's own route-wiring scope (not `assessments.py`'s real behaviour, proven with real
    Postgres/ArcadeDB in `tests/services/api/test_assessments.py`) needs a fake that satisfies the
    interface without a live store, the same reason this file already fakes `graph`/
    `investigations`."""

    def __init__(self) -> None:
        self.flagged: list[str] = []

    async def list_citing(self, referent_id: str) -> list[object]:
        return []

    async def flag_for_review(self, judgement_id: str, *, reason: str) -> None:
        self.flagged.append(judgement_id)


class _FakeInvestigations:
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        # `need` (ADR-052) is accepted and ignored: this fake proves the unit check. The level
        # rules have their own tests in `test_investigation_levels.py`.
        if investigation_id != "inv-1":
            raise InvestigationNotFoundError(investigation_id)
        investigation = Investigation(
            id="inv-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="analyst-1",
            owning_unit="unit-1",
        )
        if investigation.owning_unit != principal.org_unit:
            raise InvestigationNotFoundError(investigation_id)
        return investigation


@pytest.fixture
def fakes():
    model = _FakeModelPort()
    candidates = _FakeExtractionCandidates()
    graph = _FakeGraphPort()
    audit = _FakeAudit()

    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_model] = lambda: model
    app.dependency_overrides[get_extraction_candidates] = lambda: candidates
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_ontology] = lambda: ONTOLOGY
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: _FakeInvestigations()
    app.dependency_overrides[get_judgements_store] = lambda: _FakeJudgements()

    client = TestClient(app)
    try:
        yield client, model, candidates, graph, audit
    finally:
        app.dependency_overrides.clear()


def test_run_extraction_returns_candidates_and_audits(fakes) -> None:
    client, _model, _candidates, _graph, audit = fakes

    response = client.post(
        "/v1/investigations/inv-1/ingest/extract",
        json={
            "document_id": "doc-1",
            "text": "Statement of: Dana MERCER.",
            "profile": {"entity_types": ["Person"]},
            "handling": _handling().model_dump(),
            "model": "qwen2.5:0.5b-instruct",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "pending"
    assert audit.records[-1]["action"] == "run_extraction"


def test_run_extraction_denies_a_principal_in_a_different_org_unit(fakes) -> None:
    client, _model, _candidates, _graph, _audit = fakes
    app.dependency_overrides[get_principal] = lambda: OTHER_UNIT_PRINCIPAL

    response = client.post(
        "/v1/investigations/inv-1/ingest/extract",
        json={
            "document_id": "doc-1",
            "text": "x",
            "profile": {"entity_types": ["Person"]},
            "handling": _handling().model_dump(),
            "model": "m",
        },
    )

    assert response.status_code == 404


def test_list_candidates_returns_only_the_principals_own_unit(fakes) -> None:
    client, _model, candidates, _graph, _audit = fakes
    candidates.records["cand-1"] = _record("cand-1")

    response = client.get(
        "/v1/investigations/inv-1/ingest/candidates", params={"document_id": "doc-1"}
    )

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == ["cand-1"]


def test_list_candidates_denies_a_principal_in_a_different_org_unit(fakes) -> None:
    client, _model, _candidates, _graph, _audit = fakes
    app.dependency_overrides[get_principal] = lambda: OTHER_UNIT_PRINCIPAL

    response = client.get(
        "/v1/investigations/inv-1/ingest/candidates", params={"document_id": "doc-1"}
    )

    assert response.status_code == 404


def test_accept_candidate_writes_a_node_and_returns_its_id(fakes) -> None:
    client, _model, candidates, graph, audit = fakes
    candidates.records["cand-1"] = _record("cand-1")

    response = client.post("/v1/investigations/inv-1/ingest/candidates/cand-1/accept", json={})

    assert response.status_code == 200
    assert response.json()["node_id"] == graph.upserted[0].id
    assert candidates.records["cand-1"].status == CandidateStatus.ACCEPTED
    assert audit.records[-1]["action"] == "accept_extraction_candidate"


def test_accept_candidate_returns_404_for_an_unknown_candidate(fakes) -> None:
    client, _model, _candidates, _graph, _audit = fakes

    response = client.post(
        "/v1/investigations/inv-1/ingest/candidates/no-such-candidate/accept", json={}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "extraction_candidate_not_found"


def test_accept_candidate_twice_returns_409(fakes) -> None:
    client, _model, candidates, _graph, _audit = fakes
    candidates.records["cand-1"] = _record("cand-1", status=CandidateStatus.ACCEPTED)

    response = client.post("/v1/investigations/inv-1/ingest/candidates/cand-1/accept", json={})

    assert response.status_code == 409
    assert response.json()["error"] == "candidate_not_pending"


def test_accept_candidate_denies_a_principal_in_a_different_org_unit(fakes) -> None:
    client, _model, candidates, _graph, _audit = fakes
    candidates.records["cand-1"] = _record("cand-1")
    app.dependency_overrides[get_principal] = lambda: OTHER_UNIT_PRINCIPAL

    response = client.post("/v1/investigations/inv-1/ingest/candidates/cand-1/accept", json={})

    assert response.status_code == 404


def test_reject_candidate_marks_rejected(fakes) -> None:
    client, _model, candidates, _graph, audit = fakes
    candidates.records["cand-1"] = _record("cand-1")

    response = client.post("/v1/investigations/inv-1/ingest/candidates/cand-1/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert candidates.records["cand-1"].status == CandidateStatus.REJECTED
    assert audit.records[-1]["action"] == "reject_extraction_candidate"


def test_reject_candidate_denies_a_principal_in_a_different_org_unit(fakes) -> None:
    client, _model, candidates, _graph, _audit = fakes
    candidates.records["cand-1"] = _record("cand-1")
    app.dependency_overrides[get_principal] = lambda: OTHER_UNIT_PRINCIPAL

    response = client.post("/v1/investigations/inv-1/ingest/candidates/cand-1/reject")

    assert response.status_code == 404


def test_confirm_node_route_flips_state_and_audits(fakes) -> None:
    client, _model, _candidates, graph, audit = fakes
    graph.nodes["n1"] = _node("n1", ProvenanceState.INFERRED)

    response = client.post("/v1/investigations/inv-1/nodes/n1/confirm")

    assert response.status_code == 200
    assert graph.superseded[0][1].provenance.state == ProvenanceState.ASSERTED
    assert audit.records[-1]["action"] == "confirm_node"


def test_confirm_node_route_404_for_a_node_in_a_different_org_unit(fakes) -> None:
    """The same existence-leak discipline every other node read in this app
    already uses: a principal without access gets the same 404 an unknown node id would."""
    client, _model, _candidates, graph, _audit = fakes
    graph.nodes["n1"] = _node("n1", ProvenanceState.INFERRED, owning_unit="unit-2")

    response = client.post("/v1/investigations/inv-1/nodes/n1/confirm")

    assert response.status_code == 404
    assert response.json()["error"] == "node_not_found"
    assert graph.superseded == []


def test_confirm_node_route_409_when_already_asserted(fakes) -> None:
    client, _model, _candidates, graph, _audit = fakes
    graph.nodes["n1"] = _node("n1", ProvenanceState.ASSERTED)

    response = client.post("/v1/investigations/inv-1/nodes/n1/confirm")

    assert response.status_code == 409
    assert response.json()["error"] == "provenance_transition_invalid"


def test_retract_node_route_flips_state_back_and_audits(fakes) -> None:
    client, _model, _candidates, graph, audit = fakes
    graph.nodes["n1"] = _node("n1", ProvenanceState.ASSERTED)

    response = client.post("/v1/investigations/inv-1/nodes/n1/retract")

    assert response.status_code == 200
    assert graph.superseded[0][1].provenance.state == ProvenanceState.INFERRED
    assert audit.records[-1]["action"] == "retract_node"


def test_retract_node_route_404_for_a_node_in_a_different_org_unit(fakes) -> None:
    client, _model, _candidates, graph, _audit = fakes
    graph.nodes["n1"] = _node("n1", ProvenanceState.ASSERTED, owning_unit="unit-2")

    response = client.post("/v1/investigations/inv-1/nodes/n1/retract")

    assert response.status_code == 404


def test_confirming_a_node_does_not_touch_an_unrelated_conflict_flagged_edge(fakes) -> None:
    """The user's own explicit ask when Stage 6 was scoped: confirming an inferred entity that
    happens to be part of a cluster carrying a recorded resolution conflict
    (`services/resolve/conflicts.py`, Stage 5) must not silently clear or hide that conflict.
    `confirm_node`/`retract_node` only ever call `GraphPort.get_node`/`supersede_node` against the
    target node id — there is no code path here that could reach a `NOT_SAME_AS` edge's
    `conflict_pending` property, and this test proves it rather than relying on that being
    architecturally obvious: the fake's `upserted`/`superseded` logs are exhaustive, and neither
    ever receives an edge."""
    client, _model, _candidates, graph, _audit = fakes
    graph.nodes["n1"] = _node("n1", ProvenanceState.INFERRED)

    response = client.post("/v1/investigations/inv-1/nodes/n1/confirm")

    assert response.status_code == 200
    # The only write this call could have made was to `n1` itself, via `supersede_node` — no
    # `upsert_edges`/`supersede_edge` call exists on this fake at all for confirm/retract to reach,
    # so a conflict-carrying `NOT_SAME_AS` edge elsewhere in the same cluster is structurally
    # unreachable from this code path, not merely untouched by coincidence in this one run.
    assert len(graph.superseded) == 1
    assert graph.superseded[0][0] == "n1"
