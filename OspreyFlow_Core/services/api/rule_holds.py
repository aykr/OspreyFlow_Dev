"""Reading a case's rule audit, and deciding on held rows (`06_DECISIONS.md` ADR-109 ruling 1).

**The audit read (rule 3).** An entry naming a node the reader cannot see is withheld whole — not
redacted, since an entry that says "rule X fired on [hidden]" tells the reader something fired on
something they may not know exists — and withheld before paging, so neither the page nor its total
counts it. Visibility is the adapter's own answer (`GraphPort.get_node` as the reader), never a
check made here.

**A release.** The held rows of one load are loaded together under a new load id, through the same
`load_with_rules` path as any run, provenance unchanged (each keeps its original row number). The
case's pre-commit rules judge them again, but a failure no longer holds them: the reviewer's
release is the human judgement fail-closed was waiting for (`RuleGate(fail_closed=False)`).
"""

from __future__ import annotations

from collections.abc import Sequence

from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from ports.media import MediaStore
from schemas.domain import HeldRow, OntologySchema, Principal, RuleAuditEntry, RuleAuditPage
from schemas.ingest import LoadReport, Recipe

from .alerts import AlertStore, evidence_node_ids, read_evidence_ids, settle_repoints
from .audit import AuditWriter
from .rule_evaluation import RULE_AUDIT_ACTIONS, RuleGate
from .studio_publish import LoadSink, load_with_rules, post_commit_notes


def _ids(entry: RuleAuditEntry, key: str) -> list[str]:
    raw = entry.detail.get(key) or []
    return [str(n) for n in raw] if isinstance(raw, list) else []


def _old_firing(entry: RuleAuditEntry) -> bool:
    """A `rule_fired` entry written before L2.8b names its alert and its nodes but not the links and
    transactions it cites, so whether the reader may see them cannot be known from it."""
    return entry.action == "rule_fired" and "alert_id" in entry.detail and (
        "edge_ids" not in entry.detail or "event_ids" not in entry.detail
    )


#: The entries about one alert: checked by what that alert cites now, not what it cited when the
#: entry was written, since a repoint (ADR-109 Amendment 10) moves an alert onto a link's successor.
_ABOUT_AN_ALERT = ("rule_fired", "alert_node_withheld")


async def readable_rule_audit(
    audit: AuditWriter,
    graph: GraphPort,
    investigation_id: str,
    reader: Principal,
    *,
    analytics: AnalyticsPort,
    alerts: AlertStore,
    offset: int = 0,
    limit: int = 100,
) -> RuleAuditPage:
    """The case's rule audit as `reader` may read it (ADR-109 ruling 1; ADR-146 decision 10). An
    entry about an alert (a firing, a withheld node) is checked by everything its alert cites now,
    its own node included; any other by the nodes, links and transactions it names. All are read in
    one batched read per kind as the reader (`read_evidence_ids`, the queue's check), transactions
    in the reader's case, and an entry naming any the reader cannot see is withheld whole, before
    paging, so the total never counts it; one about an alert the store no longer holds is withheld.
    A firing written before its links were recorded keeps its entry, its words withheld (fail
    closed, the orchestrator's call). An evaluation's count of findings is withheld from a reader
    from whom any of that rule's firings is withheld, and kept for one who may see them all."""
    await settle_repoints(alerts, graph)
    entries = await audit.list_for_case(investigation_id, RULE_AUDIT_ACTIONS)
    about = sorted({str(e.detail["alert_id"]) for e in entries
                    if e.action in _ABOUT_AN_ALERT and "alert_id" in e.detail})  # fmt: skip
    current = await alerts.cited_by_ids(about)

    def cites(entry: RuleAuditEntry) -> tuple[list[str], list[str], list[str]] | None:
        if entry.action in _ABOUT_AN_ALERT and "alert_id" in entry.detail:
            alert = current.get(str(entry.detail["alert_id"]))
            if alert is None:
                return None
            return evidence_node_ids(alert), list(alert.edge_ids), list(alert.event_ids)
        return _ids(entry, "node_ids"), _ids(entry, "edge_ids"), _ids(entry, "event_ids")

    named = [cites(e) for e in entries]
    readable = await read_evidence_ids(
        reader,
        graph,
        analytics,
        node_ids={n for c in named if c for n in c[0]},
        edge_ids={n for c in named if c for n in c[1]},
        event_ids_by_scope={investigation_id: {n for c in named if c for n in c[2]}},
    )
    shown = [c is not None and readable.covers(*c) for c in named]
    unseen_rules = {
        str(e.detail.get("rule_id"))
        for e, ok in zip(entries, shown, strict=True)
        if not ok and e.action in _ABOUT_AN_ALERT
    }
    kept: list[RuleAuditEntry] = []
    for entry, ok in zip(entries, shown, strict=True):
        if not ok:
            continue
        if _old_firing(entry) and "words" in entry.detail:
            entry = entry.model_copy(
                update={"detail": {k: v for k, v in entry.detail.items() if k != "words"}}
            )
        if entry.action == "rule_evaluated" and str(entry.detail.get("rule_id")) in unseen_rules:
            entry = entry.model_copy(update={
                "detail": {**{k: v for k, v in entry.detail.items() if k != "findings"},
                           "findings_withheld": True},
                "result_cardinality": 0,
            })  # fmt: skip
        kept.append(entry)
    return RuleAuditPage(entries=kept[offset : offset + limit], total=len(kept))


class ReleaseRefused(Exception):
    """A release that cannot be honoured as asked, in words."""


async def release_held_rows(
    held: Sequence[HeldRow],
    recipe: Recipe,
    reviewer: Principal,
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    analytics: AnalyticsPort | None,
    media: MediaStore | None,
    rules: RuleGate,
    load_id: str,
    sink: LoadSink | None = None,
) -> LoadReport:
    """Loads `held` — rows of one load, of this recipe at the version they were held under."""
    if not held:
        raise ReleaseRefused("no held rows were named")
    if len({(h.load_id, h.source) for h in held}) != 1:
        raise ReleaseRefused("held rows from different loads are released one load at a time")
    if any(h.recipe_id != recipe.id or h.recipe_version != recipe.version for h in held):
        raise ReleaseRefused(
            "the recipe has been published again since these rows were held; run it again over "
            "the source instead, so the rows are read by the recipe as it now stands"
        )
    ordered = sorted(held, key=lambda h: h.row_index)
    report, events, _ = await load_with_rules(
        recipe,
        [h.row for h in ordered],
        reviewer,
        graph=graph,
        ontology=ontology,
        load_id=load_id,
        investigation_scope=rules.investigation_id,
        source=ordered[0].source,
        media=media,
        rules=rules,
        row_numbers=[h.row_index for h in ordered],
        scheme=rules.scheme,
        sink=sink,
    )
    if analytics is not None and events:
        await analytics.load_events(events)
    report.rule_notes.extend(await post_commit_notes(rules, events, load_id=load_id, sink=sink))
    return report


__all__ = ["ReleaseRefused", "readable_rule_audit", "release_held_rows"]
