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
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from ontology.influencers import (
    StrengthSettings,
    load_strength_defaults,
    resolve_influencers,
    resolve_settings,
)
from schemas.analytics import EventRecord
from schemas.domain import EdgeWrite, Interval, NodeWrite, PatternQuery, Principal, TypologyRule
from schemas.sentences import SentenceRuleParams
from schemas.strength import ActiveInfluencer

from .dataset_scope import made_in
from .kyc_rules import customer_rows
from .pattern_store import PatternNotFoundError
from .rule_sentences import (
    Hit,
    SentenceContext,
    _split,
    judge_sentence,
    judge_subjects,
    sentence_of,
    sentence_words,
)
from .screening import ListClearance

if TYPE_CHECKING:
    from .rule_evaluation import Finding, RuleGate
    from .strength_influencers import InfluencerStore


def sentence_of_rule(rule: TypologyRule) -> SentenceRuleParams | None:
    return rule.params if isinstance(rule.params, SentenceRuleParams) else None


def is_just_me(rule: TypologyRule) -> bool:
    """A rule whose alerts are its author's alone: a sentence just for them, or a pattern or
    template rule made through `POST …/rules` (ADR-146 Amendment 6 decision 12)."""
    if rule.just_me:
        return True
    params = sentence_of_rule(rule)
    return params is not None and params.sentence.scope == "just_me"


def routed_team_of(rule: TypologyRule) -> str | None:
    """ADR-146 decision 8: the named team a sentence rule's alerts go to, or `None` (the case's)."""
    params = sentence_of_rule(rule)
    if params is None or params.sentence.team != "team":
        return None
    return params.sentence.team_id


def writes_no_alert_node(rule: TypologyRule) -> bool:
    """A rule whose alerts some members of the case may not read puts nothing in the case's graph:
    one just for its author (K8), and one routed to a named team (ADR-146 decision 8). An `Alert`
    node carries the finding's words to every member who may read its markings (expand, a node
    list), which the queue's team check would not reach (rule 3)."""
    return is_just_me(rule) or routed_team_of(rule) is not None


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
    if params is None and rule.just_me:
        # ADR-146 Amendment 6 decision 12: a template rule just for its author, as a sentence's.
        return {"rule_id": f"monitor:sentence:{rule.id}", "typology": None, "team": None,
                "dataset_id": rule.dataset_id}  # fmt: skip
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
            "severity": sentence.severity, "team": team, "dataset_id": dataset,
            "routed_team": routed_team_of(rule)}  # fmt: skip


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


async def strength_context(
    store: InfluencerStore | None, investigation_id: str
) -> tuple[list[ActiveInfluencer], tuple[str, ...], StrengthSettings]:
    """ADR-139: the influencers in force in the case, the types rarity leaves out, and (Amendment
    2) the composition and rarity measure. With no store (a run that has none), the weights
    file's alone."""
    defaults = load_strength_defaults()
    if store is None:
        active, _ = resolve_influencers(defaults.influencers)
        return active, defaults.rarity_exclude_types, resolve_settings(defaults)
    active, _, _ = await store.active_for_case(investigation_id, defaults.influencers)
    settings = await store.settings_for_case(investigation_id, defaults)
    return active, defaults.rarity_exclude_types, settings


async def _context(
    rule: TypologyRule, deployer: Principal, gate: RuleGate
) -> tuple[SentenceRuleParams, PatternQuery, SentenceContext]:
    """What judging the sentence reads, each as its author: the drawn pattern read afresh, the
    author's own hotlists, the screening lists' entries."""
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
        subject = params.sentence.subject
        if relationship.list_id is not None:
            # ADR-146 decision 3: the one Studio list the rule names, read within its dataset.
            if gate.rule_lists is None:
                raise RuntimeError("this run cannot read the screening list the rule names")
            entries[subject] = await gate.rule_lists(rule, relationship.list_id, subject)
        else:
            if gate.screening is None:
                raise RuntimeError("this run has no screening lists to screen against")
            # ADR-146 Amendment 7 point 8 (the orchestrator's review, item 1): only the lists the
            # deployer is cleared for, in the store's own query.
            entries[subject] = await gate.screening.entries(
                subject, cleared=ListClearance.of(deployer, gate.scheme)
            )
    influencers, exclude, settings = await strength_context(
        gate.influencers, gate.investigation_id
    )
    ctx = SentenceContext(
        graph=gate.graph,
        analytics=gate.analytics,
        investigation_scope=gate.investigation_id,
        ontology=gate.ontology,
        hotlisted=hotlisted,
        screening_entries=entries,
        influencers=influencers,
        rarity_exclude_types=exclude,
        composition=settings.composition,
        rarity_measure=settings.rarity_measure,
    )
    return params, saved.definition, ctx


def _findings(
    rule: TypologyRule, deployer: Principal, hits: Sequence[Hit], said: str
) -> list[Finding]:
    from .rule_evaluation import Finding

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


async def judge_sentence_rule(
    rule: TypologyRule,
    deployer: Principal,
    written: Sequence[NodeWrite | EdgeWrite],
    events: Sequence[EventRecord],
    gate: RuleGate,
) -> list[Finding]:
    params, pattern, ctx = await _context(rule, deployer, gate)
    hits = await judge_sentence(
        rule, deployer, written, events, ctx, pattern=pattern, scheme=gate.scheme
    )
    return _findings(rule, deployer, hits, sentence_words(params.sentence, gate.ontology))


#: How far back a scheduled run reads: the day, or the week, since the last slot.
SCHEDULE_PERIOD = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}


async def run_scheduled_rule(
    rule: TypologyRule, deployer: Principal, gate: RuleGate, *, now: datetime
) -> int:
    """One scheduled slot (below); see `_judge_stored`."""
    return await _judge_stored(rule, deployer, gate, now=now, on_refresh=False)


#: ADR-146 decision 3 (L2.11): a rule that runs when its screening list refreshes judges what was
#: stored over the last day, as a daily schedule does, against the list as it now stands.
LIST_REFRESH_PERIOD = timedelta(days=1)


async def run_on_list_refresh(
    rule: TypologyRule, deployer: Principal, gate: RuleGate, *, now: datetime
) -> int:
    """ADR-146 decision 3, *When* a screening list refreshes: the rule judged once, as its author,
    over the last day of what is stored, against the list's new version; each new finding raised
    once, as at a load. Returns how many alerts it raised."""
    return await _judge_stored(rule, deployer, gate, now=now, on_refresh=True)


async def _judge_stored(
    rule: TypologyRule, deployer: Principal, gate: RuleGate, *, now: datetime, on_refresh: bool
) -> int:
    """ADR-133 decision 1, stage (d): one scheduled slot of a sentence rule, as its author over what
    is stored — the subjects its drawn pattern matches as the author may see them (rule 3), judged
    over the last day or week (a frequency over its own span before that) — each new finding raised
    as at a load, once. More subjects than the rule's `max_matches` is refused in words, never
    judged in part (rule 2). Returns how many alerts it raised."""
    params, pattern, ctx = await _context(rule, deployer, gate)
    sentence = params.sentence
    if gate.ontology is not None:
        sentence = sentence_of(pattern, sentence, gate.ontology)
    if not on_refresh and sentence.schedule is None:
        raise RuntimeError("the rule has no schedule to run on")
    counted = await gate.graph.match_count(pattern, deployer, ceiling=params.max_matches + 1)
    if counted > params.max_matches:
        raise RuntimeError(
            f"its drawn pattern matches more than {params.max_matches:,} subjects, the rule's "
            "limit; none was judged"
        )
    period = (
        LIST_REFRESH_PERIOD
        if on_refresh or sentence.schedule is None
        else SCHEDULE_PERIOD[sentence.schedule.every]
    )
    span = timedelta(days=getattr(sentence.frequency, "within_days", 0))
    window = Interval(valid_from=now - period - span, valid_to=now)
    firsts = Interval(valid_from=now - period, valid_to=now)
    subjects: list[Any] = []
    if counted:
        matched = await gate.graph.match(
            pattern.model_copy(update={"limit": params.max_matches}), deployer
        )
        subjects = sorted(
            (n for n in matched.nodes if n.type == sentence.subject), key=lambda n: n.id
        )
    rest = _split(sentence, gate.ontology)[1] if gate.ontology is not None else sentence.conditions
    hits = await judge_subjects(
        subjects, sentence, deployer, ctx, window=window, firsts=firsts, conditions=rest
    )
    from .rule_evaluation import PartlyRaised

    raised = 0
    try:
        for finding in _findings(rule, deployer, hits, sentence_words(sentence, gate.ontology)):
            if await gate.seen(finding):
                continue
            await gate.raise_committed(finding)
            raised += 1
    except Exception as error:
        if raised:
            raise PartlyRaised(raised, error) from error
        raise
    return raised


__all__ = [
    "holds_on_hit",
    "is_deployment_wide",
    "is_just_me",
    "judge_sentence_rule",
    "rows_of_finding",
    "run_on_list_refresh",
    "run_scheduled_rule",
    "routed_team_of",
    "sentence_alert_fields",
    "writes_no_alert_node",
    "sentence_rows",
]
