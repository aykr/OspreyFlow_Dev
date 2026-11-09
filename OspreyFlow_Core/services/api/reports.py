"""A case's report (`06_DECISIONS.md` ADR-111): the figures behind the Glass's Reports view and the
dashboards' feed — one computation, so the two cannot disagree.

**Every figure is counted as its reader (rule 3).** Alerts come through the one queue's own
all-or-nothing check (`alert_queue.monitoring_queue`, scoped in the query, one batched read): an
alert naming anything the reader cannot see is in no total, outcome, age bucket or monitoring
figure (ADR-134 decision 2) — the CLAUDE.md "histogram bucket" clause read literally. Held rows are
counted through `HeldRowStore.list_authorized`, which filters marking and reach in SQL, and only for
Editors and above (the route decides). Each customer's KYC status is `kyc.assess` as the reader.

**Bounded, never cut (rule 2).** Past `ALERT_BOUND` visible alerts in the period, or
`CUSTOMER_BOUND` customers, the report answers `ReportLimitExceeded` — counted from what the
reader sees, so the refusal discloses nothing a figure would not.

**Figures only.** Labels, dates and numbers; never a name, an identifier or an alert's words — the
feed leaves the Glass, and `test_the_feed_carries_no_free_text` holds it to that.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from ports.analytics import AnalyticsPort
from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.domain import (
    CLOSING_REASONS,
    POLE_CLASS_ORDER,
    AgeBand,
    AgeCount,
    Alert,
    ExpandRequest,
    HeldFigures,
    KycFigures,
    LabelledWeekCount,
    MonitoringFigures,
    OntologySchema,
    OutcomeCount,
    PoleClass,
    PoleClassCount,
    PoleFigures,
    PoleTypeCount,
    Principal,
    QueuedAlert,
    ReportCount,
    ReportFigures,
    ReportLimitExceeded,
    TeamCount,
    WeekCount,
)
from schemas.explore import TypeCounts

from .alert_queue import monitoring_queue
from .alerts import AlertStore
from .explore import ExploreService
from .held_rows import HeldRowStore
from .kyc import assess
from .kyc_rules import CUSTOMER_TYPES

ALERT_BOUND = 10_000
CUSTOMER_BOUND = 2_000
#: How many documents' holders one expansion asks for.
_EXPAND_BATCH = 200
AGE_LABELS: tuple[AgeBand, ...] = ("under a day", "1 to 7 days", "7 to 30 days", "over 30 days")
#: The Outcomes figures, in the order the feed carries them: open, claimed, each closing reason
#: (ADR-133 Amendment 5), and closed with none.
OUTCOME_FIGURES = ("open", "claimed", *CLOSING_REASONS, "closed")
BANDS = ("low", "medium", "high")


class ReportLimitExceededError(Exception):
    def __init__(self, detail: ReportLimitExceeded) -> None:
        super().__init__(f"report bound of {detail.cap} {detail.cap_kind} exceeded")
        self.detail = detail


def _age_label(created: datetime, now: datetime) -> AgeBand:
    days = (now - created).total_seconds() / 86400
    if days < 1:
        return AGE_LABELS[0]
    if days < 7:
        return AGE_LABELS[1]
    if days < 30:
        return AGE_LABELS[2]
    return AGE_LABELS[3]


def _alert_figures(
    visible: Sequence[Alert], *, start: date, now: datetime
) -> tuple[list[WeekCount], list[ReportCount], list[OutcomeCount], int]:
    in_period = [a for a in visible if a.created_at.date() >= start]
    if len(in_period) > ALERT_BOUND:
        raise ReportLimitExceededError(
            ReportLimitExceeded(cap_kind="alerts", cap=ALERT_BOUND, would_be=len(in_period))
        )
    weeks: Counter[tuple[date, str]] = Counter()
    outcomes: dict[str, OutcomeCount] = {}
    for alert in in_period:
        day = alert.created_at.date()
        typology = alert.typology or "other"
        weeks[(day - timedelta(days=day.weekday()), typology)] += 1
        row = outcomes.setdefault(typology, OutcomeCount(typology=typology))
        if alert.status == "closed":
            # Each closing reason its own figure, and one with none (taken back) closed: never open
            # (build order step 18c).
            name = alert.disposition or "closed"
            setattr(row, name, getattr(row, name) + 1)
        elif alert.status == "claimed":
            row.claimed += 1
        else:
            row.open += 1
    ages = Counter(_age_label(a.created_at, now) for a in visible if a.status != "closed")
    return (
        [WeekCount(week_start=w, typology=t, count=n) for (w, t), n in sorted(weeks.items())],
        [ReportCount(label=label, value=ages[label]) for label in AGE_LABELS],
        [outcomes[t] for t in sorted(outcomes)],
        len(in_period),
    )


def _week_of(moment: datetime) -> date:
    day = moment.date()
    return day - timedelta(days=day.weekday())


def _weeks(counts: Counter[tuple[date, str, str]]) -> list[LabelledWeekCount]:
    return [
        LabelledWeekCount(week_start=w, label=label, typology=typology, count=n)
        for (w, label, typology), n in sorted(counts.items())
    ]


#: The rule group an alert of each kind is counted under: each typology by its typology (a closed
#: name, where a rule's own name is analyst-written text the feed never carries), hotlists together,
#: monitors together (ADR-134 decision 2).
_RULE_GROUP = {"typology": "typology", "hotlist": "hotlists", "monitor": "monitors"}
#: Still in the queue: open, claimed, or proposed for closing (ADR-146 decision 6, G9: a proposed
#: close counts as open everywhere).
_IN_QUEUE = ("open", "claimed", "closing")
#: ADR-145 Amendment 4 decision 9's "closed as not of interest": the two closing reasons that say
#: the alert found nothing to act on (ADR-133 decision 7's list).
NOT_OF_INTEREST = ("false_positive", "no_further_action")


def _group(q: QueuedAlert) -> tuple[str, str]:
    """The rule group an alert is counted under, as `raised_by_rule` labels it."""
    # A kind this table does not name yet (ADR-146 decision 1's analyst and drawn-watch alerts,
    # L2.10) is counted under its own name rather than refused.
    return _RULE_GROUP.get(q.kind, q.kind), (q.alert.typology or "") if q.kind == "typology" else ""


def _panel_figures(
    visible: Sequence[QueuedAlert], *, start: date, now: datetime, reader_id: str
) -> tuple[list[AgeCount], list[TeamCount]]:
    """The *Alerts* panel's open by source and age (ADR-146 decision 9) and the board's team view
    (ADR-145 Amendment 4 decision 9), by rule group, over the same rows as every other figure."""
    ages: Counter[tuple[str, str, AgeBand]] = Counter()
    team: dict[tuple[str, str], TeamCount] = {}
    for q in visible:
        label, typology = _group(q)
        row = team.setdefault((label, typology), TeamCount(label=label, typology=typology))
        alert = q.alert
        if alert.status in _IN_QUEUE:
            ages[(label, typology, _age_label(alert.created_at, now))] += 1
            if alert.assignee is None:
                row.unassigned += 1
            elif alert.assignee == reader_id:
                row.mine += 1
            if now - alert.created_at > timedelta(days=7):
                row.older_than_week += 1
        elif alert.status == "closed" and (alert.decided_at or alert.created_at).date() >= start:
            row.closed += 1
            if alert.disposition in NOT_OF_INTEREST:
                row.not_of_interest += 1
    by_age = [
        AgeCount(label=label, typology=typology, age=age, count=n)
        for (label, typology, age), n in sorted(ages.items())
    ]
    return by_age, [team[k] for k in sorted(team)]


def _monitoring_figures(
    visible: Sequence[QueuedAlert], *, start: date, now: datetime, reader_id: str
) -> MonitoringFigures:
    """ADR-134 decision 2, over every alert the reader's queue holds whole (any kind)."""
    raised: Counter[tuple[date, str, str]] = Counter()
    matches: Counter[tuple[date, str, str]] = Counter()
    closed: Counter[tuple[date, str, str]] = Counter()
    took: Counter[str] = Counter()
    in_period = [q for q in visible if q.alert.created_at.date() >= start]
    if len(in_period) > ALERT_BOUND:
        raise ReportLimitExceededError(
            ReportLimitExceeded(cap_kind="alerts", cap=ALERT_BOUND, would_be=len(in_period))
        )
    for q in in_period:
        week = _week_of(q.alert.created_at)
        typology = (q.alert.typology or "") if q.kind == "typology" else ""
        raised[(week, _RULE_GROUP.get(q.kind, q.kind), typology)] += 1
        if q.kind == "hotlist":
            matches[(week, "hotlists", "")] += 1
    for q in visible:
        if q.alert.status != "closed":
            continue
        decided = q.alert.decided_at or q.alert.created_at
        if decided.date() < start:
            continue
        outcome = q.alert.disposition or "closed"
        closed[(_week_of(decided), outcome, "")] += 1
        took[_age_label(q.alert.created_at, decided)] += 1
    open_by_source, team = _panel_figures(visible, start=start, now=now, reader_id=reader_id)
    return MonitoringFigures(
        open_by_source=open_by_source,
        team=team,
        raised_by_rule=_weeks(raised),
        closed_by_outcome=_weeks(closed),
        time_to_close=[ReportCount(label=label, value=took[label]) for label in AGE_LABELS],
        hotlist_matches=_weeks(matches),
    )


async def alert_report(
    alerts: AlertStore,
    graph: GraphPort,
    analytics: AnalyticsPort,
    investigation_id: str,
    reader: Principal,
    *,
    today: date,
    period_weeks: int = 12,
) -> ReportFigures:
    """The report's alert figures alone, as `reader`: one read of the one queue — which rows is the
    query's answer, what they name one batched read as the reader (`monitoring_queue`) — from which
    the typology figures (ADR-111) and the monitoring figures (ADR-134 decision 2) are both
    counted, so they cannot disagree about which alerts the reader may see."""
    now = datetime.now(UTC)
    start = today - timedelta(weeks=period_weeks)
    every_kind = await monitoring_queue(alerts, graph, analytics, investigation_id, reader)
    typology = [q.alert for q in every_kind if q.kind == "typology"]
    by_week, by_age, outcomes, total = _alert_figures(typology, start=start, now=now)
    return ReportFigures(
        period_weeks=period_weeks,
        as_of=today,
        generated_at=now,
        alerts_total=total,
        alerts_by_week=by_week,
        open_by_age=by_age,
        outcomes=outcomes,
        monitoring=_monitoring_figures(every_kind, start=start, now=now, reader_id=reader.id),
    )


async def _customers(graph: GraphPort, reader: Principal) -> list[str]:
    """The people and organisations the reader can see holding a verifying document."""
    documents: list[str] = []
    cursor = None
    while True:
        page = await graph.list_nodes("Document", reader, cursor=cursor)
        documents.extend(n.id for n in page.nodes)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    holders: set[str] = set()
    for i in range(0, len(documents), _EXPAND_BATCH):
        found = await graph.expand(
            ExpandRequest(
                node_ids=documents[i : i + _EXPAND_BATCH],
                edge_types=["VERIFIED_BY"],
                direction="in",
            ),
            reader,
        )
        holders |= {n.id for n in found.nodes if n.type in CUSTOMER_TYPES}
        if len(holders) > CUSTOMER_BOUND:
            raise ReportLimitExceededError(
                ReportLimitExceeded(cap_kind="customers", cap=CUSTOMER_BOUND, would_be=len(holders))
            )
    return sorted(holders)


async def _kyc_figures(
    graph: GraphPort, compute: ComputePort, reader: Principal, today: date
) -> KycFigures:
    statuses = [
        await assess(graph, compute, node_id, reader, today=today)
        for node_id in await _customers(graph, reader)
    ]
    bands: Counter[str] = Counter(s.risk_band for s in statuses)
    verified = sum(1 for s in statuses if s.status == "verified")
    return KycFigures(
        customers=len(statuses),
        verified=verified,
        unverified=len(statuses) - verified,
        by_band=[ReportCount(label=band, value=bands[band]) for band in BANDS],
    )


#: The one entity type left out of every POLE figure (ADR-126 decision 4): alerts are the Figures
#: tab's own subject, and system-written alerts from shared datasets would disagree with
#: `alerts_total`.
_LEFT_OUT_OF_POLE = "Alert"


def pole_figures(
    counts: TypeCounts, ontology: OntologySchema, *, counted_at: datetime
) -> PoleFigures:
    """The POLE summary from the kept per-type counts (ADR-126 decision 4), classified by the
    composed ontology's `pole_class`. A stored type the ontology does not know is under `other`;
    `Alert` is in no figure; a link counts unless its type is `system`, one the ontology does not
    know included."""
    class_of = {e.name: e.pole_class for e in ontology.entity_types}
    system_links = {e.name for e in ontology.edge_types if e.system}
    by_class: dict[PoleClass, list[PoleTypeCount]] = {c: [] for c in PoleClass}
    other: list[PoleTypeCount] = []
    for entity_type, count in counts.nodes.items():
        if entity_type == _LEFT_OUT_OF_POLE or count < 1:
            continue
        row = PoleTypeCount(entity_type=entity_type, count=count)
        if entity_type in class_of:
            by_class[class_of[entity_type]].append(row)
        else:
            other.append(row)

    def largest_first(rows: list[PoleTypeCount]) -> list[PoleTypeCount]:
        return sorted(rows, key=lambda r: (-r.count, r.entity_type))

    return PoleFigures(
        classes=[
            PoleClassCount(
                pole_class=c,
                total=sum(r.count for r in by_class[c]),
                types=largest_first(by_class[c]),
            )
            for c in POLE_CLASS_ORDER
        ],
        other=largest_first(other),
        links=sum(n for t, n in counts.edges.items() if t not in system_links),
        counted_at=counted_at,
    )


async def case_report(
    *,
    alerts: AlertStore,
    graph: GraphPort,
    analytics: AnalyticsPort,
    held: HeldRowStore,
    compute: ComputePort,
    explore: ExploreService,
    ontology: OntologySchema,
    domains: Sequence[str],
    investigation_id: str,
    reader: Principal,
    today: date,
    period_weeks: int = 12,
    show_held: bool = False,
) -> ReportFigures:
    figures = await alert_report(
        alerts, graph, analytics, investigation_id, reader, today=today, period_weeks=period_weeks
    )
    held_figures = None
    if show_held:
        held_figures = HeldFigures(
            held=len(await held.list_authorized(investigation_id, reader, status="held")),
            released=len(await held.list_authorized(investigation_id, reader, status="released")),
            rejected=len(await held.list_authorized(investigation_id, reader, status="rejected")),
        )
    # ADR-126 decision 3: `kyc` when `fibo` is among the case's packs, `pole` when they are anything
    # other than exactly `[fibo]`. Each is computed only when it is to be sent, so a case without
    # `fibo` assesses no customer and a pure AML case reads no counts.
    kyc = await _kyc_figures(graph, compute, reader, today) if "fibo" in domains else None
    pole = None
    if sorted(set(domains)) != ["fibo"]:
        counts = await explore.counts(reader)
        if counts.computed_at is None:
            # A kept entry from before the stamp existed: a miss. Recount past the cache, and never
            # put "now" on counts that were taken earlier.
            counts = await explore.counts(reader, fresh=True)
        if counts.computed_at is None:
            raise RuntimeError(
                "the explore counts carry no computed_at, so the card cannot say when"
            )
        pole = pole_figures(counts, ontology, counted_at=counts.computed_at)
    return figures.model_copy(update={"held": held_figures, "kyc": kyc, "pole": pole})


def feed_rows(figures: ReportFigures) -> list[tuple[str, str, str, str, int]]:
    """The report flattened for a spreadsheet or a BI tool: section, label, typology, week,
    value."""
    rows: list[tuple[str, str, str, str, int]] = [("total", "alerts", "", "", figures.alerts_total)]
    rows += [
        ("raised", "", w.typology, w.week_start.isoformat(), w.count)
        for w in figures.alerts_by_week
    ]
    rows += [("open_by_age", c.label, "", "", c.value) for c in figures.open_by_age]
    for o in figures.outcomes:
        rows += [("outcome", label, o.typology, "", getattr(o, label))
                 for label in OUTCOME_FIGURES]  # fmt: skip
    # ADR-134 decision 2: the monitoring dashboard's sections, every kind of alert.
    m = figures.monitoring
    rows += [("raised_by_rule", w.label, w.typology, w.week_start.isoformat(), w.count)
             for w in m.raised_by_rule]  # fmt: skip
    rows += [("closed", w.label, "", w.week_start.isoformat(), w.count)
             for w in m.closed_by_outcome]  # fmt: skip
    rows += [("time_to_close", c.label, "", "", c.value) for c in m.time_to_close]
    rows += [("hotlist_matches", w.label, "", w.week_start.isoformat(), w.count)
             for w in m.hotlist_matches]  # fmt: skip
    # ADR-146 decision 9 and ADR-145 Amendment 4 decision 9: the Alerts panel's and the team view's
    # figures. The age band joins the rule group in the label, as `pole_type` joins its class: the
    # week column holds a date or nothing.
    rows += [("open_by_source", f"{c.label}:{c.age}", c.typology, "", c.count)
             for c in m.open_by_source]  # fmt: skip
    team_figures = ("unassigned", "mine", "older_than_week", "closed", "not_of_interest")
    for t in m.team:
        rows += [
            (f"team_{name}", t.label, t.typology, "", getattr(t, name)) for name in team_figures
        ]
    if figures.held is not None:
        rows += [("held_rows", label, "", "", getattr(figures.held, label))
                 for label in ("held", "released", "rejected")]  # fmt: skip
    if figures.kyc is not None:
        rows += [("kyc", label, "", "", getattr(figures.kyc, label))
                 for label in ("customers", "verified", "unverified")]  # fmt: skip
        rows += [("kyc_band", c.label, "", "", c.value) for c in figures.kyc.by_band]
    if figures.pole is not None:
        # `typology` stays empty: a BI user filtering typologies must never meet an entity type.
        # A label is built only from the closed `pole_class` and an ontology `entity_type`.
        for c in figures.pole.classes:
            cls = c.pole_class.value
            rows.append(("pole", cls, "", "", c.total))
            rows += [("pole_type", f"{cls}:{t.entity_type}", "", "", t.count) for t in c.types]
        rows += [("pole_other", f"other:{t.entity_type}", "", "", t.count)
                 for t in figures.pole.other]  # fmt: skip
        rows.append(("pole_links", "links", "", "", figures.pole.links))
    return rows


__all__ = [
    "ReportLimitExceededError",
    "alert_report",
    "case_report",
    "feed_rows",
    "pole_figures",
]
