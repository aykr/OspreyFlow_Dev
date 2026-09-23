"""Export pipeline and handling gate — `03_CONDUIT_MIDDLEWARE.md` §6, `02_GLASS_FRONTEND.md` §10,
Phase 8 Stage 4d, against the accepted `06_DECISIONS.md` ADR-045/046/047.

**This is the operation with the least reversibility in the product.** Once `submit_export`
returns, an artefact exists outside this system's own boundary and "no principal re-checks
anything ever again" (`06_DECISIONS.md` ADR-045's own finding). Every check below runs *before*
that point, not after — there is no second chance.

**Backend only.** Stage 4e (`02_GLASS_FRONTEND.md` §10) renders the three artefact shapes
(chart/subgraph/report) and the handling-gate UI; this module supplies the gate, the mark, the
manifest and the ledger that every shape shares — there is one gate, not three
(`02_GLASS_FRONTEND.md` §10's own "10.1 Triggers" table).

**The cross-session access question, stated rather than assumed (this session's own Part 2
instruction).** The Glass's in-session working set and this module's own export-time evaluation
are two separate reads, and access can change between them — a handling reclassification, an
`org_unit` reassignment, a revocation. **Decided: the export gate re-checks the exporting
analyst's own *current* access to every item, fresh, at export time, never the in-session
snapshot.** For a `NodeId` item this is a real re-check — `graph.get_node` is called again here,
not trusted from whatever the client submitted, so a node reclassified or revoked since the
analyst built their selection is caught. For an `EdgeId` item this is only a *partial* re-check —
see the `GraphPort.get_edge` limitation below — disclosed, not silently narrower than the node
case without saying so.

**The `GraphPort.get_edge` limitation, inherited rather than newly introduced.** `GraphPort` has
no `get_edge` (already disclosed, for two other reasons). An edge's own `Handling` block is
instead taken from the client's
own submission (`ExportItem.handling`) — the edge *does* still get evaluated against the handling
scheme (`consult_originator`, classification dominance), so a stale-but-honest client is still
caught by the scheme check; what this module cannot do, and a node-shaped item's own `get_node`
recheck can, is independently confirm the client's submitted edge handling is still current, or
that the edge itself has not been revoked since the analyst selected it. **Consequence, stated
plainly:** a malicious or stale client could in principle submit fabricated edge-handling data
lower than the edge's real current classification and have it pass the scheme check that should
have blocked it — a real gap, not a theoretical one, closed only once `GraphPort.get_edge` exists.
**Disposition: whichever future work first builds `GraphPort.get_edge`** — the same disposition
already given to every other consequence of this same missing method, not invented here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import asyncpg
from pydantic import BaseModel, Field

from conduit_common.identity import new_id
from ontology.handling import HandlingScheme, evaluate_handling, principal_may_view
from ports.graph import GraphPort
from schemas.domain import Handling, Principal

from .assessments import JudgementStore, judgement_visible_to
from .working_set.service import WorkingSetService

# --- ADR-045: the withheld-item manifest policy ----------------------------------------------

ExportManifestPolicy = Literal["disclose", "omit"]

#: ADR-045's own decided default. Unlike ADR-038's `_NOTIFY_VALUE` (whitelist to the *narrower*
#: disclosure), this whitelists to the *narrower* mode too but the narrower mode here is `omit`,
#: not the default — the two switches are inverted on purpose (ADR-045's own "the opposite
#: fail-closed direction from ADR-038, and deliberately so"). An unset, empty or unrecognised
#: configuration value must resolve to `disclose`, so the whitelist match is against `"omit"`,
#: with everything else — including nothing at all — falling through to `disclose`.
_OMIT_VALUE = "omit"


def export_manifest_policy_from_value(raw: str | None) -> ExportManifestPolicy:
    """`06_DECISIONS.md` ADR-045's own fail-closed test: "An unset, empty or unrecognised
    configuration value means `disclose`." A whitelist match to exactly `"omit"`; every other
    value, including `None` and `""`, falls through to `disclose` — fail-closed by construction,
    the same shape `services/api/alerts.py::disclosure_policy_from_value` already established for
    ADR-038, with the opposite default."""
    return "omit" if raw == _OMIT_VALUE else "disclose"


# --- The gate ---------------------------------------------------------------------------------


class ExportItem(BaseModel):
    """One node or edge in the export selection, as the client (the Glass, which already holds
    each element's own `handling` block for rendering — `02_GLASS_FRONTEND.md` §4's provenance
    strokes) submits it. `handling` is the client's own snapshot — trusted outright for an edge
    (the `get_edge` limitation, above), re-fetched fresh from `graph` for a node."""

    id: str
    kind: Literal["node", "edge"]
    handling: Handling
    label: str = ""  #: A11y/copy-rules-shaped name for the blocked-item list (§7's own "name what
    #: happened"); falls back to `id` if the client submits nothing better.


class BlockedItem(BaseModel):
    """A15's own literal assertion: a blocking item is *named*, not merely counted."""

    id: str
    kind: Literal["node", "edge", "judgement"]
    label: str
    reason: Literal["access_denied", "consult_originator", "citation_unverifiable"]


class ExportBlockedError(Exception):
    """Raised by `evaluate_export_selection`/`submit_export` whenever anything in the selection
    cannot proceed — the same "fail loudly, name the specific thing, never a bare boolean" posture
    `services/api/assessments.py::UnverifiableCitationError` already established for the
    invisible-judgement defect's own fix, applied here to a whole selection rather than one
    judgement's own citations (a genuinely different shape — several named items, two distinct
    reasons, one of which is overridable and one of which never is — so this is its own error
    type rather than a forced reuse of a narrower one)."""

    def __init__(self, blocked: list[BlockedItem]) -> None:
        self.blocked = blocked
        self.access_denied = [b for b in blocked if b.reason == "access_denied"]
        self.consult_originator = [b for b in blocked if b.reason == "consult_originator"]
        self.citation_unverifiable = [b for b in blocked if b.reason == "citation_unverifiable"]
        names = ", ".join(f"{b.label} ({b.reason})" for b in blocked)
        super().__init__(f"export blocked: {names}")


class OverrideRequiredError(ExportBlockedError):
    """`03_CONDUIT_MIDDLEWARE.md` §6: "Override requires a justification and an originator
    reference, both recorded." A subclass of `ExportBlockedError`, not a sibling — every
    `consult_originator` block is, by definition, an `ExportBlockedError` (it blocks the export
    and names the item, A15's own literal assertion); this narrower type fires specifically when
    the caller's own override attempt is incomplete — zero, one, or the other of the two required
    fields, never both — so a caller that only cares "was I blocked" can catch the parent type,
    and one building the override form specifically can catch this one instead."""


async def evaluate_export_selection(
    items: list[ExportItem], principal: Principal, graph: GraphPort, scheme: HandlingScheme
) -> list[BlockedItem]:
    """The gate's own per-item pass. A node's `handling` is re-fetched fresh from `graph`
    (the cross-session recheck this module's own docstring commits to); an edge's is taken from
    `item.handling` as submitted (the disclosed `get_edge` limitation). `access_denied` is checked
    first and independently of `consult_originator` — an item the principal cannot currently see at
    all is a harder block than one they can see but need an originator's sign-off for, and the two
    are reported as distinct reasons rather than collapsed into one "blocked" bucket, since only
    one of them is ever overridable."""
    blocked: list[BlockedItem] = []
    for item in items:
        effective_handling: Handling = item.handling
        if item.kind == "node":
            node = await graph.get_node(item.id, principal)
            if node is None:
                blocked.append(
                    BlockedItem(
                        id=item.id,
                        kind=item.kind,
                        label=item.label or item.id,
                        reason="access_denied",
                    )
                )
                continue
            effective_handling = node.handling
        else:
            # Edge: no `get_edge` to re-fetch against — evaluate the client's own submission
            # directly (this module's own docstring has the full, disclosed limitation).
            if not principal_may_view(item.handling, principal, scheme):
                blocked.append(
                    BlockedItem(
                        id=item.id,
                        kind=item.kind,
                        label=item.label or item.id,
                        reason="access_denied",
                    )
                )
                continue

        decision = evaluate_handling(effective_handling, scheme)
        if decision.consult_originator:
            blocked.append(
                BlockedItem(
                    id=item.id,
                    kind=item.kind,
                    label=item.label or item.id,
                    reason="consult_originator",
                )
            )
    return blocked


async def verify_judgement_citations_for_export(
    judgement_ids: list[str],
    principal: Principal,
    graph: GraphPort,
    judgements: JudgementStore,
) -> list[BlockedItem]:
    """`06_DECISIONS.md` ADR-046's own export requirement: "the export handling gate must
    independently verify every exported judgement's own `supporting` citations against the
    *exporting analyst's* own access... if any citation falls outside it." Reuses
    `judgement_visible_to` — the identical function the live Judgements tab (Stage 4c) already
    calls at read time — rather than a second, parallel visibility check that could drift from it;
    the only difference here is *whose* principal is passed: the exporting analyst's, fresh, never
    the in-session viewer's."""
    blocked: list[BlockedItem] = []
    for judgement_id in judgement_ids:
        judgement = await judgements.get(judgement_id)
        if not await judgement_visible_to(judgement, principal, graph):
            blocked.append(
                BlockedItem(
                    id=judgement.id,
                    kind="judgement",
                    label=judgement.statement[:80],
                    reason="citation_unverifiable",
                )
            )
    return blocked


# --- ADR-047: the mark -------------------------------------------------------------------------


class ExportMark(BaseModel):
    """`03_CONDUIT_MIDDLEWARE.md` §6's own four provenance fields, plus `06_DECISIONS.md`
    ADR-047's own Gap 1 decision: the artefact's own highest handling level present, not only
    provenance. Machine-readable by construction — this object *is* the machine-readable form;
    Stage 4e's own job is rendering it visibly on each of the three artefact shapes
    (`02_GLASS_FRONTEND.md` §10.3), not this module's."""

    osprey_mark: Literal["OspreyFlow"] = "OspreyFlow"
    investigation_id: str
    exported_at: datetime
    resolution_threshold: float
    handling_level: str


def compute_handling_level(handlings: list[Handling], scheme: HandlingScheme) -> str:
    """The highest classification present across every item actually included in the export,
    per `06_DECISIONS.md` ADR-047's own "an artefact assembled from mixed-handling items must be
    treated at the level of its most sensitive component" reasoning — the same dominance order
    `HandlingScheme.clears`/`AccessFilter` already use, reused rather than a second ranking
    invented for this one purpose. Raises if `handlings` is empty — an export with nothing in it
    has no handling level to encode, and this function does not silently invent one (`ontology.
    errors.HandlingSchemeError` is the same error class every other handling-scheme misuse in
    this codebase already raises)."""
    if not handlings:
        raise ValueError("compute_handling_level: no items to derive a handling level from")
    ranked = {c: i for i, c in enumerate(scheme.classification)}
    highest = max(handlings, key=lambda h: ranked.get(h.classification, -1))
    return highest.classification


# --- The ledger — ADR-047's own Gap 2 --------------------------------------------------------


class ComplianceRoleRequiredError(Exception):
    """`06_DECISIONS.md` ADR-047's own Gap 2 decision: the ledger is "readable by a compliance
    principal without needing per-investigation access" — and, symmetrically, not readable by
    anyone lacking that role, the same shape `services/api/app.py::require_studio_role` already
    establishes for a different cross-cutting role."""


class ExportLedgerEntry(BaseModel):
    """**Metadata only — never content.** The fields below are exactly what a compliance
    principal needs to establish, after the fact, that an export happened and that process was
    followed: who exported, when, from which investigation, at what handling level, whether the
    withheld-item manifest was disclosed or suppressed, and whether an override justification and
    originator reference were recorded at all. **`justification`/`originator_reference` were
    found and fixed as a real defect, not kept as a disclosed limitation**: the field names
    originally carried the analyst's own free-text content — exactly the shape a `consult_
    originator` override's own justification would naturally take ("cleared because..."), which
    could itself name the withheld item, the originator, or other investigation content a
    compliance principal has no clearance for, reachable through the one route
    (`GET /v1/exports`) this system deliberately built to need none. Fixed to booleans:
    `justification_given`/`originator_reference_given` record the *fact* an override was properly
    recorded, never its content. The full text remains exactly where investigation-scoped access
    already governs it — the audit stream (`services/api/app.py::submit_export_route`'s own
    `audit.record(..., justification=body.justification)` call, `CLAUDE.md` standing rule 4)."""

    id: str
    investigation_id: str
    principal_id: str
    artefact_kind: Literal["chart", "subgraph", "report"]
    handling_level: str
    exported_at: datetime
    item_count: int
    withheld_count: int
    manifest_policy: ExportManifestPolicy
    justification_given: bool = False
    originator_reference_given: bool = False


_LEDGER_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS export_ledger (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    artefact_kind TEXT NOT NULL,
    handling_level TEXT NOT NULL,
    exported_at TIMESTAMPTZ NOT NULL,
    item_count INTEGER NOT NULL,
    withheld_count INTEGER NOT NULL,
    manifest_policy TEXT NOT NULL,
    justification_given BOOLEAN NOT NULL DEFAULT FALSE,
    originator_reference_given BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS export_ledger_investigation_id_idx ON export_ledger (investigation_id);
"""


class ExportLedgerStore:
    """**Deliberately not `investigations`-scoped and not `owning_unit`-filtered** — ADR-047's own
    Gap 2 reasoning: the ledger's entire value to compliance is that it is readable by someone who
    is not, and should not need to be, a principal on any investigation at all. `record` is written
    by the exporting analyst's own principal (any authorized exporter may write their own entry);
    only `list_all` is gated, by role, not by investigation."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> ExportLedgerStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_LEDGER_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def record(self, entry: ExportLedgerEntry) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO export_ledger (id, investigation_id, principal_id, artefact_kind, "
                "handling_level, exported_at, item_count, withheld_count, manifest_policy, "
                "justification_given, originator_reference_given) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                entry.id,
                entry.investigation_id,
                entry.principal_id,
                entry.artefact_kind,
                entry.handling_level,
                entry.exported_at,
                entry.item_count,
                entry.withheld_count,
                entry.manifest_policy,
                entry.justification_given,
                entry.originator_reference_given,
            )

    async def list_all(self, principal: Principal) -> list[ExportLedgerEntry]:
        """The one cross-investigation read in this module — `scripts/authorized_query_check.py`'s
        own detection shape is a syntactic, single-call check for a *principal-scoped* query; this
        method is deliberately *not* principal-scoped by investigation, the same disclosed,
        by-design exemption `06_DECISIONS.md` ADR-038's own addendum already establishes for
        `evaluate_hotlists_for_entry` — gated by role instead, checked explicitly below, not by the
        query's own `WHERE` clause."""
        if "compliance" not in principal.roles:
            raise ComplianceRoleRequiredError(principal.id)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM export_ledger ORDER BY exported_at DESC")
        return [
            ExportLedgerEntry(
                id=row["id"],
                investigation_id=row["investigation_id"],
                principal_id=row["principal_id"],
                artefact_kind=row["artefact_kind"],
                handling_level=row["handling_level"],
                exported_at=row["exported_at"],
                item_count=row["item_count"],
                withheld_count=row["withheld_count"],
                manifest_policy=row["manifest_policy"],
                justification_given=row["justification_given"],
                originator_reference_given=row["originator_reference_given"],
            )
            for row in rows
        ]


# --- Orchestration ------------------------------------------------------------------------------


class ExportManifest(BaseModel):
    policy: ExportManifestPolicy
    withheld_count: int | None = None  #: `None` under `omit` — the field is absent from the
    #: artefact's own payload in that mode, not zeroed (`06_DECISIONS.md` ADR-045's own option
    #: (c): "the artefact's own payload contains no manifest field").


class ExportResult(BaseModel):
    """`mark` is a required field, not `| None` — the type itself is `06_DECISIONS.md` ADR-047's
    own "the export pipeline never produces an artefact without a mark" guarantee: there is no
    code path that can construct an `ExportResult` without one, because Pydantic will not build
    the model without it. `submit_export` below is the only function that constructs this type."""

    mark: ExportMark
    manifest: ExportManifest
    ledger_entry_id: str


class ExportRequest(BaseModel):
    """No `withheld_count` field. **Found and fixed rather than left as the original disclosed
    limitation implied it could safely stay**: a caller-supplied count is not a narrower version
    of the real figure, it is a channel through which a client can make the manifest actively
    misstate completeness — the exact "an artefact that silently omits material misleads its
    reader" failure `06_DECISIONS.md` ADR-045 exists to prevent, now reachable through the one
    field that was supposed to be reporting it. `submit_export` (below) obtains the real count
    itself, server-side, from `WorkingSetService.withheld_count_for` — the same fix shape this
    stage's own node-handling recheck already applied to a client-submitted `handling` block,
    applied here to a client-submitted count instead."""

    artefact_kind: Literal["chart", "subgraph", "report"]
    items: list[ExportItem]
    judgement_ids: list[str] = Field(default_factory=list)
    resolution_threshold: float
    justification: str | None = None
    originator_reference: str | None = None


async def submit_export(
    *,
    investigation_id: str,
    request: ExportRequest,
    principal: Principal,
    graph: GraphPort,
    scheme: HandlingScheme,
    judgements: JudgementStore,
    ledger: ExportLedgerStore,
    working_set: WorkingSetService,
    manifest_policy: ExportManifestPolicy,
) -> ExportResult:
    """The one function that produces an `ExportResult` — every artefact shape (Stage 4e) calls
    this, not three separate pipelines (`02_GLASS_FRONTEND.md` §10's own "there is one gate, not
    three"). Order: evaluate the selection, evaluate the judgement citations, raise
    `ExportBlockedError` naming everything at once (not one item at a time, so an analyst sees the
    whole picture on the first attempt) unless every blocked item is a `consult_originator` one
    *and* a justification and originator reference were both supplied — raises
    `OverrideRequiredError` instead if only one of the two is present. Only once nothing blocks
    does it compute the mark and write the ledger entry; nothing before that point can produce
    a result."""
    if not request.items:
        raise ValueError("submit_export: an export with no items has nothing to evaluate")

    selection_blocked = await evaluate_export_selection(request.items, principal, graph, scheme)
    citation_blocked = await verify_judgement_citations_for_export(
        request.judgement_ids, principal, graph, judgements
    )
    blocked = selection_blocked + citation_blocked

    access_denied = [b for b in blocked if b.reason == "access_denied"]
    consult_originator = [b for b in blocked if b.reason == "consult_originator"]
    citation_unverifiable = [b for b in blocked if b.reason == "citation_unverifiable"]

    # access_denied and citation_unverifiable are never overridable — the principal cannot
    # currently see the item at all, so no justification changes that fact.
    if access_denied or citation_unverifiable:
        raise ExportBlockedError(access_denied + citation_unverifiable + consult_originator)

    if consult_originator:
        if not (request.justification and request.originator_reference):
            raise OverrideRequiredError(consult_originator)

    effective_handlings = [item.handling for item in request.items]
    # Nodes: use the *fresh* handling `evaluate_export_selection` already confirmed visible,
    # not the client's own submission — re-fetch once more here rather than thread it back out
    # of the gate, since a second `get_node` call is cheap and keeps the gate's own return shape
    # (a list of blocked items) from having to also carry every item's resolved handling.
    for i, item in enumerate(request.items):
        if item.kind == "node":
            node = await graph.get_node(item.id, principal)
            if node is not None:  # already confirmed non-None above; re-checked defensively
                effective_handlings[i] = node.handling

    handling_level = compute_handling_level(effective_handlings, scheme)
    exported_at = datetime.now(UTC)
    mark = ExportMark(
        investigation_id=investigation_id,
        exported_at=exported_at,
        resolution_threshold=request.resolution_threshold,
        handling_level=handling_level,
    )

    # The withheld count is never accepted from the client — `withheld_count_for` computes it
    # server-side, against `principal`'s own current access over the investigation's real,
    # unfiltered membership, the same figure the status bar already shows this analyst all
    # session. See `WorkingSetService.withheld_count_for`'s own docstring for why a caller-supplied
    # count was found and fixed as a real defect, not kept as a disclosed limitation.
    withheld_count = await working_set.withheld_count_for(investigation_id, principal)

    manifest = ExportManifest(
        policy=manifest_policy,
        withheld_count=withheld_count if manifest_policy == "disclose" else None,
    )

    entry = ExportLedgerEntry(
        id=new_id(),
        investigation_id=investigation_id,
        principal_id=principal.id,
        artefact_kind=request.artefact_kind,
        handling_level=handling_level,
        exported_at=exported_at,
        item_count=len(request.items),
        withheld_count=withheld_count,
        manifest_policy=manifest_policy,
        justification_given=bool(request.justification),
        originator_reference_given=bool(request.originator_reference),
    )
    await ledger.record(entry)

    return ExportResult(mark=mark, manifest=manifest, ledger_entry_id=entry.id)


__all__ = [
    "BlockedItem",
    "ComplianceRoleRequiredError",
    "ExportBlockedError",
    "ExportItem",
    "ExportLedgerEntry",
    "ExportLedgerStore",
    "ExportManifest",
    "ExportManifestPolicy",
    "ExportMark",
    "ExportRequest",
    "ExportResult",
    "OverrideRequiredError",
    "compute_handling_level",
    "evaluate_export_selection",
    "export_manifest_policy_from_value",
    "submit_export",
    "verify_judgement_citations_for_export",
]
