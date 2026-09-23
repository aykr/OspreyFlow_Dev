"""The change-stream evaluator — `06_DECISIONS.md` ADR-037/038, Phase 7 Stage 6b. The bounds
Stage 6a deferred (concurrency limit, per-evaluation cost cap, overrun behaviour) land here,
because this is the first scheduled/event-driven consumer of the change stream Stage 6a built with
none — writing a lock with nothing yet acquiring it repeatedly would have been bounding a
mechanism that could not yet run unbounded (6a's own disclosed reasoning).

**Two evaluators, not one, because hotlists and monitors have genuinely different leak shapes —
`06_DECISIONS.md` ADR-036 and ADR-038 each already say so, not invented here.**

`evaluate_hotlists_for_entry` — a hotlist holds a bare identifier with no graph context at all
(ADR-038: "an analyst can hotlist a bare phone number... before it resolves to anything they can
see"), so *finding* a match needs a read unscoped to any one owner's own access — the same
`service_principal` `services/resolve/trigger.py` already uses for corpus-wide resolution, reused
here rather than inventing a second unrestricted identity — and *disclosing* it is a separate
decision, `06_DECISIONS.md` ADR-038's own `strict`/`notify` switch, applied via `alerts.py`'s
`record_match` using the hotlist owner's own principal.

`evaluate_monitors_for_entry` — a saved-pattern monitor evaluates as the saving analyst's own
principal, never a service principal (`06_DECISIONS.md` ADR-036, quoted directly: "no new
privileged code path, nothing the existing silent-truncation and access-control discipline does
not already require of every
other read"). `GraphPort.match` is already principal-filtered, so a monitor's own query can never
return a match its owner cannot see — there is no out-of-access case for `record_match`'s
`strict`/`notify` branch to ever take for a monitor, and this module does not pretend one exists;
every monitor alert reaches `record_match` already proven visible by the match query itself.

**Deduplication, disclosed as coarse rather than assumed precise.** `GraphPort.match` returns one
`Subgraph` per pattern, not a list of discrete match instances — this build's own compiler
(`06_DECISIONS.md` ADR-030) has no concept of enumerating separate matches, only the union of
everything a pattern currently matches. A monitor's own "did this get a new match" question is
therefore answered at the whole-subgraph level: a hash of the current match's own sorted node/edge
ids, compared against the last hash this monitor alerted on (`Valkey`, one key per monitor). The
match set growing, shrinking to a different-but-nonempty set, or changing composition all count as
"new" and re-alert; an unchanged match set does not. This is coarser than per-instance dedup and
disclosed as such, not silently assumed to be the finer-grained thing a reader might expect from
"a new match."

**`status`, written on every evaluation attempt — Stage 6c, `06_DECISIONS.md` ADR-036's own
amendment.** A skipped evaluation (`principal_for_owner` returns `None`, or — for a monitor — its
own pattern no longer resolves) is not left as a silent in-memory `continue`: the hotlist/monitor
row's own `status` is written `"stopped"` before skipping, `"active"` on every attempt that
genuinely resolves a principal and runs, so the owner (or another reader of the list/inbox) can see
it rather than believe a watch is live when 6c's own synchronous wiring (`app.py`'s
`run_studio_recipe`) never had a principal to evaluate it as. Not sticky — the next successful
attempt flips it back, so this reflects the most recent reach, not a one-way trip."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from services.resolve.trigger import service_principal
from valkey.asyncio import Valkey
from valkey.asyncio.lock import Lock
from valkey.exceptions import LockError

from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.domain import Alert, Hotlist, Monitor, Principal, Subgraph

from .alerts import AlertStore, DisclosurePolicy, record_match
from .audit import AuditWriter
from .change_stream import ChangeStreamEntry
from .hotlists import HotlistStore
from .monitors import MonitorStore
from .pattern_store import PatternNotFoundError, PatternStore

#: Bounds `services/resolve/trigger.py`'s own `LOCK_TTL_SECONDS`/`PAGE_SIZE` precedent —
#: conservative and disclosed as a guess, not a measurement, for the identical reason that
#: module's own docstring gives: no timing of a hotlist/monitor evaluation at corpus scale
#: exists anywhere in this repository.
LOCK_TTL_SECONDS = 5 * 60

#: The per-evaluation cost cap (ADR-037): how many of a single change-stream entry's own touched
#: node ids a hotlist evaluation will check. Bounds `GraphPort.get_node` calls per entry per
#: hotlist, not the number of hotlists themselves — a corpus-wide fan-out over many hotlists is
#: bounded by the overlap lock below (one evaluation in flight per hotlist at a time) and by the
#: caller's own population size, not by this constant.
MAX_TOUCHED_NODES_PER_EVALUATION = 200

_HOTLIST_LOCK_PREFIX = "hotlist:running:"
_MONITOR_LOCK_PREFIX = "monitor:running:"
_MONITOR_LAST_SIGNATURE_PREFIX = "monitor:last_signature:"


@dataclass(frozen=True)
class EvaluationResult:
    skipped: bool
    reason: str | None = None
    alerts: list[Alert] | None = None

    def alert_list(self) -> list[Alert]:
        return self.alerts or []


async def _with_overlap_guard(
    lock_key: str, valkey: Valkey, fn: Callable[[], Awaitable[list[Alert]]]
) -> EvaluationResult:
    lock: Lock = valkey.lock(lock_key, timeout=LOCK_TTL_SECONDS, blocking=False)
    acquired = await lock.acquire()
    if not acquired:
        # Overrun behaviour (ADR-037): skip the redundant trigger rather than queue or error it —
        # the identical choice `services/resolve/trigger.py`'s own overlap guard already makes,
        # relying on the lock to make the skip safe.
        return EvaluationResult(skipped=True, reason="an evaluation is already in progress")
    try:
        alerts = await fn()
        return EvaluationResult(skipped=False, alerts=alerts)
    finally:
        try:
            await lock.release()
        except LockError:
            pass


async def evaluate_hotlists_for_entry(
    entry: ChangeStreamEntry,
    *,
    graph: GraphPort,
    scheme: HandlingScheme,
    hotlist_store: HotlistStore,
    alert_store: AlertStore,
    audit: AuditWriter,
    valkey: Valkey,
    principal_for_owner: Callable[[str], Awaitable[Principal | None]],
    policy: DisclosurePolicy,
) -> list[Alert]:
    """One overlap-guarded evaluation per active hotlist. `principal_for_owner` is supplied by the
    caller, never resolved here — `06_DECISIONS.md` ADR-036's own "resolved fresh, never cached"
    requirement means a live, current `Principal` for the owner. **Async since `06_DECISIONS.md`
    ADR-043 (Phase 8 Stage 1):** a real caller's own implementation is a live OAuth2 Token Exchange
    call, not a synchronous lookup — `app.py`'s own `_evaluate_watches_best_effort` is the real
    implementation; this module still makes no assumption about what the callable does beyond
    awaiting it once per owner. Returning `None` is the disclosed stand-in for ADR-036's own "the
    monitor stops" when a principal cannot be resolved (unset, refused, or unreachable — ADR-044's
    own still-undecided question about distinguishing those is not this module's to answer): this
    evaluation is skipped for that owner, not run against a stale or invented one.

    `matcher` below is deliberately unscoped — `06_DECISIONS.md` ADR-038's own addendum records
    why this is a justified exemption rather than an oversight `authorized-query-check` missed
    (it cannot see this shape at all: a module function, not a `*_authorized` store method), what
    the only barrier to disclosure is (`record_match`'s own `policy` branch, called below with
    `recipient` — the owner's principal — never with `matcher`), and names the test that pins it."""
    if not entry.node_ids:
        return []
    touched = entry.node_ids[:MAX_TOUCHED_NODES_PER_EVALUATION]
    matcher = service_principal(scheme)
    all_alerts: list[Alert] = []

    for hotlist in await hotlist_store.list_all_active():
        recipient = await principal_for_owner(hotlist.owner_id)
        if recipient is None:
            await hotlist_store.set_status(hotlist.id, "stopped")
            continue
        await hotlist_store.set_status(hotlist.id, "active")

        async def _run(hotlist: Hotlist = hotlist, recipient: Principal = recipient) -> list[Alert]:
            found: list[Alert] = []
            for node_id in touched:
                node = await graph.get_node(node_id, matcher)
                if node is None:
                    continue
                value = node.properties.get("value_normalised")
                if value != hotlist.identifier:
                    continue
                alert = await record_match(
                    graph=graph,
                    alert_store=alert_store,
                    audit=audit,
                    recipient=recipient,
                    rule_id=f"hotlist:{hotlist.id}",
                    matched_identifier=hotlist.identifier,
                    triggering_node_ids=[node_id],
                    policy=policy,
                    investigation_id=entry.investigation_id,
                )
                if alert is not None:
                    found.append(alert)
            return found

        result = await _with_overlap_guard(f"{_HOTLIST_LOCK_PREFIX}{hotlist.id}", valkey, _run)
        all_alerts.extend(result.alert_list())

    return all_alerts


async def evaluate_monitors_for_entry(
    entry: ChangeStreamEntry,
    *,
    graph: GraphPort,
    monitor_store: MonitorStore,
    pattern_store: PatternStore,
    alert_store: AlertStore,
    audit: AuditWriter,
    valkey: Valkey,
    principal_for_owner: Callable[[str], Awaitable[Principal | None]],
) -> list[Alert]:
    """One overlap-guarded evaluation per active monitor. Async since `06_DECISIONS.md` ADR-043
    (Phase 8 Stage 1) — see `evaluate_hotlists_for_entry`'s own docstring above for the full
    reasoning, identical here. `policy` is not a parameter here — a
    monitor's own match is always principal-filtered by construction (this module's own docstring
    has the full reasoning), so `record_match` always takes its "visible" branch and the
    `strict`/`notify` switch is never reached for a monitor alert, not merely defaulted to one
    side of it."""
    # The change stream entry gates *when* an evaluation runs and carries `investigation_id`
    # through to a fired alert; it does not otherwise shape *what* is checked — the pattern's own
    # query is re-run in full against the owner's current access each time, the same "re-verify
    # from the authoritative source" discipline `change_stream.py`'s own docstring already commits
    # this codebase to, rather than trying to infer from touched ids alone whether a pattern with
    # joins across them could newly match.
    all_alerts: list[Alert] = []

    for monitor in await monitor_store.list_all_active():
        recipient = await principal_for_owner(monitor.owner_id)
        if recipient is None:
            await monitor_store.set_status(monitor.id, "stopped")
            continue

        async def _run(monitor: Monitor = monitor, recipient: Principal = recipient) -> list[Alert]:
            try:
                saved = await pattern_store.get_authorized(monitor.pattern_id, recipient)
            except PatternNotFoundError:
                # The pattern was deleted, or its owner changed — `PatternStore` has no delete
                # today, so in practice this is "the owning principal this monitor's own row
                # names no longer owns the pattern it was created against," ADR-036's own
                # "the monitor stops" case, extended from principal validity to pattern validity.
                await monitor_store.set_status(monitor.id, "stopped")
                return []
            await monitor_store.set_status(monitor.id, "active")
            subgraph = await graph.match(saved.definition, recipient)
            if not subgraph.nodes and not subgraph.edges:
                return []
            signature = _match_signature(subgraph)
            sig_key = f"{_MONITOR_LAST_SIGNATURE_PREFIX}{monitor.id}"
            last = await valkey.get(sig_key)
            last_str = last.decode() if isinstance(last, bytes) else last
            if last_str == signature:
                return []
            await valkey.set(sig_key, signature)
            triggering_ids = [n.id for n in subgraph.nodes]
            alert = await record_match(
                graph=graph,
                alert_store=alert_store,
                audit=audit,
                recipient=recipient,
                rule_id=f"monitor:{monitor.id}",
                matched_identifier=saved.name,
                triggering_node_ids=triggering_ids,
                policy="strict",  # irrelevant here — see this function's own docstring
                investigation_id=entry.investigation_id,
            )
            return [alert] if alert is not None else []

        result = await _with_overlap_guard(f"{_MONITOR_LOCK_PREFIX}{monitor.id}", valkey, _run)
        all_alerts.extend(result.alert_list())

    return all_alerts


def _match_signature(subgraph: Subgraph) -> str:
    node_ids = sorted(n.id for n in subgraph.nodes)
    edge_ids = sorted(e.id for e in subgraph.edges)
    raw = "|".join(node_ids) + "::" + "|".join(edge_ids)
    return hashlib.sha256(raw.encode()).hexdigest()


__all__ = [
    "LOCK_TTL_SECONDS",
    "MAX_TOUCHED_NODES_PER_EVALUATION",
    "EvaluationResult",
    "evaluate_hotlists_for_entry",
    "evaluate_monitors_for_entry",
]
