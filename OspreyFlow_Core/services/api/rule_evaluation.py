"""Typology rules on the change-stream chassis (`06_DECISIONS.md` ADR-109 phase A).

A rule is one of `services/ingest/typologies.py`'s three typologies with its parameters (rule 8:
a closed vocabulary, no expression language), deployed by a case Author, evaluated as its
deployer's principal resolved fresh (ADR-036), at the trigger point it declares (ruling 1):

- **post-commit** — after a load commits, on its change-stream entry, best-effort, never failing
  the ingest (the ADR-036/037 discipline `evaluation.py` already follows for monitors);
- **pre-commit** — over the incoming rows inside the load, before the graph commit: a hit loads
  with its alert (the `Alert` node written in the same graph transaction as the rows), and a rule
  that errors or overruns its budget fails closed, holding the rows it could not judge.

**Where a flow comes from.** Same-pair `TRANSACTED` writes merge into one link (`engine.py`'s
`_write_edge`), so a single transaction is not a graph edge: it is an event in the analytics store
(`EventRecord`, carrying its amount, its time and both account node ids). A rule reads flows from
there, through `AnalyticsPort.list_events` and so with the access step in its `WHERE` clause
(rule 3); incoming flows a pre-commit rule judges are filtered by `handling_readable`, the same
predicate in Python, so a rule never fires on what its deployer could not read.

**Nothing truncated silently (rule 2).** The context read stops at `CONTEXT_CAP` events and raises
`RuleContextTooLarge` rather than judging a slice — for a pre-commit rule that is a failure, so the
rows are held; for a post-commit rule it is audited as a failure.

This module is the pure core (flows, typologies, the access predicate, the alert's marking) and
the evaluation entry points; stores live in `typology_rules.py` and `held_rows.py`.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from services.ingest.typologies import (
    MoneyFlow,
    TypologyHit,
    circular_flows,
    rapid_movement,
    structuring,
)
from services.resolve.trigger import service_principal
from valkey.asyncio import Valkey

from conduit_common.identity import new_edge_id, new_id, new_node_id
from conduit_common.valkey_compat import reply
from ontology.handling import HandlingScheme, merge_handling
from ports.analytics import AnalyticsPort
from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import (
    Alert,
    AlertMode,
    CircularFlowParams,
    EdgeWrite,
    Handling,
    HeldRow,
    Interval,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    RapidMovementParams,
    SourceRef,
    StructuringParams,
    TxId,
    TypologyRule,
)

from .alerts import AlertStore
from .audit import AuditWriter
from .held_rows import HeldRowStore
from .kyc_expiries import KycExpiryStore
from .pattern_store import PatternStore
from .screening import ScreeningListStore

#: The edge type whose events are money movements.
FLOW_EDGE_TYPE = "TRANSACTED"

#: The most context events one rule evaluation will read before refusing to judge a slice.
#: A guess, not a measurement — disclosed as `evaluation.py` discloses its own bounds.
CONTEXT_CAP = 10_000

TypologyParamsT = StructuringParams | RapidMovementParams | CircularFlowParams

#: The typologies judged over money movements; the rest (`kyc_rules.py`) over new customers.
FLOW_TYPOLOGIES = frozenset({"structuring", "rapid_movement", "circular_flow"})


def is_flow_rule(rule: TypologyRule) -> bool:
    return rule.params.typology in FLOW_TYPOLOGIES


class RuleContextTooLarge(Exception):
    """More context than `CONTEXT_CAP`: the rule refuses to judge part of it (rule 2)."""


def _amount(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def flows_from_events(events: Iterable[EventRecord]) -> list[MoneyFlow]:
    """Each `TRANSACTED` event with a numeric amount, as a flow citing its own event id. An event
    with no amount is not a movement of value and is not invented into one."""
    flows: list[MoneyFlow] = []
    for event in events:
        if event.edge_type != FLOW_EDGE_TYPE:
            continue
        amount = _amount(event.properties.get("amount"))
        if amount is None:
            continue
        flows.append(
            MoneyFlow(
                source=event.source_id,
                target=event.target_id,
                amount=amount,
                at=event.occurred_at,
                ref=event.event_id,
            )
        )
    return flows


def context_window(params: TypologyParamsT) -> timedelta:
    """How far either side of the judged flows a rule must read to see a whole pattern."""
    if isinstance(params, RapidMovementParams):
        return timedelta(hours=params.within_hours)
    return timedelta(days=params.window_days)


def run_typology(params: TypologyParamsT, flows: list[MoneyFlow]) -> list[TypologyHit]:
    if isinstance(params, StructuringParams):
        return structuring(
            flows,
            threshold=params.threshold,
            window=timedelta(days=params.window_days),
            minimum_count=params.minimum_count,
        )
    if isinstance(params, RapidMovementParams):
        return rapid_movement(
            flows,
            within=timedelta(hours=params.within_hours),
            keep_fraction=params.keep_fraction,
        )
    return circular_flows(flows, max_hops=params.max_hops)


def transaction_key(event: EventRecord) -> tuple[object, ...]:
    """What makes two events the same transaction: one link, one moment, one amount, the same
    ends. Re-running an export writes its events to the analytics store again under new ids
    (`load_events` inserts; found building ADR-109 phase A), so a rule must not read one movement
    as two — it would find structuring in a single deposit loaded twice."""
    return (
        event.edge_id,
        event.source_id,
        event.target_id,
        event.occurred_at,
        _amount(event.properties.get("amount")),
    )


def one_per_transaction(events: Iterable[EventRecord]) -> dict[tuple[object, ...], EventRecord]:
    """Each transaction once, as its earliest-loaded event (the lowest id: ids are ULIDs), so the
    same finding cites the same events however many times its export was loaded."""
    chosen: dict[tuple[object, ...], EventRecord] = {}
    for event in events:
        key = transaction_key(event)
        if key not in chosen or event.event_id < chosen[key].event_id:
            chosen[key] = event
    return chosen


def hits_citing(hits: Iterable[TypologyHit], event_ids: set[str]) -> list[TypologyHit]:
    """The hits this load is responsible for: those citing at least one of its events. A pattern
    made wholly of flows already there was there before, and is not this load's finding."""
    return [h for h in hits if event_ids.intersection(h.refs)]


def hit_signature(rule_id: str, hit: TypologyHit) -> str:
    """One finding, one signature, whichever order its flows were read in — so it alerts once."""
    raw = "|".join([rule_id, hit.typology, hit.subject, *sorted(hit.refs)])
    return hashlib.sha256(raw.encode()).hexdigest()


def handling_readable(scheme: HandlingScheme, principal: Principal, handling: Handling) -> bool:
    """The adapters' access predicate in Python (`adapters/analytics_duckdb/access_filter.py`):
    the classification within the clearance, and the handling code either not restricted or one the
    principal may receive from their own unit (as owner or originator). Used where there is no query
    to inject it into — events a pre-commit rule judges before they reach any store."""
    try:
        if not scheme.clears(principal.clearance, handling.classification):
            return False
    except Exception:  # noqa: BLE001 - a marking outside the scheme is not readable
        return False
    code = scheme.handling_codes.get(handling.handling_code)
    if code is None:
        return False
    if code.dissemination != "restricted":
        return True
    return handling.handling_code in principal.receivable_handling_codes and (
        principal.org_unit in (handling.owning_unit, handling.originator)
    )


def alert_handling(scheme: HandlingScheme, handlings: Sequence[Handling]) -> Handling | None:
    """The marking of an `Alert` node: never lower than anything it references (ADR-109 ruling 2),
    so only a reader who can read every referent can read the alert (rule 3). `merge_handling`
    gives the highest classification and narrowest codes, but keeps one owning unit and originator;
    when a restricted code is among the referents and they do not all share one unit and
    originator, no single marking is safe — `None`, and the caller withholds the node (the queue
    row stays, its evidence re-checked per reader, ADR-039)."""
    if not handlings:
        return None
    restricted = {
        c for c, d in scheme.handling_codes.items() if d.dissemination == "restricted"
    }
    if any(h.handling_code in restricted for h in handlings):
        units = {(h.owning_unit, h.originator) for h in handlings}
        if len(units) > 1:
            return None
    marking = handlings[0]
    for other in handlings[1:]:
        marking = merge_handling(marking, other, scheme)
    return marking


# --- reading context, judging, raising --------------------------------------
#
# Everything below reads or writes; the functions above are pure.


_PAGE = 200
_SIGNATURES_PREFIX = "rule:alerted:"

#: Every audit action this module writes — the rule audit's whole vocabulary (ruling 1), which the
#: inspection read selects on.
RULE_AUDIT_ACTIONS: tuple[str, ...] = (
    "rule_deployed",
    "rule_retired",
    "rule_evaluated",
    "rule_fired",
    "rule_failed",
    "rows_held",
    "rows_released",
    "rows_rejected",
    "alert_node_withheld",
)


async def read_flow_events(
    analytics: AnalyticsPort,
    principal: Principal,
    *,
    investigation_scope: str,
    node_ids: Sequence[str],
    window: Interval,
) -> list[EventRecord]:
    """Every money-movement event touching `node_ids` within `window` that `principal` may read —
    the access step in the adapter's own `WHERE` clause. Pages to the end; more than
    `CONTEXT_CAP` is refused, never sliced (rule 2)."""
    events: list[EventRecord] = []
    offset = 0
    while True:
        page = await analytics.list_events(
            EventListRequest(
                filter=EventFilter(
                    investigation_scope=investigation_scope,
                    window=window,
                    node_ids=list(node_ids),
                    edge_types=[FLOW_EDGE_TYPE],
                ),
                offset=offset,
                limit=_PAGE,
            ),
            principal,
        )
        if page.total > CONTEXT_CAP:
            raise RuleContextTooLarge(
                f"{page.total:,} money movements around these accounts, more than the "
                f"{CONTEXT_CAP:,} a rule reads at once — not judged on part of them"
            )
        events.extend(page.events)
        offset += len(page.events)
        if not page.events or offset >= page.total:
            return events


@dataclass(frozen=True)
class Finding:
    """One thing a rule found, with what makes it explainable in hand: a typology's hit over flows
    (`from_hit`, its events cited) or a KYC finding about entities (`kyc_rules.py`, its nodes and
    links named, and anything it writes alongside its alert — a screening match's listed party and
    its `SAME_AS` — in `pending`)."""

    rule: TypologyRule
    deployer: Principal
    typology: str
    subject: str
    refs: tuple[str, ...]
    words: str
    node_ids: list[str]
    edge_ids: list[str] = field(default_factory=list)
    events: tuple[EventRecord, ...] = ()
    pending: tuple[NodeWrite | EdgeWrite, ...] = ()

    @classmethod
    def from_hit(
        cls,
        rule: TypologyRule,
        deployer: Principal,
        hit: TypologyHit,
        events: tuple[EventRecord, ...],
    ) -> Finding:
        return cls(
            rule=rule,
            deployer=deployer,
            typology=hit.typology,
            subject=hit.subject,
            refs=hit.refs,
            words=hit.words,
            node_ids=sorted({e.source_id for e in events} | {e.target_id for e in events}),
            edge_ids=sorted({e.edge_id for e in events}),
            events=events,
        )

    @property
    def signature(self) -> str:
        raw = "|".join([self.rule.id, self.typology, self.subject, *sorted(self.refs)])
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def window(self) -> Interval | None:
        times = [e.occurred_at for e in self.events]
        return Interval(valid_from=min(times), valid_to=max(times)) if times else None


async def judge(
    rule: TypologyRule,
    deployer: Principal,
    incoming: Sequence[EventRecord],
    *,
    analytics: AnalyticsPort,
    scheme: HandlingScheme,
    investigation_scope: str,
) -> list[Finding]:
    """The rule over this load's events and the flows around them. Only events the deployer may
    read are judged or read (rule 3); only findings citing one of this load's events count."""
    judged = [
        e
        for e in incoming
        if e.edge_type == FLOW_EDGE_TYPE and handling_readable(scheme, deployer, e.handling)
    ]
    params = rule.params
    if not isinstance(params, (StructuringParams, RapidMovementParams, CircularFlowParams)):
        return []
    if not flows_from_events(judged):
        return []
    reach = context_window(params)
    times = [e.occurred_at for e in judged]
    accounts = sorted({e.source_id for e in judged} | {e.target_id for e in judged})
    context = await read_flow_events(
        analytics,
        deployer,
        investigation_scope=investigation_scope,
        node_ids=accounts,
        window=Interval(valid_from=min(times) - reach, valid_to=max(times) + reach),
    )
    canonical = one_per_transaction([*context, *judged])
    by_id = {e.event_id: e for e in canonical.values()}
    hits = hits_citing(
        run_typology(params, flows_from_events(by_id.values())),
        {canonical[transaction_key(e)].event_id for e in judged},
    )
    return [
        Finding.from_hit(rule, deployer, h, tuple(by_id[r] for r in h.refs))
        for h in hits
    ]


async def _referent_handlings(
    graph: GraphPort,
    scheme: HandlingScheme,
    finding: Finding,
    unseen: Handling | None,
    known: Mapping[str, Handling],
) -> list[Handling]:
    """The markings an alert must not be lower than: every cited event's, everything it writes
    alongside, and every referenced node's as stored. A node not yet committed (written in this
    very load's transaction) cannot be read back: its marking as written (`known`) stands in, else
    `unseen` — the highest marking the load's recipe could give it."""
    handlings = [e.handling for e in finding.events]
    pending = {w.id: w.handling for w in finding.pending}
    handlings.extend(pending.values())
    reader = service_principal(scheme)
    for node_id in finding.node_ids:
        if node_id in pending:
            continue
        if node_id in known:
            handlings.append(known[node_id])
            continue
        node = await graph.get_node(node_id, reader)
        if node is not None:
            handlings.append(node.handling)
        elif unseen is not None:
            handlings.append(unseen)
        else:
            raise RuntimeError(f"alert referent {node_id} could not be read for its marking")
    return handlings


async def write_alert_node(
    graph: GraphPort,
    scheme: HandlingScheme,
    finding: Finding,
    tx: TxId,
    *,
    unseen: Handling | None = None,
    load_id: str | None = None,
    known: Mapping[str, Handling] | None = None,
    writes: RuleWrites | None = None,
) -> str | None:
    """The `Alert` node and its `ALERTED_ON` links, in `tx` — at the highest marking of what it
    references, `inferred`, attributed to the rule (ruling 2; rules 3 and 5) — after anything the
    finding writes alongside (`pending`). `None` when no single marking is safe
    (`alert_handling`): the node is withheld, the queue row still raised."""
    record = writes if writes is not None else RuleWrites()
    if finding.pending:
        pending_nodes = [w for w in finding.pending if isinstance(w, NodeWrite)]
        pending_edges = [w for w in finding.pending if isinstance(w, EdgeWrite)]
        record.node_ids.extend(await graph.upsert_nodes(pending_nodes, tx))
        record.edges(pending_edges, await graph.upsert_edges(pending_edges, tx))
    marking = alert_handling(
        scheme, await _referent_handlings(graph, scheme, finding, unseen, known or {})
    )
    if marking is None:
        return None
    now = datetime.now(UTC)
    provenance = Provenance(
        state=ProvenanceState.INFERRED,
        sources=[
            SourceRef(document_id=f"rule:{finding.rule.id}", locator=ref, excerpt_hash="")
            for ref in finding.refs
        ],
        extracted_by=f"rule:{finding.rule.id}",
        first_seen=now,
    )
    node = NodeWrite(
        id=new_node_id(),
        type="Alert",
        properties={
            "rule_id": finding.rule.id,
            "typology": finding.typology,
            "words": finding.words,
            "raised_at": now.isoformat(),
        },
        provenance=provenance,
        handling=marking,
        created_by=finding.deployer.id,
        created_at=now,
        load_id=load_id,
    )
    (node_id,) = await graph.upsert_nodes([node], tx)
    record.node_ids.append(node_id)
    alerted = [
        EdgeWrite(
            id=new_edge_id(),
            type="ALERTED_ON",
            source=node_id,
            target=target,
            basis="probabilistic",
            provenance=provenance,
            handling=marking,
            created_by=finding.deployer.id,
            created_at=now,
            load_id=load_id,
        )
        for target in finding.node_ids
    ]
    record.edges(alerted, await graph.upsert_edges(alerted, tx))
    return node_id


def alert_row(finding: Finding, alert_node_id: str | None, investigation_id: str) -> Alert:
    return Alert(
        id=new_id(),
        rule_id=f"typology:{finding.rule.id}",
        owner_id=finding.deployer.id,
        mode=AlertMode.FULL,
        referent_node_ids=finding.node_ids,
        investigation_id=investigation_id,
        created_at=datetime.now(UTC),
        dataset_id=finding.rule.dataset_id,
        typology=finding.typology,
        words=finding.words,
        edge_ids=finding.edge_ids,
        event_ids=[e.event_id for e in finding.events],
        window=finding.window,
        trigger=finding.rule.trigger,
        alert_node_id=alert_node_id,
    )


def _source_rows(event: EventRecord) -> list[int]:
    rows = event.properties.get("source_rows") or []
    return [int(r) for r in rows if isinstance(r, (int, str)) and str(r).lstrip("-").isdigit()]


@dataclass
class RuleWrites:
    """The graph elements a rule wrote for a load (ADR-127 decision 6): an `Alert` node, its
    `ALERTED_ON` links and anything the finding writes alongside (`pending`). They belong to the
    load, so its record lists them. A write that returns another element's id merged into it: a
    pending link between two parties already linked is the same link."""

    node_ids: list[str] = field(default_factory=list)
    created_edge_ids: list[str] = field(default_factory=list)
    merged_edge_ids: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.node_ids or self.created_edge_ids or self.merged_edge_ids)

    def edges(self, written: Sequence[EdgeWrite], returned: Sequence[str]) -> None:
        for write, edge_id in zip(written, returned, strict=True):
            (self.created_edge_ids if edge_id == write.id else self.merged_edge_ids).append(edge_id)


@dataclass
class PreCommitVerdict:
    """What the case's pre-commit rules decided about one load, before its commit."""

    findings: list[tuple[Finding, str | None]] = field(default_factory=list)
    #: Rows a failing rule could not judge, by original row number, with the failing rule and why.
    hold: dict[int, tuple[TypologyRule, str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    #: What the rules wrote into the load's transaction, for the load's record.
    writes: RuleWrites = field(default_factory=RuleWrites)


@dataclass
class RuleGate:
    """The case's rules, for one load: `pre_commit` inside the transaction, `after_commit` once it
    has committed, `post_commit` once the load's events are in the analytics store. Built per
    request by the run route; `fail_closed=False` for a reviewer's release, whose decision is the
    human judgement a failing rule would otherwise wait for."""

    rules: list[TypologyRule]
    investigation_id: str
    graph: GraphPort
    analytics: AnalyticsPort | None
    scheme: HandlingScheme
    alert_store: AlertStore
    audit: AuditWriter
    valkey: Valkey
    principal_for_owner: Callable[[str], Awaitable[Principal | None]]
    loader: Principal
    held_store: HeldRowStore | None = None
    fail_closed: bool = True
    #: ADR-109 phase F: what the KYC typologies read — the screening lists, and the ownership maths
    #: for screening an organisation's beneficial owners.
    screening: ScreeningListStore | None = None
    compute: ComputePort | None = None
    #: ADR-109 phase D: where a drawn pattern rule's saved pattern is read from.
    patterns: PatternStore | None = None
    #: What the last load wrote, kept for its post-commit rules (set by `load_with_rules`).
    last_written: Sequence[NodeWrite | EdgeWrite] = ()
    #: ADR-109 phase F: where a verifying document's expiry is recorded for the daily sweep.
    expiries: KycExpiryStore | None = None

    async def record_expiries(self, written: Sequence[NodeWrite | EdgeWrite]) -> int:
        """Every verifying document this load wrote that carries an expiry, recorded so the
        daily sweep can find the ones that lapse (the change stream never sees a clock pass)."""
        if self.expiries is None:
            return 0
        documents = {
            w.id: w
            for w in written
            if isinstance(w, NodeWrite) and w.type == "Document" and w.properties.get("expires_on")
        }
        pairs = [
            (w.target, w.source, str(documents[w.target].properties["expires_on"])[:10])
            for w in written
            if isinstance(w, EdgeWrite) and w.type == "VERIFIED_BY" and w.target in documents
        ]
        return await self.expiries.record(self.investigation_id, pairs)

    async def _deployer(self, rule: TypologyRule) -> Principal | None:
        deployer = await self.principal_for_owner(rule.owner_id)
        if deployer is not None and rule.dataset_id is not None:
            deployer = deployer.model_copy(update={"datasets": [rule.dataset_id]})
        return deployer

    async def _audit(self, action: str, detail: dict[str, object], count: int = 0) -> None:
        await self.audit.record(
            principal=self.loader,
            action=action,
            investigation_id=self.investigation_id,
            resolved_query=detail,
            result_cardinality=count,
        )

    async def hold(self, rows: Sequence[HeldRow]) -> None:
        """Into the quarantine, audited. With no quarantine to hold them in, holding cannot be
        honoured, and saying the rows were held when they were dropped would be a silent part-load
        (rule 2): refused."""
        if not rows:
            return
        if self.held_store is None:
            raise RuntimeError("rows had to be held and this run has no quarantine to hold them")
        await self.held_store.hold(rows)
        await self._audit(
            "rows_held",
            {"load_id": rows[0].load_id, "rule_ids": sorted({r.rule_id for r in rows}),
             "rows": [r.row_index for r in rows]},
            len(rows),
        )

    async def _seen(self, finding: Finding) -> bool:
        return bool(
            await reply(
                self.valkey.sismember(f"{_SIGNATURES_PREFIX}{finding.rule.id}", finding.signature)
            )
        )

    async def _remember(self, finding: Finding) -> None:
        await reply(self.valkey.sadd(f"{_SIGNATURES_PREFIX}{finding.rule.id}", finding.signature))

    async def _judge_rule(
        self,
        rule: TypologyRule,
        deployer: Principal,
        events: Sequence[EventRecord],
        written: Sequence[NodeWrite | EdgeWrite],
    ) -> list[Finding]:
        """A flow typology over the load's money movements; a KYC typology over its new customers
        (`kyc_rules.py`, imported here, not at the top: it builds on this module)."""
        if is_flow_rule(rule):
            if self.analytics is None:
                raise RuntimeError(
                    "this run has no analytics store to read the flows around these accounts"
                )
            return await judge(
                rule,
                deployer,
                events,
                analytics=self.analytics,
                scheme=self.scheme,
                investigation_scope=self.investigation_id,
            )
        if rule.params.typology == "pattern":
            from .pattern_rules import judge_pattern

            return await judge_pattern(
                rule, deployer, written, graph=self.graph, patterns=self.patterns
            )
        from .kyc_rules import KycContext, judge_kyc

        context = KycContext(
            graph=self.graph,
            scheme=self.scheme,
            screening=self.screening,
            compute=self.compute,
            today=datetime.now(UTC).date(),
        )
        return await judge_kyc(rule, deployer, written, context)

    @staticmethod
    def _rows_for(
        rule: TypologyRule,
        events: Sequence[EventRecord],
        written: Sequence[NodeWrite | EdgeWrite],
    ) -> list[int]:
        """The rows a rule judges, and so would hold were it to fail: those carrying a money
        movement for a flow typology; those that created a customer for a KYC one."""
        if rule.params.typology == "pattern":
            return []  # a drawn pattern runs after commit only; it never holds a row
        if is_flow_rule(rule):
            return sorted(
                {r for e in events if e.edge_type == FLOW_EDGE_TYPE for r in _source_rows(e)}
            )
        from .kyc_rules import CUSTOMER_TYPES, customer_rows

        return customer_rows(
            [w for w in written if isinstance(w, NodeWrite) and w.type in CUSTOMER_TYPES]
        )

    async def pre_commit(
        self,
        events: Sequence[EventRecord],
        tx: TxId,
        *,
        load_id: str,
        unseen: Handling | None,
        written: Sequence[NodeWrite | EdgeWrite] = (),
    ) -> PreCommitVerdict:
        verdict = PreCommitVerdict()
        known = {w.id: w.handling for w in written if isinstance(w, NodeWrite)}
        for rule in (r for r in self.rules if r.trigger == "pre_commit"):
            flow_rows = self._rows_for(rule, events, written)
            reason: str | None = None
            findings: list[Finding] = []
            deployer = await self._deployer(rule)
            if deployer is None:
                reason = "the rule's deployer could not be resolved, so it could not run as them"
            else:
                try:
                    async with asyncio.timeout(rule.budget_ms / 1000):
                        findings = await self._judge_rule(rule, deployer, events, written)
                except TimeoutError:
                    reason = f"it overran its {rule.budget_ms:,} ms budget"
                except Exception as exc:  # noqa: BLE001 - a failing rule fails closed, in words
                    reason = f"it failed: {exc}"
            if reason is not None:
                await self._audit(
                    "rule_failed",
                    {"rule_id": rule.id, "trigger": "pre_commit", "load_id": load_id,
                     "reason": reason, "rows": flow_rows},
                    len(flow_rows),
                )
                if self.fail_closed:
                    for row in flow_rows:
                        verdict.hold.setdefault(row, (rule, reason))
                    verdict.notes.append(
                        f"Rule “{rule.name}” could not judge {len(flow_rows)} row(s) — "
                        f"{reason}; they are held for review, not loaded."
                    )
                else:
                    verdict.notes.append(
                        f"Rule “{rule.name}” could not judge this release — {reason}; "
                        "loaded on the reviewer's decision."
                    )
                continue
            assert deployer is not None
            fresh = [f for f in findings if not await self._seen(f)]
            await self._audit(
                "rule_evaluated",
                {"rule_id": rule.id, "trigger": "pre_commit", "load_id": load_id,
                 "findings": len(fresh)},
                len(fresh),
            )
            for finding in fresh:
                try:
                    node_id = await write_alert_node(
                        self.graph,
                        self.scheme,
                        finding,
                        tx,
                        unseen=unseen,
                        load_id=load_id,
                        known=known,
                        writes=verdict.writes,
                    )
                except RuntimeError:
                    # A referent's marking cannot be known: no node rather than a guessed one.
                    node_id = None
                verdict.findings.append((finding, node_id))
            if fresh:
                verdict.notes.append(f"Rule “{rule.name}” raised {len(fresh)} alert(s).")
        return verdict

    async def after_commit(self, verdict: PreCommitVerdict) -> list[Alert]:
        """The queue rows for what `pre_commit` wrote into the committed graph."""
        return [await self._raise_row(f, node_id) for f, node_id in verdict.findings]

    async def _raise_row(self, finding: Finding, node_id: str | None) -> Alert:
        alert = alert_row(finding, node_id, self.investigation_id)
        await self.alert_store.save(alert)
        await self._remember(finding)
        detail: dict[str, object] = {
            "rule_id": finding.rule.id,
            "alert_id": alert.id,
            "trigger": finding.rule.trigger,
            "words": finding.words,
            "node_ids": finding.node_ids,
        }
        await self._audit("rule_fired", detail, 1)
        if node_id is None:
            await self._audit(
                "alert_node_withheld",
                {"rule_id": finding.rule.id, "alert_id": alert.id, "node_ids": finding.node_ids,
                 "reason": "its referents' restricted markings belong to different units"},
            )
        return alert

    async def raise_committed(
        self, finding: Finding, *, load_id: str | None = None, writes: RuleWrites | None = None
    ) -> Alert:
        """A finding raised outside any load's transaction (after commit, or by the daily sweep):
        its node in a transaction of its own, then its queue row. `writes` collects what it wrote,
        for the record of the load it follows."""
        tx = await self.graph.begin_transaction()
        try:
            node_id = await write_alert_node(
                self.graph, self.scheme, finding, tx, load_id=load_id, writes=writes
            )
        except Exception:
            await self.graph.rollback_transaction(tx)
            raise
        await self.graph.commit_transaction(tx)
        return await self._raise_row(finding, node_id)

    async def seen(self, finding: Finding) -> bool:
        return await self._seen(finding)

    async def post_commit(
        self,
        events: Sequence[EventRecord],
        *,
        load_id: str,
        written: Sequence[NodeWrite | EdgeWrite] = (),
        writes: RuleWrites | None = None,
    ) -> list[str]:
        """The case's post-commit rules, over the committed load's events and new customers —
        best-effort: a failure is audited and said, never raised into the load (ADR-036/037)."""
        notes: list[str] = []
        for rule in (r for r in self.rules if r.trigger == "post_commit"):
            try:
                deployer = await self._deployer(rule)
                if deployer is None:
                    raise RuntimeError("the rule's deployer could not be resolved")
                findings = await self._judge_rule(rule, deployer, events, written)
                fresh = [f for f in findings if not await self._seen(f)]
                await self._audit(
                    "rule_evaluated",
                    {"rule_id": rule.id, "trigger": "post_commit", "load_id": load_id,
                     "findings": len(fresh)},
                    len(fresh),
                )
                for finding in fresh:
                    await self.raise_committed(finding, load_id=load_id, writes=writes)
                if fresh:
                    notes.append(f"Rule “{rule.name}” raised {len(fresh)} alert(s).")
            except Exception as exc:  # noqa: BLE001 - best-effort, audited and said
                await self._audit(
                    "rule_failed",
                    {"rule_id": rule.id, "trigger": "post_commit", "load_id": load_id,
                     "reason": str(exc)},
                )
                notes.append(f"Rule “{rule.name}” could not run after the load: {exc}.")
        return notes


def held_rows_for(
    verdict: PreCommitVerdict,
    rows: Sequence[dict[str, str]],
    *,
    row_numbers: Sequence[int] | None,
    investigation_id: str,
    recipe_id: str,
    recipe_version: int,
    load_id: str,
    source: str,
    handling: Handling,
    dataset_id: str | None,
    row_handling: Callable[[dict[str, str]], Handling] | None = None,
) -> list[HeldRow]:
    numbers = list(row_numbers) if row_numbers is not None else list(range(len(rows)))
    position = {n: i for i, n in enumerate(numbers)}
    now = datetime.now(UTC)
    return [
        HeldRow(
            id=new_id(),
            investigation_id=investigation_id,
            recipe_id=recipe_id,
            recipe_version=recipe_version,
            load_id=load_id,
            source=source,
            row_index=row,
            row={k: "" if v is None else str(v) for k, v in rows[position[row]].items()},
            rule_id=rule.id,
            reason=reason,
            handling=row_handling(rows[position[row]]) if row_handling is not None else handling,
            held_at=now,
            dataset_id=dataset_id,
        )
        for row, (rule, reason) in sorted(verdict.hold.items())
        if row in position
    ]
