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

from .audit import AuditWriter
from .rule_evaluation import RULE_AUDIT_ACTIONS, RuleGate
from .studio_publish import load_with_rules


def _named_nodes(entry: RuleAuditEntry) -> list[str]:
    raw = entry.detail.get("node_ids") or []
    return [str(n) for n in raw] if isinstance(raw, list) else []


async def readable_rule_audit(
    audit: AuditWriter,
    graph: GraphPort,
    investigation_id: str,
    reader: Principal,
    *,
    offset: int = 0,
    limit: int = 100,
) -> RuleAuditPage:
    visible: dict[str, bool] = {}

    async def sees(node_id: str) -> bool:
        if node_id not in visible:
            visible[node_id] = await graph.get_node(node_id, reader) is not None
        return visible[node_id]

    kept: list[RuleAuditEntry] = []
    for entry in await audit.list_for_case(investigation_id, RULE_AUDIT_ACTIONS):
        if all([await sees(n) for n in _named_nodes(entry)]):
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
    )
    if analytics is not None and events:
        await analytics.load_events(events)
    report.rule_notes.extend(await rules.post_commit(events, load_id=load_id))
    return report


__all__ = ["ReleaseRefused", "readable_rule_audit", "release_held_rows"]
