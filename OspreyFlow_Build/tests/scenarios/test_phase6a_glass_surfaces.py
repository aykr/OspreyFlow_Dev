"""Phase 6a's own exit criterion, end to end: "Acceptance scenario B's
B6, B9, B10 and B11 pass end to end against Phase 6's existing API." Four stages with
their own passing tests is not that, per this repository's own precedent: `test_phase3_working_
set.py` and `test_phase6_extraction_and_resolution.py` both exist because a scenario-shaped exit
criterion gets a test that runs the scenario, "against the live stack... rather than trusting each
stage's own tests to add up correctly" (Phase 6's own write-up).

Real FastAPI app (`services.api.app`), real ArcadeDB/Postgres/Valkey (`make dev-up`) — the same
`TestClient`-against-real-lifespan shape `test_phase3_working_set.py` established. "Against Phase
6's existing API" is this document's own phrase for what needs proving; every action below goes
through the same HTTP route the Glass itself calls for that action (`services/api/app.py`'s own
route table), in one investigation, as one principal, in the order Stage 1 seeds the rest: B11
(manual link) -> B9 (move the threshold) -> B10 (explain the resulting cluster) -> B6 (the
Dossier, on the document those two entities were extracted from).

**What this does not attempt, and why.** A literal Playwright-plus-live-Conduit run — the actual
rendered Glass, in a browser, against this same live stack — has no precedent anywhere in this
repository: all four existing Playwright suites (`keyboard/`, `a11y/`, `perf/`, `map-verify/`) boot
an isolated Vite harness with every network call intercepted via `page.route`, never a live Conduit
process. Building that combination — a live auth-token flow reaching the browser, a live Conduit
alongside Playwright's own `webServer`, CORS — is real, unscoped test infrastructure work in its
own right, not an extension of an existing pattern, so it is not attempted here rather than
asserted without having been run. This test proves what `test_phase3_working_set.py` already
established counts as "end to end" for an exit criterion in this codebase: the API surface the
Glass calls composes correctly, against the live stack, in one session. It does not prove a human
can operate the four screens — a disclosed gap, recorded
separately, as still outstanding.

**The two entities are minted by accepting real extraction candidates over the real accept
route — real Postgres, real ArcadeDB, real HTTP — but the candidates themselves are written
directly into Postgres rather than produced by a real model call.** The same choice
`test_phase6_extraction_and_resolution.py` makes for its own resolution clauses ("written
directly... since this clause is about the resolution mechanism, not extraction accuracy"): B6/B9/
B10/B11 are about the four Glass surfaces composing correctly, not about extraction accuracy
(already Phase 6's own, separately-proven concern), and the real pinned model's own documented
run-to-run variance would make the two specific entities this scenario threads through all four
steps nondeterministic for no benefit to what this test actually checks. **Accepting** them is
real, over HTTP, through the exact route the Glass calls (`accept_extraction_candidate_route`) —
that is the step this scenario needs proven (a pending candidate becoming a real, visible node),
not the extraction call ahead of it.

**B9's own honest mechanics, stated rather than glossed over.** A manual link (B11) writes a
`SAME_AS` edge with `score=1.0` (`01_DOMAIN_MODEL.md` §4) — which exceeds every valid τ
(`SetThresholdRequest.threshold` is bounded `[0.0, 1.0]`). `_manual_assertion` (`services/api/
working_set/service.py`) reprojects at the investigation's *current* τ inside the same call that
writes the edge, so the merge and its change summary (`DeltaReproject.merged`) appear in **B11's
own response**, before B9's threshold call ever runs — not a bug, the literal point of a manual
override being threshold-independent. B9's own subsequent `PUT` in this scenario therefore reports
a truthfully empty change (`merged=0`) — nothing left to newly merge — and this test asserts that
honestly rather than engineering a second, contrived pair just to force a non-zero count on that
specific call. What B9's step actually proves here is what matters for this composed story: the
threshold mechanism runs for real (a real reprojection, a real persisted τ) against a state B11
already produced, and that state survives the move unchanged — the same "a manual assertion is
stable under a subsequent resolution move" property `test_phase6_exit_criterion_end_to_end`'s own
clause 3 already proves for a split. A fresh Strict-to-Broad transition on a *Splink-scored* pair
(a score genuinely between the two bands) is exactly what that existing closing pass's own clause 2
already covers — repeating it here, on an unrelated pair, would not make this scenario more
thorough, only longer.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.review import ExtractionCandidateStore
from services.extract.candidates import ExtractionCandidate

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal
from tests.conftest import default_claims, sign_token

MESSAGE_TEXT = "Dana Mercer met Alex Doe at the depot."
NAME_A = "Dana Mercer"
NAME_B = "Alex Doe"
PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    """The same shape `test_phase3_working_set.py`'s own fixture uses — `ApiConfig.from_env()`
    reads these at lifespan startup, not import time, so setting them before `TestClient(app)`
    is entered is enough."""
    previous = {
        key: os.environ.get(key)
        for key in ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    }
    os.environ["OIDC_JWKS_URL"] = jwks_url
    os.environ["OIDC_ALGORITHMS"] = "RS256"
    os.environ["ARCADEDB_DATABASE"] = "ospreyflow"
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _bearer(private_key: rsa.RSAPrivateKey) -> dict[str, str]:
    token = sign_token(private_key, default_claims())
    return {"Authorization": f"Bearer {token}"}


def _handling() -> dict[str, str | None]:
    return {
        "classification": "OFFICIAL",
        "handling_code": "P",
        "originator": "unit-1",
        "owning_unit": "unit-1",
        "action_code": None,
        "sanitisation_code": None,
    }


def _locator(name: str) -> str:
    start = MESSAGE_TEXT.index(name)
    return f"char span {start}-{start + len(name)}"


def _candidate(
    document_id: str, name: str, given_names: str, family_name: str
) -> ExtractionCandidate:
    return ExtractionCandidate(
        id=new_id(),
        document_id=document_id,
        entity_type="Person",
        properties={"given_names": given_names, "family_name": family_name},
        confidence=0.9,
        model="qwen2.5:0.5b-instruct",
        locator=_locator(name),
        excerpt_hash="irrelevant-here",
        handling=_handling(),  # type: ignore[arg-type]
    )


async def _seed_candidates(document_id: str) -> tuple[str, str]:
    """Writes the document text and two `pending` candidates directly into the real Postgres
    store — see this module's own docstring for why extraction itself is not run for real here.
    Returns the two candidates' own ids, for the accept calls the test drives over HTTP below."""
    store = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.store_document_text(document_id, MESSAGE_TEXT, PRINCIPAL)
        (record_a, record_b) = await store.store(
            [
                _candidate(document_id, NAME_A, "Dana", "Mercer"),
                _candidate(document_id, NAME_B, "Alex", "Doe"),
            ],
            PRINCIPAL,
        )
        return record_a.id, record_b.id
    finally:
        await store.close()


async def _fetch_node_json(node_id: str) -> dict[str, Any]:
    """The node `accept_extraction_candidate_route` (called over HTTP below) just minted, fetched
    back directly against the same real `ospreyflow` ArcadeDB database the running `TestClient`
    app's own lifespan connects to (`api_env` above) — not `adapters.graph_arcadedb.testing.
    arcadedb_adapter`, which provisions its own, separate, uniquely-named database and would see
    nothing the app just wrote. The same direct-client pattern `test_phase3_working_set.py`'s own
    `_arrange_graph` already uses."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        node = await graph.get_node(node_id, PRINCIPAL)
        assert node is not None
        return node.model_dump(mode="json")
    finally:
        await client.aclose()


def test_phase6a_exit_criterion_end_to_end(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)

    document_id = new_id()
    candidate_a_id, candidate_b_id = asyncio.run(_seed_candidates(document_id))

    from services.api.app import app

    with TestClient(app) as client:
        created = client.post("/v1/investigations", headers=headers)
        assert created.status_code == 201, created.text
        investigation_id = created.json()["id"]

        # === Preamble: two real, pending candidates become two real, visible nodes — over the
        # === exact HTTP route the Glass's own "Accept" action calls, not a direct GraphPort write.
        accept_a = client.post(
            f"/v1/investigations/{investigation_id}/ingest/candidates/{candidate_a_id}/accept",
            headers=headers,
            json={},
        )
        assert accept_a.status_code == 200, accept_a.text
        node_a_id = accept_a.json()["node_id"]

        accept_b = client.post(
            f"/v1/investigations/{investigation_id}/ingest/candidates/{candidate_b_id}/accept",
            headers=headers,
            json={},
        )
        assert accept_b.status_code == 200, accept_b.text
        node_b_id = accept_b.json()["node_id"]

        node_a_json = asyncio.run(_fetch_node_json(node_a_id))
        node_b_json = asyncio.run(_fetch_node_json(node_b_id))

        seeded = client.post(
            f"/v1/investigations/{investigation_id}/seed",
            headers=headers,
            json={"nodes": [node_a_json, node_b_json], "edges": []},
        )
        assert seeded.status_code == 200, seeded.text

        # === B11 (Stage 1) — manual link, the interface's own action, seeding everything below.
        link_response = client.post(
            f"/v1/investigations/{investigation_id}/resolution/link",
            headers=headers,
            json={"node_a": node_a_id, "node_b": node_b_id},
        )
        assert link_response.status_code == 200, link_response.text
        link_delta = link_response.json()
        # This *is* "the merge with its change summary" (B9's own words) — see this module's own
        # docstring for exactly why it lands here, at link time, not at the threshold move below.
        assert link_delta["merged"] == 1
        assert link_delta["affected"] == 2
        cluster_id = min(node_a_id, node_b_id)  # `compute_clusters`'s own tie-break convention
        assert link_delta["delta"]["affected_cluster_ids"][node_a_id] == cluster_id
        assert link_delta["delta"]["affected_cluster_ids"][node_b_id] == cluster_id

        # === B9 (Stage 2) — move the threshold, for real: a genuine `PUT`, a genuine persisted τ,
        # === a genuine (truthfully empty) change summary — see this module's docstring for why
        # === `merged` is correctly 0 here rather than forced non-zero.
        threshold_response = client.put(
            f"/v1/investigations/{investigation_id}/resolution/threshold",
            headers=headers,
            json={"threshold": 0.80},
        )
        assert threshold_response.status_code == 200, threshold_response.text
        threshold_delta = threshold_response.json()
        assert threshold_delta["merged"] == 0
        assert threshold_delta["split"] == 0

        persisted = client.get(
            f"/v1/investigations/{investigation_id}/resolution/threshold", headers=headers
        )
        assert persisted.status_code == 200, persisted.text
        assert persisted.json()["threshold"] == 0.80

        # === B10 (Stage 3) — explain the resulting cluster: the per-comparison weights, not just
        # === the total, and (since this pair was manually asserted, not Splink-scored) the
        # === "Basis" column's own "Asserted by analyst" branch, driven by a real field, not text.
        explain_response = client.get(
            f"/v1/investigations/{investigation_id}/resolution/explain/{cluster_id}",
            headers=headers,
        )
        assert explain_response.status_code == 200, explain_response.text
        explanation = explain_response.json()
        assert set(explanation["member_node_ids"]) == {node_a_id, node_b_id}
        (pair,) = explanation["pairs"]
        assert {pair["node_a"], pair["node_b"]} == {node_a_id, node_b_id}
        assert pair["edge_type"] == "SAME_AS"
        assert pair["manually_asserted"] is True
        assert pair["score"] == 1.0

        # === B6 (Stage 4) — the Dossier, on the document those two entities were extracted from.
        dossier_response = client.get(
            f"/v1/investigations/{investigation_id}/dossier/documents/{document_id}",
            headers=headers,
        )
        assert dossier_response.status_code == 200, dossier_response.text
        document_view = dossier_response.json()
        assert document_view["text"] == MESSAGE_TEXT
        spans_by_node = {span["node_id"]: span for span in document_view["spans"]}
        assert set(spans_by_node) == {node_a_id, node_b_id}
        # Accepted, never confirmed — `inferred`, not `asserted` (that promotion is `/nodes/{id}/
        # confirm`'s own, separate action, not part of this exit criterion).
        assert spans_by_node[node_a_id]["provenance_state"] == "inferred"
        assert spans_by_node[node_b_id]["provenance_state"] == "inferred"
        a_start, a_end = spans_by_node[node_a_id]["start"], spans_by_node[node_a_id]["end"]
        assert document_view["text"][a_start:a_end] == NAME_A
        b_start, b_end = spans_by_node[node_b_id]["start"], spans_by_node[node_b_id]["end"]
        assert document_view["text"][b_start:b_end] == NAME_B
