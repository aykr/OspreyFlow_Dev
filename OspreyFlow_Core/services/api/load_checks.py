"""The Ingest Studio's "Checks on load" step and Verify's would-be alerts (`06_DECISIONS.md` ADR-133
decision 6, stage (d); `09_INGEST_STUDIO.md` §5a).

**Attaching, never writing (decision 6).** The step lists the load-time rules of the case and of the
whole deployment — rules analysts wrote — and the data engineer chooses which apply to this pipeline
and what a hit does here: load with its alert, or hold the rows for a reviewer (before commit only).
A choice names rules by id (`LoadCheck`); it cannot carry a rule, so the step writes no rule. A rule
just for its author is their own watch, not a check on a load, and is not offered; a
whole-deployment rule applies to every pipeline and cannot be left off one
(`recipe_run.always_judges`).

**Verify (decision 6: "the alerts a sample would raise, beside the rejection report").** The
pipeline's checks judge the dry run's sample as they would judge the load — each as its own author,
resolved afresh — over the rows the person verifying may read in full. Nothing is written: the gate
Verify builds holds an alert store, a quarantine and a signature set that refuse every call
(`READ_ONLY`). A would-be alert is shown only where every entity it names is one the sample shows
the person verifying (rule 3). A check a dry run cannot judge — one that reads money movements or
events, or links in the stored graph — is said, with why, never left out silently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from schemas.domain import (
    AlertSeverity,
    Edge,
    EdgeWrite,
    Node,
    NodeWrite,
    OntologySchema,
    TypologyRule,
)
from schemas.monitoring import (
    CheckNotJudged,
    LoadCheck,
    LoadCheckOnHit,
    LoadCheckRule,
    LoadChecksView,
    WouldRaise,
)
from schemas.sentences import GRAPH_RELATIONSHIPS, SentenceRuleParams

from .alert_queue import node_name
from .alerts import default_severity
from .aml_rules import AML_TYPOLOGIES
from .rule_evaluation import FLOW_TYPOLOGIES, RuleGate
from .rule_sentences import sentence_words
from .sentence_rules import holds_on_hit, is_deployment_wide, is_just_me
from .typology_rules import LoadChecksRecord


class ChecksRefused(ValueError):
    """A choice of checks that cannot be kept, in words."""


class _ReadOnly:
    """A store Verify's gate must never touch: any call fails, so a write cannot happen quietly."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attr: str) -> Any:
        raise RuntimeError(f"Verify writes nothing, and asked the {self._name} to {attr}")


#: `recipe_run._rule_gate`'s stores for Verify: each refuses every call.
READ_ONLY = {
    "alerts_store": _ReadOnly("alert store"),
    "held_rows": _ReadOnly("quarantine"),
    "valkey": _ReadOnly("signature set"),
    "audit": _ReadOnly("audit (a rule's own record of a load)"),
    "expiries": None,
}


def offered(rule: TypologyRule) -> bool:
    """A rule the step offers: running, or waiting for approval; judged as data loads; and the
    case's or the deployment's, not one person's own."""
    return (
        rule.status in ("pending", "active") and rule.trigger != "schedule" and not is_just_me(rule)
    )


def _sentence(rule: TypologyRule) -> SentenceRuleParams | None:
    return rule.params if isinstance(rule.params, SentenceRuleParams) else None


def severity_of(rule: TypologyRule) -> AlertSeverity:
    params = _sentence(rule)
    if params is not None:
        return params.sentence.severity
    return default_severity("typology", rule.params.typology)


def rule_words(rule: TypologyRule, ontology: OntologySchema | None) -> str:
    params = _sentence(rule)
    if params is not None:
        return sentence_words(params.sentence, ontology)
    when = "before each load commits" if rule.trigger == "pre_commit" else "after each load commits"
    return f"The {rule.params.typology.replace('_', ' ')} typology, {when}."


def checks_view(
    recipe_id: str,
    rules: Sequence[TypologyRule],
    record: LoadChecksRecord | None,
    ontology: OntologySchema | None,
) -> LoadChecksView:
    available = [
        LoadCheckRule(
            rule_id=r.id,
            name=r.name,
            words=rule_words(r, ontology),
            scope="deployment" if is_deployment_wide(r) else "this_case",
            trigger=r.trigger,
            severity=severity_of(r),
            status="pending" if r.status == "pending" else "active",
            can_hold=r.trigger == "pre_commit",
            always_applies=is_deployment_wide(r),
            authors_on_hit="hold" if holds_on_hit(r) else "alert",
        )
        for r in rules
        if offered(r)
    ]
    return LoadChecksView(
        recipe_id=recipe_id,
        chosen=record is not None,
        checks=list(record.checks) if record else [],
        available=available,
        set_by=record.set_by if record else None,
        set_at=record.set_at if record else None,
    )


def check_choice(checks: Sequence[LoadCheck], rules: Sequence[TypologyRule]) -> list[LoadCheck]:
    """The engineer's choice, each check against the rules the step offers them: a rule not
    offered (another case's, one person's own, a retired one, or none) is refused, as is holding on
    a rule that runs after commit, each in words."""
    by_id = {r.id: r for r in rules if offered(r)}
    seen: set[str] = set()
    kept: list[LoadCheck] = []
    for check in checks:
        rule = by_id.get(check.rule_id)
        if rule is None:
            raise ChecksRefused(f"There is no rule “{check.rule_id}” in this case to attach.")
        if check.on_hit == "hold" and rule.trigger != "pre_commit":
            raise ChecksRefused(
                f"“{rule.name}” runs after the load commits, so a hit cannot hold its rows."
            )
        if check.rule_id in seen:
            raise ChecksRefused(f"“{rule.name}” is attached twice.")
        seen.add(check.rule_id)
        kept.append(check)
    return kept


# --- Verify -------------------------------------------------------------------------------------


_MOVEMENTS = (
    "It reads money movements, which a dry run does not make; it is judged when the load runs."
)
_STORED_GRAPH = (
    "It is matched against the stored graph, so it is judged only once the load has committed."
)
_STORED_LINKS = (
    "It reads links from the stored graph, so it is judged only once the load has committed."
)
_EVENTS = "It counts events, which a dry run does not make; it is judged when the load runs."


def _why_not_judged(rule: TypologyRule) -> str | None:
    typology = rule.params.typology
    if typology in FLOW_TYPOLOGIES or typology in AML_TYPOLOGIES:
        return _MOVEMENTS
    if typology == "pattern":
        return _STORED_GRAPH
    params = _sentence(rule)
    if params is not None:
        relationship = params.sentence.relationship
        if relationship is not None and relationship.kind in GRAPH_RELATIONSHIPS:
            return _STORED_LINKS
        if params.sentence.frequency is not None:
            return _EVENTS
    return None


def as_writes(nodes: Sequence[Node], edges: Sequence[Edge]) -> list[NodeWrite | EdgeWrite]:
    """The dry run's would-be elements in the shape a load hands its rules."""
    written: list[NodeWrite | EdgeWrite] = [
        NodeWrite(
            id=n.id,
            type=n.type,
            properties=n.properties,
            provenance=n.provenance,
            handling=n.handling,
            created_by=n.audit.created_by,
            created_at=n.audit.created_at,
            datasets=n.datasets,
        )  # fmt: skip
        for n in nodes
    ]
    written.extend(
        EdgeWrite(
            id=e.id,
            type=e.type,
            source=e.source,
            target=e.target,
            properties=e.properties,
            interval=e.interval,
            provenance=e.provenance,
            handling=e.handling,
            created_by=e.audit.created_by,
            created_at=e.audit.created_at,
        )  # fmt: skip
        for e in edges
    )
    return written


async def would_raise(
    gate: RuleGate | None,
    written: Sequence[NodeWrite | EdgeWrite],
    shown: Mapping[str, Node],
) -> tuple[list[WouldRaise], list[CheckNotJudged], int]:
    """What the pipeline's checks would raise over the sample, as at its load, writing nothing.
    `written` is what the sample would write that the person verifying may read in full; `shown`
    is the sample as they see it. Returns the would-be alerts, the checks not judged, and how many
    checks were judged."""
    if gate is None:
        return [], [], 0
    raised: list[WouldRaise] = []
    not_judged: list[CheckNotJudged] = []
    judged = 0
    for rule in gate.rules:
        if not offered(rule):
            continue
        why = _why_not_judged(rule)
        if why is not None:
            not_judged.append(CheckNotJudged(rule_id=rule.id, rule_name=rule.name, why=why))
            continue
        deployer = await gate._deployer(rule)
        if deployer is None:
            not_judged.append(CheckNotJudged(
                rule_id=rule.id, rule_name=rule.name,
                why="Its author could not be acted as, so it could not be judged here.",
            ))  # fmt: skip
            continue
        # Judged over the rows as written, as a rule that runs before commit judges them.
        as_written = rule.model_copy(update={"trigger": "pre_commit"})
        try:
            findings = await gate._judge_rule(as_written, deployer, [], written)
        except Exception as error:  # noqa: BLE001 - said, never raised into Verify
            not_judged.append(CheckNotJudged(rule_id=rule.id, rule_name=rule.name,
                                             why=f"It could not be judged: {error}."))  # fmt: skip
            continue
        judged += 1
        on_hit: LoadCheckOnHit = "hold" if gate.holds(rule) else "alert"
        for finding in findings:
            # Named: the sample's entities this reader sees, and what the rule itself would write
            # beside its alert (a screening match's listed party, from the reference list).
            own = {w.id for w in finding.pending}
            if finding.subject not in shown or not set(finding.node_ids) <= set(shown) | own:
                continue  # names something the sample does not show this reader
            entity = shown[finding.subject]
            raised.append(WouldRaise(
                rule_id=rule.id, rule_name=rule.name, severity=severity_of(rule), on_hit=on_hit,
                entity_id=entity.id, entity_type=entity.type, entity_name=node_name(entity),
            ))  # fmt: skip
    return raised, not_judged, judged


def readable_in_full(nodes: Sequence[Node], shown: Mapping[str, Node]) -> list[Node]:
    """The would-be nodes the reader sees unmasked: the ones a would-be alert may name."""
    return [n for n in nodes if n.id in shown and shown[n.id].properties == n.properties]


__all__ = [
    "READ_ONLY",
    "ChecksRefused",
    "as_writes",
    "check_choice",
    "checks_view",
    "offered",
    "readable_in_full",
    "rule_words",
    "would_raise",
]
