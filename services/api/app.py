"""The Conduit's FastAPI app — `docs/03_CONDUIT_MIDDLEWARE.md` §1/§3.

**Stateless.** Every `app.state` attribute below is a client for an
external store (ArcadeDB, Valkey, Postgres); none of it is session or
working-set state, which lives entirely in Valkey via `working_set/
store.py`. Two instances of this app, started independently, serve any
request for any investigation identically — `tests/services/api/
test_statelessness.py` is the proof this phase's exit criterion asks for
("kill the instance serving a session mid-investigation and the analyst
notices nothing").

**Every route audits before it discloses or before it returns success.**
`docs/00_ARCHITECTURE.md` §5 / `03_CONDUIT_MIDDLEWARE.md` §8: "an
unaudited read is worse than a refused one... Reject reads. This is the
one case where the platform fails closed." Each handler below performs
its `GraphPort`/`WorkingSetService` action first (a read's result
cardinality is only known once it has run), writes the audit row, and
only then returns — an `AuditWriteError` propagates as a 503 with nothing
disclosed to the caller, never a result returned alongside a swallowed
audit failure.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import GraphPort
from schemas.domain import Edge, ExpandRequest, Node, NodeId, OntologySchema, Principal

from . import search as search_module
from .audit import AuditWriteError, AuditWriter
from .auth import PrincipalResolutionError, PrincipalResolver, bearer_scheme
from .config import ApiConfig
from .history import (
    HistoryStep,
    HistoryStepNotFoundError,
    HistoryStepSummary,
    InvestigationHistoryStore,
)
from .investigations import Investigation, InvestigationNotFoundError, InvestigationStore
from .jobs import JobQueue
from .notify import notify_channel, publish_delta
from .search import SearchRequest, SearchResponse
from .working_set.models import (
    CardinalityPreview,
    DeltaNotice,
    DeltaRemove,
    DeltaSnapshot,
    ExpansionOutcome,
    LimitExceededError,
    WorkingSetDelta,
    decode_delta,
)
from .working_set.service import WorkingSetService
from .working_set.store import ValkeyWorkingSetStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = ApiConfig.from_env()

    arcadedb_client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await arcadedb_client.create_database_if_absent()
    handling_scheme = load_uk_le_scheme()
    ontology = load_default_ontology()
    graph: GraphPort = GraphArcadeDBAdapter(arcadedb_client, handling_scheme)
    await graph.apply_schema(ontology)

    valkey = Valkey(host=config.valkey.host, port=config.valkey.port, db=config.valkey.db)
    audit = await AuditWriter.connect(config.postgres.dsn)
    investigations = await InvestigationStore.connect(config.postgres.dsn)
    history = await InvestigationHistoryStore.connect(config.postgres.dsn)

    app.state.config = config
    app.state.graph = graph
    app.state.ontology = ontology
    app.state.valkey = valkey
    app.state.working_set = WorkingSetService(graph, ValkeyWorkingSetStore(valkey), handling_scheme)
    app.state.audit = audit
    app.state.investigations = investigations
    app.state.history = history
    app.state.jobs = JobQueue(valkey)
    app.state.principal_resolver = PrincipalResolver(config)

    try:
        yield
    finally:
        await arcadedb_client.aclose()
        await valkey.aclose()
        await audit.close()
        await investigations.close()
        await history.close()


app = FastAPI(title="OspreyFlow Conduit", lifespan=lifespan)

# The Glass is served from its own origin (`apps/workspace`'s Vite dev
# server locally; a separately-hosted static build in a real deployment)
# and calls this API cross-origin — discovered as a real gap, not a
# pre-empted one, the first time Checkpoint 2's canvas actually tried to
# call `/v1/ontology` from a browser and every request failed preflight.
# Read directly from the environment rather than through `ApiConfig`:
# that dataclass requires `OIDC_JWKS_URL` to be set (`config.py`'s own
# `from_env`), which many tests importing this module never set, since
# `app.dependency_overrides` bypasses `PrincipalResolver` entirely for
# them — middleware, unlike a dependency, must be registered before the
# app is used at all, not deferred into `lifespan`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(
        o.strip()
        for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- dependencies ---------------------------------------------------------


def get_working_set(request: Request) -> WorkingSetService:
    return request.app.state.working_set  # type: ignore[no-any-return]


def get_audit(request: Request) -> AuditWriter:
    return request.app.state.audit  # type: ignore[no-any-return]


def get_investigations(request: Request) -> InvestigationStore:
    return request.app.state.investigations  # type: ignore[no-any-return]


def get_history(request: Request) -> InvestigationHistoryStore:
    return request.app.state.history  # type: ignore[no-any-return]


def get_graph(request: Request) -> GraphPort:
    return request.app.state.graph  # type: ignore[no-any-return]


def get_ontology(request: Request) -> OntologySchema:
    return request.app.state.ontology  # type: ignore[no-any-return]


def get_valkey(request: Request) -> Valkey:
    return request.app.state.valkey  # type: ignore[no-any-return]


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> Principal:
    resolver: PrincipalResolver = request.app.state.principal_resolver
    try:
        return resolver.resolve(credentials.credentials)
    except PrincipalResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


WorkingSetDep = Annotated[WorkingSetService, Depends(get_working_set)]
AuditDep = Annotated[AuditWriter, Depends(get_audit)]
InvestigationsDep = Annotated[InvestigationStore, Depends(get_investigations)]
HistoryDep = Annotated[InvestigationHistoryStore, Depends(get_history)]
GraphDep = Annotated[GraphPort, Depends(get_graph)]
OntologyDep = Annotated[OntologySchema, Depends(get_ontology)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]


async def get_authorized_investigation(
    investigation_id: str,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    audit: AuditDep,
) -> Investigation:
    """The one gate every investigation-scoped route depends on instead of
    a bare `investigation_id` path param — divergence-review fix #1.
    `InvestigationStore.get_authorized` already collapses "no such
    investigation" and "wrong `owning_unit`" into the same exception,
    mapped to the same 404 by `_investigation_not_found_handler`; this
    wrapper's only addition is recording the denial in the audit stream
    before it propagates, same as every other action here."""
    try:
        return await investigations.get_authorized(investigation_id, principal)
    except InvestigationNotFoundError:
        await audit.record(
            principal=principal,
            action="access_denied",
            investigation_id=investigation_id,
            resolved_query={},
            result_cardinality=0,
        )
        raise


AuthorizedInvestigationDep = Annotated[Investigation, Depends(get_authorized_investigation)]


# --- exception handling ----------------------------------------------------


@app.exception_handler(LimitExceededError)
async def _limit_exceeded_handler(request: Request, exc: LimitExceededError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=exc.detail.model_dump())


@app.exception_handler(AuditWriteError)
async def _audit_write_error_handler(request: Request, exc: AuditWriteError) -> JSONResponse:
    # `03_CONDUIT_MIDDLEWARE.md` §8: "The audit stream is unavailable.
    # Reject reads. This is the one case where the platform fails
    # closed." 503, not 500: this is a named, expected failure mode with
    # its own documented behaviour, not an unhandled server error.
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "audit_unavailable", "detail": str(exc)},
    )


@app.exception_handler(InvestigationNotFoundError)
async def _investigation_not_found_handler(
    request: Request, exc: InvestigationNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "investigation_not_found"}
    )


@app.exception_handler(HistoryStepNotFoundError)
async def _history_step_not_found_handler(
    request: Request, exc: HistoryStepNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"error": "history_step_not_found"}
    )


# --- investigations ---------------------------------------------------------


@app.post("/v1/investigations", status_code=status.HTTP_201_CREATED)
async def create_investigation(
    principal: PrincipalDep, investigations: InvestigationsDep, audit: AuditDep
) -> Investigation:
    investigation = await investigations.create(principal)
    await audit.record(
        principal=principal,
        action="create_investigation",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=1,
    )
    return investigation


@app.get("/v1/investigations/{investigation_id}")
async def get_investigation(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    audit: AuditDep,
) -> Investigation:
    await audit.record(
        principal=principal,
        action="get_investigation",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=1,
    )
    return investigation


@app.post("/v1/investigations/{investigation_id}/branch", status_code=status.HTTP_201_CREATED)
async def branch_investigation(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    investigations: InvestigationsDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> Investigation:
    # `03_CONDUIT_MIDDLEWARE.md` §3.1: "fork the working set into a new
    # investigation" — one of the cap breach's three options, made real.
    # `AuthorizedInvestigationDep` has already checked the branching
    # principal against the *source* investigation's `owning_unit`; the
    # new investigation gets its own, from this principal, not inherited.
    new_investigation = await investigations.create(principal, branched_from=investigation.id)
    outcome = await working_set.branch(investigation.id, new_investigation.id, principal)
    await publish_delta(valkey, new_investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        new_investigation.id,
        seq=outcome.delta.seq,
        label=f"Branched from {investigation.id}",
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="branch",
        investigation_id=investigation.id,
        resolved_query={"new_investigation_id": new_investigation.id},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return new_investigation


async def _record_history_step(
    working_set: WorkingSetService,
    history: InvestigationHistoryStore,
    investigation_id: str,
    *,
    seq: int,
    label: str,
    principal: Principal,
) -> HistoryStep:
    """Called after every mutation that changes working-set membership
    (`07_BUILD_PLAN.md` Phase 4's "Named-step history with restore") — full
    current membership, not just the mutation's own delta, so the step is
    independently restorable (`history.py`'s module docstring)."""
    nodes, edges = await working_set.current_membership(investigation_id)
    return await history.record_step(
        investigation_id, seq=seq, label=label, created_by=principal.id, nodes=nodes, edges=edges
    )


# --- working set ------------------------------------------------------------


class SeedRequest(BaseModel):
    nodes: list[Node]
    edges: list[Edge] = []


class ExpandBody(BaseModel):
    request: ExpandRequest
    justification: str | None = None


class RemoveNodesRequest(BaseModel):
    node_ids: list[NodeId]


@app.post("/v1/investigations/{investigation_id}/seed")
async def seed(
    investigation: AuthorizedInvestigationDep,
    body: SeedRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> ExpansionOutcome:
    outcome = await working_set.seed(investigation.id, body.nodes, body.edges, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=f"Seeded {len(outcome.delta.nodes)} node(s)",
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="seed",
        investigation_id=investigation.id,
        resolved_query={"node_count": len(body.nodes), "edge_count": len(body.edges)},
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
    )
    return outcome


@app.post("/v1/investigations/{investigation_id}/expand")
async def expand(
    investigation: AuthorizedInvestigationDep,
    body: ExpandBody,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> ExpansionOutcome:
    outcome = await working_set.expand(investigation.id, body.request, principal)
    await publish_delta(valkey, investigation.id, outcome.delta)
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=outcome.delta.seq,
        label=(
            f"Expanded {len(outcome.delta.nodes)} node(s) from "
            f"{len(body.request.node_ids)} seed(s)"
        ),
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="expand",
        investigation_id=investigation.id,
        resolved_query=body.request.model_dump(mode="json"),
        result_cardinality=len(outcome.delta.nodes) + len(outcome.delta.edges),
        justification=body.justification,
    )
    return outcome


@app.post("/v1/investigations/{investigation_id}/expand/preview")
async def expand_preview(
    investigation: AuthorizedInvestigationDep,
    body: ExpandBody,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    audit: AuditDep,
) -> CardinalityPreview:
    preview = await working_set.expand_preview(investigation.id, body.request, principal)
    await audit.record(
        principal=principal,
        action="expand_preview",
        investigation_id=investigation.id,
        resolved_query=body.request.model_dump(mode="json"),
        result_cardinality=preview.candidate_node_count + preview.candidate_edge_count,
    )
    return preview


@app.delete("/v1/investigations/{investigation_id}/nodes")
async def remove_nodes(
    investigation: AuthorizedInvestigationDep,
    body: RemoveNodesRequest,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> dict[str, int]:
    seq = await working_set.remove(investigation.id, body.node_ids)
    await publish_delta(
        valkey, investigation.id, DeltaRemove(seq=seq, node_ids=list(body.node_ids))
    )
    await _record_history_step(
        working_set,
        history,
        investigation.id,
        seq=seq,
        label=f"Removed {len(body.node_ids)} node(s)",
        principal=principal,
    )
    await audit.record(
        principal=principal,
        action="remove_nodes",
        investigation_id=investigation.id,
        resolved_query={"node_ids": body.node_ids},
        result_cardinality=len(body.node_ids),
    )
    return {"seq": seq}


# --- named-step history -----------------------------------------------------


@app.get("/v1/investigations/{investigation_id}/history")
async def get_investigation_history(
    investigation: AuthorizedInvestigationDep,
    principal: PrincipalDep,
    history: HistoryDep,
    audit: AuditDep,
) -> list[HistoryStepSummary]:
    steps = await history.list_steps(investigation.id)
    await audit.record(
        principal=principal,
        action="get_history",
        investigation_id=investigation.id,
        resolved_query={},
        result_cardinality=len(steps),
    )
    return steps


@app.post("/v1/investigations/{investigation_id}/history/{step_id}")
async def restore_history_step(
    investigation: AuthorizedInvestigationDep,
    step_id: str,
    principal: PrincipalDep,
    working_set: WorkingSetDep,
    history: HistoryDep,
    audit: AuditDep,
    valkey: Annotated[Valkey, Depends(get_valkey)],
) -> DeltaSnapshot:
    step = await history.get_step(investigation.id, step_id)
    # `WorkingSetService.restore` re-projects `step`'s stored (unfiltered)
    # bodies against `principal` fresh — never the visibility `step` was
    # recorded with (`history.py`'s module docstring).
    snapshot = await working_set.restore(investigation.id, step.nodes, step.edges, principal)
    await publish_delta(valkey, investigation.id, snapshot)
    await audit.record(
        principal=principal,
        action="restore_history_step",
        investigation_id=investigation.id,
        resolved_query={"step_id": step_id},
        result_cardinality=len(snapshot.nodes) + len(snapshot.edges),
    )
    return snapshot


# --- search -------------------------------------------------------------------


@app.post("/v1/search")
async def search_route(
    body: SearchRequest,
    principal: PrincipalDep,
    graph: GraphDep,
    audit: AuditDep,
) -> SearchResponse:
    result = await search_module.search(graph, body, principal)
    await audit.record(
        principal=principal,
        action="search",
        resolved_query={"query": body.query},
        result_cardinality=len(result.nodes),
    )
    return result


# --- ontology -----------------------------------------------------------------


@app.get("/v1/ontology")
async def get_ontology_route(principal: PrincipalDep, ontology: OntologyDep) -> OntologySchema:
    """The Glass's channel/shape mapping (`docs/02_GLASS_FRONTEND.md` §4:
    "Hue is entity type; shape is entity type too") comes from here, not a
    hardcoded copy of `packages/ontology/default.yaml` in the frontend —
    the ontology already carries `EntityTypeDef.channel`/`.shape` per type,
    and duplicating that mapping client-side would drift the moment a
    deployment's ontology changes. Authenticated like every other route,
    but not investigation-scoped and not audited: this is deployment-wide
    schema *metadata* (entity/edge type names, channels, shapes,
    identifiers) — never a node, a property value or a count — the same
    category of thing `principal_may_view` was never meant to gate."""
    return ontology


# --- the delta stream --------------------------------------------------------


async def _authenticate_websocket(websocket: WebSocket) -> Principal:
    """`WebSocket` connections carry no `Authorization` header dependency
    injection the way an HTTP route does — the bearer token is read from
    the same header manually, once, before `accept()`.

    **A browser's native `WebSocket` cannot set that header at all** — a
    real gap Checkpoint 2 hit the first time the Glass tried to open this
    connection from an actual browser, not a pre-empted one. The `?token=`
    query parameter is this phase's resolution: the same long-lived JWT a
    browser client already holds and already sends as a Bearer header on
    every ordinary HTTP call, so this does not mint or expose a new
    credential — the marginal risk is a token appearing in this server's
    own access/proxy logs, which a Bearer header avoids. A short-lived,
    single-use "ticket" (minted by an authenticated HTTP call, exchanged
    here instead of the JWT itself) closes that gap properly and is named
    here as the production hardening this phase does not implement, not
    left silent. The `Authorization` header is still tried first, for a
    non-browser client (this phase's own `ws`-based integration test) that
    *can* set it.
    """
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[len("bearer ") :]
    else:
        token = websocket.query_params.get("token", "")
        if not token:
            raise PrincipalResolutionError("missing bearer token")
    resolver: PrincipalResolver = websocket.app.state.principal_resolver
    return resolver.resolve(token)


async def _forward_notifications(
    pubsub: Any, websocket: WebSocket, working_set: WorkingSetService, principal: Principal
) -> None:
    """Relays a live mutation from `notify.py`'s Pub/Sub channel to this
    one connected principal — re-projected via `WorkingSetService.
    project_delta` first, since the delta was recorded by whichever
    principal caused the mutation, who may not be this socket's principal
    (`03_CONDUIT_MIDDLEWARE.md` §4's read-time handling filter applies to
    the live push exactly as much as to reconnect replay)."""
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = message["data"]
        raw = decode_delta(json.loads(data.decode() if isinstance(data, bytes) else data))
        delta, hidden = working_set.project_delta(raw, principal)
        await websocket.send_text(delta.model_dump_json())
        if hidden > 0:
            notice = DeltaNotice(
                seq=delta.seq,
                message=f"{hidden} item(s) withheld by handling policy",
                count=hidden,
            )
            await websocket.send_text(notice.model_dump_json())


async def _handle_resync_requests(
    websocket: WebSocket,
    working_set: WorkingSetService,
    investigation_id: str,
    principal: Principal,
) -> None:
    while True:
        payload = await websocket.receive_json()
        last_ack = payload.get("last_acknowledged_seq")
        deltas = await working_set.sync(
            investigation_id, principal, last_acknowledged_seq=last_ack
        )
        for delta in deltas:
            await websocket.send_text(delta.model_dump_json())


@app.websocket("/v1/investigations/{investigation_id}/stream")
async def stream(websocket: WebSocket, investigation_id: str) -> None:
    """`03_CONDUIT_MIDDLEWARE.md` §3.2: "bidirectional delta channel".
    On connect, and on any later `{"last_acknowledged_seq": ...}` message
    from the client, replies with exactly what `WorkingSetService.sync`
    decides — the missed deltas, or a full snapshot when the gap can't be
    proven closed (never a silent patch attempt either way), both already
    filtered for this connection's own principal. Between those moments,
    deltas from *any* Conduit instance's mutation on this investigation
    arrive via `notify.py`'s Valkey Pub/Sub channel, so a seed/expand
    handled by a different instance than the one holding this socket
    still reaches the client live — also filtered per-connection."""
    try:
        principal = await _authenticate_websocket(websocket)
    except PrincipalResolutionError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    investigations: InvestigationStore = websocket.app.state.investigations
    audit: AuditWriter = websocket.app.state.audit
    try:
        await investigations.get_authorized(investigation_id, principal)
    except InvestigationNotFoundError:
        await audit.record(
            principal=principal,
            action="access_denied",
            investigation_id=investigation_id,
            resolved_query={},
            result_cardinality=0,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await audit.record(
        principal=principal,
        action="stream_connect",
        investigation_id=investigation_id,
        resolved_query={},
        result_cardinality=0,
    )
    working_set: WorkingSetService = websocket.app.state.working_set
    valkey: Valkey = websocket.app.state.valkey

    try:
        init = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    initial_deltas: list[WorkingSetDelta] = await working_set.sync(
        investigation_id, principal, last_acknowledged_seq=init.get("last_acknowledged_seq")
    )
    for delta in initial_deltas:
        await websocket.send_text(delta.model_dump_json())

    pubsub = valkey.pubsub()
    channel = notify_channel(investigation_id)
    await pubsub.subscribe(channel)
    try:
        forward_task = asyncio.create_task(
            _forward_notifications(pubsub, websocket, working_set, principal)
        )
        resync_task = asyncio.create_task(
            _handle_resync_requests(websocket, working_set, investigation_id, principal)
        )
        try:
            await asyncio.wait(
                {forward_task, resync_task}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in (forward_task, resync_task):
                task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]
