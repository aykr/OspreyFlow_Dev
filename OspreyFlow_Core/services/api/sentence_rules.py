"""A sentence rule on the load path (`06_DECISIONS.md` ADR-133 decision 1, stage (b)), on ADR-109's
chassis (`rule_evaluation.RuleGate`).

**Read afresh as its author.** At each evaluation the rule's drawn pattern is read as the author
(`PatternStore.get_authorized`, ADR-036's discipline, as a `pattern` rule's), so an edit made in the
query builder is the rule as it now reads; one no longer theirs stops the rule, said and audited.
The author's hotlists are read as them too. `rule_sentences.judge_sentence` does the judging.

**What the sentence's last blanks decide here:**
- *severity* and *team* are written on the alert (`sentence_alert_fields`); "my team" labels it
  with the author's organisational unit;
- *just me* raises the alert for its author alone — no typology, so the queue gives it to its owner
  only (`alerts.queue_scope`), with no team, and no `Alert` node in the case's graph (a monitor's
  way);
- *hold* (before commit): a hit's rows are held for a reviewer, with the finding as the reason,
  instead of loading with an alert (ADR-109 ruling 1's quarantine, used for a hit).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from schemas.analytics import EventRecord
from schemas.domain import EdgeWrite, NodeWrite, Principal, TypologyRule
from schemas.sentences import SentenceRuleParams

from .dataset_scope import made_in
from .kyc_rules import customer_rows
from .pattern_store import PatternNotFoundError
from .rule_sentences import SentenceContext, judge_sentence, sentence_words

if TYPE_CHECKING:
    from .rule_evaluation import Finding, RuleGate


def sentence_of_rule(rule: TypologyRule) -> SentenceRuleParams | None:
    return rule.params if isinstance(rule.params, SentenceRuleParams) else None


def is_just_me(rule: TypologyRule) -> bool:
    params = sentence_of_rule(rule)
    return params is not None and params.sentence.scope == "just_me"


def is_deployment_wide(rule: TypologyRule) -> bool:
    params = sentence_of_rule(rule)
    return params is not None and params.sentence.scope == "deployment"


def holds_on_hit(rule: TypologyRule) -> bool:
    params = sentence_of_rule(rule)
    return params is not None and params.sentence.on_hit == "hold" and rule.trigger == "pre_commit"


def sentence_alert_fields(finding: Finding) -> dict[str, Any]:
    """The alert row's kind-deciding fields: a typology rule's, unless the sentence is just for its
    author — then a monitor-kind alert for the author alone (`monitor:sentence:<rule>`)."""
    rule = finding.rule
    params = sentence_of_rule(rule)
    if params is None:
        return {"rule_id": f"typology:{rule.id}", "typology": finding.typology,
                "dataset_id": rule.dataset_id}  # fmt: skip
    sentence = params.sentence
    # A deployment-wide rule's alert belongs to the dataset of the case whose load raised it.
    dataset = made_in(finding.deployer) if sentence.scope == "deployment" else rule.dataset_id
    team = finding.deployer.org_unit if sentence.team == "my_team" else None
    if sentence.scope == "just_me":
        return {"rule_id": f"monitor:sentence:{rule.id}", "typology": None,
                "severity": sentence.severity, "team": None, "dataset_id": dataset}  # fmt: skip
    return {"rule_id": f"typology:{rule.id}", "typology": "sentence",
            "severity": sentence.severity, "team": team, "dataset_id": dataset}  # fmt: skip


def sentence_rows(
    rule: TypologyRule, events: Sequence[EventRecord], written: Sequence[NodeWrite | EdgeWrite]
) -> list[int]:
    """The rows a sentence judges, and so would hold: those that wrote a node of its subject's
    type, and those carrying an event of its frequency's link type."""
    params = sentence_of_rule(rule)
    if params is None:
        return []
    sentence = params.sentence
    subjects = [w for w in written if isinstance(w, NodeWrite) and w.type == sentence.subject]
    rows = set(customer_rows(subjects))
    if sentence.frequency is not None:
        from .rule_evaluation import _source_rows

        for event in events:
            if event.edge_type == sentence.frequency.link_type:
                rows.update(_source_rows(event))
    return sorted(rows)


def rows_of_finding(
    finding: Finding, events: Sequence[EventRecord], written: Sequence[NodeWrite | EdgeWrite]
) -> list[int]:
    """The rows behind one hit: those that wrote its subject, and those carrying its events."""
    from .rule_evaluation import _source_rows

    subject = set(finding.node_ids)
    rows = set(customer_rows([w for w in written if isinstance(w, NodeWrite) and w.id in subject]))
    for event in events:
        if subject & {event.source_id, event.target_id}:
            rows.update(_source_rows(event))
    return sorted(rows)


async def judge_sentence_rule(
    rule: TypologyRule,
    deployer: Principal,
    written: Sequence[NodeWrite | EdgeWrite],
    events: Sequence[EventRecord],
    gate: RuleGate,
) -> list[Finding]:
    from .rule_evaluation import Finding

    params = sentence_of_rule(rule)
    assert params is not None
    if gate.patterns is None:
        raise RuntimeError("this run has no pattern store to read the rule's drawn pattern from")
    try:
        saved = await gate.patterns.get_authorized(params.pattern_id, deployer)
    except PatternNotFoundError:
        raise RuntimeError(
            "the rule's drawn pattern is no longer its author's to read; the rule cannot run"
        ) from None
    hotlisted: frozenset[str] | None = None
    relationship = params.sentence.relationship
    if relationship is not None and relationship.kind == "on_hotlist":
        if gate.hotlists is None:
            raise RuntimeError("this run has no hotlist store to read the author's hotlists from")
        hotlisted = frozenset(
            h.identifier
            for h in await gate.hotlists.list_authorized(deployer)
            if h.status == "active"
        )
    entries: dict[str, list[Any]] = {}
    if relationship is not None and relationship.kind == "on_screening_list":
        if gate.screening is None:
            raise RuntimeError("this run has no screening lists to screen against")
        entries[params.sentence.subject] = await gate.screening.entries(params.sentence.subject)
    ctx = SentenceContext(
        graph=gate.graph,
        analytics=gate.analytics,
        investigation_scope=gate.investigation_id,
        ontology=gate.ontology,
        hotlisted=hotlisted,
        screening_entries=entries,
    )
    hits = await judge_sentence(
        rule, deployer, written, events, ctx, pattern=saved.definition, scheme=gate.scheme
    )
    said = sentence_words(params.sentence, gate.ontology)
    return [
        Finding(
            rule=rule,
            deployer=deployer,
            typology="sentence",
            subject=hit.node.id,
            refs=hit.refs,
            words=f"{hit.words}. {said}",
            node_ids=[hit.node.id],
        )
        for hit in hits
    ]


__all__ = [
    "holds_on_hit",
    "is_deployment_wide",
    "is_just_me",
    "judge_sentence_rule",
    "rows_of_finding",
    "sentence_alert_fields",
    "sentence_rows",
]
