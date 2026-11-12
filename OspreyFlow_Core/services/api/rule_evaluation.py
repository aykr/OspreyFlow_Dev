"""Typology rules on the change-stream chassis (`06_DECISIONS.md` ADR-109 phase A).

A rule is one of `services/ingest/typologies.py`'s three typologies with its parameters (rule 8:
a closed vocabulary, no expression language), deployed by a case Author, evaluated as its
deployer's principal resolved fresh (ADR-036), at the trigger point it declares (ruling 1):

- **post-commit** — after a load commits, on its change-stream entry, best-effort, never failing
  the ingest (the ADR-036/037 discipline `evaluation.py` already follows for monitors);
- **pre-commit** — over the incoming rows inside the load, before the graph commit: a hit loads
  with its alert (the `Alert` node written in the same graph transaction as the rows), and a rule
  that errors or overruns its budget fails closed, holding the rows it could not judge.

**Where a flow comes from.** Same-pair `TRANSACTED` writes of one audience merge into one link
(`engine.py`'s `_write_edge`; a write of another audience is a link of its own, ADR-102 Amendment
3), so a single transaction is not a graph edge: it is an event in the analytics store
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
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

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
    AlertCitation,
    AlertMode,
    CircularFlowParams,
    EdgeWrite,
    Handling,
    HeldRow,
    Interval,
    NodeWrite,
    OntologySchema,
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
from .dataset_scope import (
    CompositeReadOnlyError,
    analyst_layer,
    analyst_writes_into,
    read_only_layer,
    reads_a_composite,
)
from .held_rows import HeldRowStore
from .hotlists import HotlistStore
from .kyc_expiries import KycExpiryStore
from .pattern_store import PatternStore
from .screening import ScreeningListStore
from .strength_influencers import InfluencerStore

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
    # ADR-133 stage (d): maker–checker's changes, and the pipeline checks rules are attached as.
    "rule_change_proposed",
    "rule_change_approved",
    "rule_change_rejected",
    "rule_changed",
    "load_checks_set",
    # L2.10's carry: the daily sweep's failure for a rule, said where a person sees it (*Changes*).
    "rule_evaluation_failed",
    # ADR-146 decision 3 (L2.11): "every change is audited and listed in *Changes*" — a draft
    # saved, tested (never its count, rule 7), made live, or asked to go live.
    "rule_draft_saved",
    "rule_tested",
    "rule_made_live",
    "rule_make_live_proposed",
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
    #: ADR-146 Amendment 7: what it cites that a reader is cleared for one by one (a screening
    #: match on each list). Each citation's ids are among `node_ids` and `edge_ids` too.
    citations: tuple[AlertCitation, ...] = ()
    #: Of `refs`, those naming a citation's source (a screening match's list entry, `<list>:<id>`):
    #: in the finding's signature, so a match on a new entry alerts again, but never on the `Alert`
    #: node, which a reader cleared for one list reads (ADR-146 Amendment 7; the lane review's
    #: item 1: the node's sources named every list's entry, a hidden one's too).
    cited_refs: tuple[str, ...] = ()

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


async def _readable_accounts(
    ids: Sequence[str],
    written: Sequence[NodeWrite | EdgeWrite],
    graph: GraphPort,
    scheme: HandlingScheme,
    deployer: Principal,
) -> set[str]:
    """The accounts the deployer may read: from the load's own writes (a pre-commit rule's accounts
    are still in the open transaction), judged by marking and dataset reach as the adapter judges
    them; the rest asked of the store as the deployer, in one batched read (rule 3 in the adapter).
    An account they may not read is absent."""
    reach = deployer.datasets
    found = {
        w.id
        for w in written
        if isinstance(w, NodeWrite)
        and w.id in set(ids)
        and handling_readable(scheme, deployer, w.handling)
        and (reach is None or bool(set(w.datasets) & set(reach)))
    }
    missing = [i for i in ids if i not in found]
    if missing:
        found |= {n.id for n in await graph.get_nodes(missing, deployer)}
    return found


async def judge(
    rule: TypologyRule,
    deployer: Principal,
    incoming: Sequence[EventRecord],
    *,
    analytics: AnalyticsPort,
    scheme: HandlingScheme,
    investigation_scope: str,
    graph: GraphPort | None = None,
    written: Sequence[NodeWrite | EdgeWrite] = (),
) -> list[Finding]:
    """The rule over this load's events and the flows around them. Only events the deployer may
    read are judged or read (rule 3); only findings citing one of this load's events count.

    An event carries its marking but no dataset (ADR-099 decision 7: it belongs to its case), so a
    rule deployed within one of the case's datasets would otherwise judge every money movement of
    the case. With `graph` (the rule gate always gives it), a movement is judged or read only when
    the deployer may read both its accounts, as the AML templates read theirs (found building
    ADR-108 Amendment 5: a rule in another dataset raised an alert on accounts its author could
    not see)."""
    judged = [
        e
        for e in incoming
        if e.edge_type == FLOW_EDGE_TYPE and handling_readable(scheme, deployer, e.handling)
    ]
    if graph is not None and judged:
        ends = sorted({e.source_id for e in judged} | {e.target_id for e in judged})
        readable = await _readable_accounts(ends, written, graph, scheme, deployer)
        judged = [e for e in judged if e.source_id in readable and e.target_id in readable]
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
    if graph is not None and context:
        ends = sorted({e.source_id for e in context} | {e.target_id for e in context})
        readable = await _readable_accounts(ends, written, graph, scheme, deployer)
        context = [e for e in context if e.source_id in readable and e.target_id in readable]
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


#: Why an alert was raised without its `Alert` node, one per path that withholds it (ADR-146
#: decision 10): its referents restricted for different units (no single safe marking); a referent
#: whose marking could not be read in the load; a cited link that could not be read.
NodeWithheld = Literal[
    "units", "unseen_referent", "unreadable_link", "originals_layer", "read_only_dataset"
]
WITHHELD_WORDS: dict[str, str] = {
    "units": "its referents' restricted markings belong to different units",
    "unseen_referent": "the marking of something it names could not be read, so no node was "
    "written rather than one marked by a guess",
    "unreadable_link": "a link it cites could not be read (taken back or replaced since it was "
    "found), so no node was written rather than one marked by a guess",
    "originals_layer": "it rests on the layer of the case this one was made from, which it reads "
    "and writes nothing into, so no node was written rather than one that names its subject "
    "elsewhere",
    "read_only_dataset": "the dataset it would be written into is read-only here, so no node was "
    "written; the alert is in the queue without it",
}


class PartlyRaised(Exception):  # noqa: N818 - a run that failed part-way, not a kind of error
    """A run outside a load (a scheduled slot, a re-screening) that failed after raising some
    alerts: what it raised is kept and counted, and the failure is said with it (L2.10's carry: a
    failed slot counted none, and a failed re-screening dropped the rule's raised count)."""

    def __init__(self, raised: int, cause: BaseException, *, customers: int = 0) -> None:
        super().__init__(str(cause))
        self.raised = raised
        self.customers = customers
        self.cause = cause


class UnseenAlertReferent(RuntimeError):
    """A referent node whose marking cannot be read (`_referent_handlings`): no node is written
    rather than one marked by a guess. A `RuntimeError`, as it always was, so every caller that
    caught one still does; `raise_committed` catches this alone (the lane-reviewer's L2.10 note)."""


class UnreadableAlertLink(RuntimeError):
    """A link an alert cites whose marking cannot be read (reverted or superseded since the
    finding was judged): its node is withheld rather than marked by a guess, wherever the alert is
    raised (ADR-146 decision 10)."""


async def _referent_handlings(
    graph: GraphPort,
    scheme: HandlingScheme,
    finding: Finding,
    unseen: Handling | None,
    known: Mapping[str, Handling],
) -> list[Handling]:
    """The markings an alert must not be lower than: every cited event's, everything it writes
    alongside, every referenced node's and every cited link's as stored (the links since ADR-146
    decision 10: a link marked above its ends left the node, and the words it carries, readable by
    someone who may not see the link). A node or link not yet committed (written in this very
    load's transaction) cannot be read back: its marking as written (`known`) stands in, else
    `unseen` — the highest marking the load's recipe could give it."""
    handlings = [e.handling for e in finding.events]
    pending = {w.id: w.handling for w in finding.pending}
    handlings.extend(pending.values())
    reader = service_principal(scheme)
    cited = sorted({e for e in finding.edge_ids if e not in pending and e not in known})
    handlings.extend(known[e] for e in finding.edge_ids if e not in pending and e in known)
    stored = {e.id: e.handling for e in await graph.get_edges(cited, reader)} if cited else {}
    for edge_id in cited:
        if edge_id in stored:
            handlings.append(stored[edge_id])
        elif unseen is not None:
            handlings.append(unseen)
        else:
            raise UnreadableAlertLink(f"alert link {edge_id} could not be read for its marking")
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
            raise UnseenAlertReferent(f"alert referent {node_id} could not be read for its marking")
    return handlings


class _AlertInAReadOnlyLayer(Exception):
    """An alert resting on what an unconverted case reads of its original's layer: its node would
    carry the layer's subjects' names, and such a case writes into no layer (ADR-144 Amendment 1
    decision 2), so the node is withheld and the queue row still raised."""


async def _alert_datasets(graph: GraphPort, scheme: HandlingScheme, finding: Finding) -> list[str]:
    """What an alert's own node and `ALERTED_ON` links name, and what it writes alongside.

    - In a case reading a composite (read-only for now; ADR-099 Amendment 15 item 2): the case's
      analyst layer, made here if it has none. An `ALERTED_ON` from the layer's node to a member's
      node is the layer's link, and changes no member.
    - In any other case, an alert any of whose referents or cited links lives in the case's layer
      goes into that layer too, its node and `ALERTED_ON` included (rule 3, the orchestrator's
      ruling of 7 November 2026): the node's words begin with a subject's name, and in the source
      they would put a name drawn or marked in this case, and one more `Alert` in the counts, in
      front of every other case reading that source. In a case not yet converted, resting on its
      original's layer, it is withheld (`_AlertInAReadOnlyLayer`).
    - Otherwise nothing is named, and the stamping graph places them in the case's dataset."""
    if await reads_a_composite():
        return await analyst_writes_into()
    if read_only_layer() is not None:
        # A case made from another and not yet converted writes nothing (L3.2 item 3, the
        # review's round 2): its alert is withheld, its queue row raised, as for its original's
        # layer before.
        raise _AlertInAReadOnlyLayer
    layers = {layer for layer in (analyst_layer(), read_only_layer()) if layer is not None}
    if not layers:
        return []
    reader = service_principal(scheme)
    pending = {w.id for w in finding.pending}
    node_ids = [n for n in finding.node_ids if n not in pending]
    nodes = await graph.get_nodes(node_ids, reader) if node_ids else []
    edges = await graph.get_edges(list(finding.edge_ids), reader) if finding.edge_ids else []
    named = [*(d for n in nodes for d in n.datasets), *(d for e in edges for d in e.datasets)]
    touched = set(named) & layers
    if not touched:
        return []
    if read_only_layer() in touched:
        raise _AlertInAReadOnlyLayer
    return await analyst_writes_into()


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
) -> tuple[str | None, Finding]:
    """The `Alert` node and its `ALERTED_ON` links, in `tx` — at the highest marking of what it
    references, `inferred`, attributed to the rule (ruling 2; rules 3 and 5) — after anything the
    finding writes alongside (`pending`). `None` when no single marking is safe
    (`alert_handling`): the node is withheld, the queue row still raised. Returned with the finding
    as stored: a pending write the store merged into one it already held (a second screening hit
    on the same match) is cited by the stored id, never the write's own, which no link holds and
    which the queue's check would read as hidden from every reader (L2.8b)."""
    record = writes if writes is not None else RuleWrites()
    from .sentence_rules import writes_no_alert_node

    if writes_no_alert_node(finding.rule):
        # An alert for its author alone, or routed to a named team, puts nothing in the case's
        # graph: its node would carry its words to members the queue does not show it to.
        return None, finding
    into = await _alert_datasets(graph, scheme, finding)  # `_AlertInAReadOnlyLayer`: no node
    if finding.pending:
        # What the finding writes alongside (a screening hit's listed party, as the list asserts
        # it, and its inferred `SAME_AS`) is new and the rule's own: in a composite case it goes
        # into the layer with the alert. A link of the layer's is of another audience than a
        # member's, so it never merges into one; a write naming a dataset of its own keeps it, and
        # the stamping graph judges it.
        pending = [w if w.datasets or not into else w.model_copy(update={"datasets": into})
                   for w in finding.pending]  # fmt: skip
        pending_nodes = [w for w in pending if isinstance(w, NodeWrite)]
        stored_nodes = list(await graph.upsert_nodes(pending_nodes, tx))
        record.node_ids.extend(stored_nodes)
        renamed = {w.id: i for w, i in zip(pending_nodes, stored_nodes, strict=True) if w.id != i}
        pending_edges = [
            w.model_copy(update={"source": renamed.get(w.source, w.source),
                                 "target": renamed.get(w.target, w.target)})  # fmt: skip
            for w in pending
            if isinstance(w, EdgeWrite)
        ]
        stored_edges = list(await graph.upsert_edges(pending_edges, tx))
        record.edges(pending_edges, stored_edges)
        renamed.update(
            {w.id: i for w, i in zip(pending_edges, stored_edges, strict=True) if w.id != i}
        )
        if renamed:
            finding = replace(
                finding,
                subject=renamed.get(finding.subject, finding.subject),
                node_ids=[renamed.get(i, i) for i in finding.node_ids],
                edge_ids=[renamed.get(i, i) for i in finding.edge_ids],
                # Only the writes the store merged are gone; one written new keeps its marking as
                # written for the node's and its citation's markings (the lane review's item 5: an
                # owner's match on one list merged, on another new, lost the new one's).
                pending=tuple(w for w in finding.pending if w.id not in renamed),
                citations=tuple(
                    c.model_copy(update={"node_ids": [renamed.get(i, i) for i in c.node_ids],
                                         "edge_ids": [renamed.get(i, i) for i in c.edge_ids]})
                    for c in finding.citations
                ),  # fmt: skip
            )
    # ADR-146 Amendment 7: the node is marked by what the alert rests on outside its citations, so
    # a reader cleared for one list's match and not another's still reads it; the `ALERTED_ON` to
    # a citation's party is marked by that citation too (`_citation_markings`).
    marking = alert_handling(
        scheme, await _referent_handlings(graph, scheme, core_of(finding), unseen, known or {})
    )
    if marking is None:
        return None, finding
    by_target = await _citation_markings(graph, scheme, finding, marking, unseen, known or {})
    now = datetime.now(UTC)
    provenance = Provenance(
        state=ProvenanceState.INFERRED,
        sources=[
            SourceRef(document_id=f"rule:{finding.rule.id}", locator=ref, excerpt_hash="")
            for ref in alert_node_refs(finding)
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
        datasets=into,
    )
    (node_id,) = await graph.upsert_nodes([node], tx)
    record.node_ids.append(node_id)
    # A citation's party no single marking can join to the node's gets no `ALERTED_ON`.
    targets = [(t, by_target.get(t, marking)) for t in finding.node_ids]
    alerted = [
        EdgeWrite(
            id=new_edge_id(),
            type="ALERTED_ON",
            source=node_id,
            target=target,
            basis="probabilistic",
            provenance=provenance,
            handling=link_marking,
            created_by=finding.deployer.id,
            created_at=now,
            load_id=load_id,
            datasets=into,
        )
        for target, link_marking in targets
        if link_marking is not None
    ]
    record.edges(alerted, await graph.upsert_edges(alerted, tx))
    return node_id, finding


def alert_node_refs(finding: Finding) -> list[str]:
    """What the `Alert` node's sources name: the finding's refs outside its citations' (ADR-146
    Amendment 7)."""
    return [r for r in finding.refs if r not in set(finding.cited_refs)]


def core_of(finding: Finding) -> Finding:
    """The finding without its citations (ADR-146 Amendment 7): what every reader of the alert
    must be able to read, and what its own node is marked by."""
    if not finding.citations:
        return finding
    nodes = {i for c in finding.citations for i in c.node_ids}
    edges = {i for c in finding.citations for i in c.edge_ids}
    return replace(
        finding,
        node_ids=[i for i in finding.node_ids if i not in nodes],
        edge_ids=[i for i in finding.edge_ids if i not in edges],
        pending=tuple(w for w in finding.pending if w.id not in nodes | edges),
        citations=(),
    )


async def _citation_markings(
    graph: GraphPort,
    scheme: HandlingScheme,
    finding: Finding,
    marking: Handling,
    unseen: Handling | None,
    known: Mapping[str, Handling],
) -> dict[str, Handling | None]:
    """Each cited party's `ALERTED_ON` marking: the node's, raised to everything its citation rests
    on; `None` where no single marking is safe (`alert_handling`), and no link is written."""
    out: dict[str, Handling | None] = {}
    for citation in finding.citations:
        ids = {*citation.node_ids, *citation.edge_ids}
        part = replace(
            finding,
            node_ids=list(citation.node_ids),
            edge_ids=list(citation.edge_ids),
            events=(),
            pending=tuple(w for w in finding.pending if w.id in ids),
            citations=(),
        )
        handlings = await _referent_handlings(graph, scheme, part, unseen, known)
        joined = alert_handling(scheme, [marking, *handlings])
        for node_id in citation.node_ids:
            out[node_id] = joined
    return out


def alert_row(finding: Finding, alert_node_id: str | None, investigation_id: str) -> Alert:
    from .sentence_rules import sentence_alert_fields

    fields = sentence_alert_fields(finding)
    return Alert(
        **fields,
        id=new_id(),
        owner_id=finding.deployer.id,
        mode=AlertMode.FULL,
        referent_node_ids=finding.node_ids,
        investigation_id=investigation_id,
        created_at=datetime.now(UTC),
        words=finding.words,
        edge_ids=finding.edge_ids,
        event_ids=[e.event_id for e in finding.events],
        window=finding.window,
        trigger=finding.rule.trigger,
        alert_node_id=alert_node_id,
        citations=list(finding.citations),
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
    #: Why each finding raised with no node was withheld, by its place in `findings`.
    withheld: dict[int, NodeWithheld] = field(default_factory=dict)
    #: Rows a failing rule could not judge, by original row number, with the failing rule and why.
    hold: dict[int, tuple[TypologyRule, str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    #: What the rules wrote into the load's transaction, for the load's record.
    writes: RuleWrites = field(default_factory=RuleWrites)


def held_because(rule: TypologyRule) -> str:
    """Why a row a rule matched is held, in words a reviewer of the row may read: the rule and its
    typology, never the finding's own words, which name what its deployer read (ADR-146 decision
    10; L2.8b's Q2)."""
    return f"it matched “{rule.name}” ({rule.params.typology.replace('_', ' ')})"


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
    #: ADR-133 stage (b): a sentence's "on one of my hotlists", read as its author, and the
    #: ontology a sentence's drawn pattern is read back against.
    hotlists: HotlistStore | None = None
    ontology: OntologySchema | None = None
    #: ADR-146 decision 3 (L2.11's list picker): a sentence's named Studio list, read within the
    #: rule's own dataset (`rule_editor.rule_list_reader`). None where no run reads one.
    rule_lists: Callable[[TypologyRule, str, str], Awaitable[list[Any]]] | None = None
    #: ADR-146 decision 3: what a rule on a declared dataset reads, its composite's members with it
    #: (`rule_editor.rule_reach_of`). None: the rule's dataset id alone, as before L2.11.
    rule_reach: Callable[[TypologyRule], Awaitable[list[str] | None]] | None = None
    #: ADR-133 decision 6, stage (d): what a hit of a rule does at this pipeline, as its "Checks on
    #: load" step chose ("alert" or "hold"), by rule id. A rule not named keeps its author's choice.
    on_hit: dict[str, str] = field(default_factory=dict)
    #: ADR-139: where a sentence's strength condition reads the case's influencers (case, then
    #: installation, then the weights file's); None, the file's alone.
    influencers: InfluencerStore | None = None

    def holds(self, rule: TypologyRule) -> bool:
        """Whether a hit of `rule` holds its rows here: before commit only; as the pipeline chose,
        else as the author wrote. A pipeline may make a whole-deployment rule hold, never loosen
        one its author wrote to hold."""
        from .sentence_rules import holds_on_hit, is_deployment_wide

        if rule.trigger != "pre_commit":
            return False
        chosen = self.on_hit.get(rule.id)
        if chosen is None or (is_deployment_wide(rule) and holds_on_hit(rule)):
            return holds_on_hit(rule)
        return chosen == "hold"

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
        from .rule_schedule import holds_a_writing_right
        from .sentence_rules import is_deployment_wide

        deployer = await self.principal_for_owner(rule.owner_id)
        if deployer is not None and not is_deployment_wide(rule) and not holds_a_writing_right(
            deployer
        ):
            # ADR-146 Amendment 6 decision 13: a rule runs as its author only while they hold a
            # right to have written it, at a load as on a schedule (a whole-deployment rule is the
            # administrator's, approved by a second person: its own rights, ADR-133 decision 7).
            return None
        if deployer is not None and rule.dataset_id is not None:
            reach: list[str] | None = [rule.dataset_id]
            if self.rule_reach is not None:
                reach = await self.rule_reach(rule)
            # A case that no longer reads the rule's dataset reads nothing through it (rule 3).
            deployer = deployer.model_copy(update={"datasets": reach or []})
        if deployer is not None and is_deployment_wide(rule):
            # ADR-133 decision 1: a deployment-wide sentence judges each case's loads within that
            # case's datasets (the loader's), as its administrator author may read them.
            deployer = deployer.model_copy(update={"datasets": self.loader.datasets})
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
        (`kyc_rules.py`, imported here, not at the top: it builds on this module). ADR-133 stage
        (c)'s AML templates over the load's movements and the accounts' own past
        (`aml_rules.py`)."""
        from .aml_rules import AML_TYPOLOGIES, judge_aml

        if rule.params.typology in AML_TYPOLOGIES:
            return await judge_aml(
                rule,
                deployer,
                events,
                written,
                graph=self.graph,
                analytics=self.analytics,
                scheme=self.scheme,
                investigation_scope=self.investigation_id,
            )
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
                graph=self.graph,
                written=written,
            )
        if rule.params.typology == "pattern":
            from .pattern_rules import judge_pattern

            return await judge_pattern(
                rule, deployer, written, graph=self.graph, patterns=self.patterns
            )
        if rule.params.typology == "sentence":
            from .sentence_rules import judge_sentence_rule

            return await judge_sentence_rule(rule, deployer, written, events, self)
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
        if rule.params.typology == "sentence":
            from .sentence_rules import sentence_rows

            return sentence_rows(rule, events, written)
        from .aml_rules import AML_TYPOLOGIES

        if is_flow_rule(rule) or rule.params.typology in AML_TYPOLOGIES:
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
        # What this load wrote, nodes and links, cannot be read back before the commit: each
        # stands in at its marking as written, never at the recipe's highest (`unseen`).
        known = {w.id: w.handling for w in written}
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
            from .sentence_rules import rows_of_finding

            if self.holds(rule):
                # ADR-133 decision 1: a hit holds its rows for a reviewer, the finding its reason.
                for finding in fresh:
                    rows = rows_of_finding(finding, events, written)
                    for row in rows:
                        verdict.hold.setdefault(row, (rule, held_because(rule)))
                    verdict.notes.append(
                        f"Rule “{rule.name}” matched {len(rows)} row(s); they are held for "
                        "review, not loaded."
                    )
                continue
            for finding in fresh:
                node_id, why, stored = await self._alert_node_in_load(
                    finding, tx, unseen=unseen, load_id=load_id, known=known, writes=verdict.writes
                )
                if why is not None:
                    verdict.withheld[len(verdict.findings)] = why
                verdict.findings.append((stored, node_id))
            if fresh:
                verdict.notes.append(f"Rule “{rule.name}” raised {len(fresh)} alert(s).")
        return verdict

    async def _alert_node_in_load(
        self,
        finding: Finding,
        tx: TxId,
        *,
        unseen: Handling | None,
        load_id: str | None,
        known: Mapping[str, Handling],
        writes: RuleWrites,
    ) -> tuple[str | None, NodeWithheld | None, Finding]:
        """The finding's `Alert` node in the load's transaction, or why there is none, and the
        finding as stored (`write_alert_node`)."""
        try:
            node_id, stored = await write_alert_node(
                self.graph, self.scheme, finding, tx, unseen=unseen, load_id=load_id, known=known,
                writes=writes,
            )  # fmt: skip
        except UnreadableAlertLink:
            return None, "unreadable_link", finding
        except _AlertInAReadOnlyLayer:
            return None, "originals_layer", finding
        except RuntimeError:
            # A referent's marking cannot be known: no node rather than a guessed one.
            return None, "unseen_referent", finding
        return node_id, ("units" if node_id is None else None), stored

    async def after_commit(self, verdict: PreCommitVerdict) -> list[Alert]:
        """The queue rows for what `pre_commit` wrote into the committed graph."""
        return [
            await self._raise_row(f, node_id, withheld=verdict.withheld.get(i))
            for i, (f, node_id) in enumerate(verdict.findings)
        ]

    async def _rests_on(self, finding: Finding, node_id: str | None) -> list[Handling] | None:
        """Every handling the alert rests on — its entities, its own node, the links and the
        transactions it cites — read as its deployer, who raised it (ADR-134 decision 3). `None`
        when any of them cannot be read so: not known, and the alert trend counts it for no one."""
        node_ids = sorted({*finding.node_ids, *([node_id] if node_id else [])})
        edge_ids = sorted(set(finding.edge_ids))
        nodes = await self.graph.get_nodes(node_ids, finding.deployer) if node_ids else []
        edges = await self.graph.get_edges(edge_ids, finding.deployer) if edge_ids else []
        if {n.id for n in nodes} != set(node_ids) or {e.id for e in edges} != set(edge_ids):
            return None
        return [
            *(n.handling for n in nodes),
            *(e.handling for e in edges),
            *(e.handling for e in finding.events),
        ]

    async def _raise_row(
        self, finding: Finding, node_id: str | None, *, withheld: NodeWithheld | None = None
    ) -> Alert:
        alert = alert_row(finding, node_id, self.investigation_id)
        await self.alert_store.save(alert, handlings=await self._rests_on(finding, node_id))
        await self._remember(finding)
        detail: dict[str, object] = {
            "rule_id": finding.rule.id,
            "alert_id": alert.id,
            "trigger": finding.rule.trigger,
            "words": finding.words,
            "node_ids": finding.node_ids,
            # Every link and transaction the finding cites, so the audit read withholds the entry,
            # and its words, from a reader who may not see them (ADR-146 decision 10; L2.8b).
            "edge_ids": list(alert.edge_ids),
            "event_ids": list(alert.event_ids),
        }
        await self._audit("rule_fired", detail, 1)
        from .sentence_rules import writes_no_alert_node

        if node_id is None and not writes_no_alert_node(finding.rule):
            await self._audit(
                "alert_node_withheld",
                {"rule_id": finding.rule.id, "alert_id": alert.id, "node_ids": finding.node_ids,
                 "reason": WITHHELD_WORDS[withheld] if withheld else "no reason was recorded"},
            )
        return alert

    async def raise_committed(
        self, finding: Finding, *, load_id: str | None = None, writes: RuleWrites | None = None
    ) -> Alert:
        """A finding raised outside any load's transaction (after commit, or by the daily sweep):
        its node in a transaction of its own, then its queue row. `writes` collects what it wrote,
        for the record of the load it follows."""
        from .sentence_rules import writes_no_alert_node

        if writes_no_alert_node(finding.rule):
            return await self._raise_row(finding, None)  # nothing goes into the case's graph
        tx = await self.graph.begin_transaction()
        try:
            node_id, stored = await write_alert_node(
                self.graph, self.scheme, finding, tx, load_id=load_id, writes=writes
            )
        except UnreadableAlertLink:
            # As the load path does for an unseen referent: no node rather than a guessed one, the
            # row still raised (the queue's full check withholds it from anyone who may not see its
            # evidence), so one reverted link never stops a sweep. A node still stops the raise.
            await self.graph.rollback_transaction(tx)
            return await self._raise_row(finding, None, withheld="unreadable_link")
        except _AlertInAReadOnlyLayer:
            await self.graph.rollback_transaction(tx)
            return await self._raise_row(finding, None, withheld="originals_layer")
        except (CompositeReadOnlyError, UnseenAlertReferent) as error:
            # L2.10's carry: outside a load, as in one, a node that cannot be written (a read-only
            # dataset) or marked (a referent's marking not known, `_referent_handlings`) leaves the
            # row raised without it, said in the audit, so one finding never stops a sweep. Not
            # for a finding that writes alongside (a screening hit's listed party and `SAME_AS`):
            # its row would cite what was never written, so its refusal stands.
            await self.graph.rollback_transaction(tx)
            if finding.pending:
                raise
            why: NodeWithheld = (
                "read_only_dataset"
                if isinstance(error, CompositeReadOnlyError)
                else "unseen_referent"
            )
            return await self._raise_row(finding, None, withheld=why)
        except Exception:
            await self.graph.rollback_transaction(tx)
            raise
        await self.graph.commit_transaction(tx)
        return await self._raise_row(
            stored, node_id, withheld="units" if node_id is None else None
        )

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
