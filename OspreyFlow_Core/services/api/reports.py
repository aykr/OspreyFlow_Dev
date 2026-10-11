"""A case's report (`06_DECISIONS.md` ADR-111): the figures behind the Glass's Reports view and the
dashboards' feed — one computation, so the two cannot disagree.

**Every figure is counted as its reader (rule 3).** Alerts come through the case queue's own
all-or-nothing check (`alert_queue.queue`): an alert naming anything the reader cannot see is in no
total, outcome or age bucket — the CLAUDE.md "histogram bucket" clause read literally. Held rows are
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

from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.domain import (
    Alert,
    ExpandRequest,
    HeldFigures,
    KycFigures,
    OutcomeCount,
    Principal,
    ReportCount,
    ReportFigures,
    ReportLimitExceeded,
    WeekCount,
)

from .alert_queue import queue
from .alerts import AlertStore
from .held_rows import HeldRowStore
from .kyc import assess
from .kyc_rules import CUSTOMER_TYPES

ALERT_BOUND = 10_000
CUSTOMER_BOUND = 2_000
#: How many documents' holders one expansion asks for.
_EXPAND_BATCH = 200
AGE_LABELS = ("under a day", "1 to 7 days", "7 to 30 days", "over 30 days")
BANDS = ("low", "medium", "high")


class ReportLimitExceededError(Exception):
    def __init__(self, detail: ReportLimitExceeded) -> None:
        super().__init__(f"report bound of {detail.cap} {detail.cap_kind} exceeded")
        self.detail = detail


def _age_label(created: datetime, now: datetime) -> str:
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
        if alert.status == "closed" and alert.disposition == "true_positive":
            row.true_positive += 1
        elif alert.status == "closed" and alert.disposition == "false_positive":
            row.false_positive += 1
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


async def case_report(
    *,
    alerts: AlertStore,
    graph: GraphPort,
    held: HeldRowStore,
    compute: ComputePort,
    investigation_id: str,
    reader: Principal,
    today: date,
    period_weeks: int = 12,
    show_held: bool = False,
) -> ReportFigures:
    now = datetime.now(UTC)
    visible = [row.alert for row in await queue(alerts, graph, investigation_id, reader)]
    by_week, by_age, outcomes, total = _alert_figures(
        visible, start=today - timedelta(weeks=period_weeks), now=now
    )
    held_figures = None
    if show_held:
        held_figures = HeldFigures(
            held=len(await held.list_authorized(investigation_id, reader, status="held")),
            released=len(await held.list_authorized(investigation_id, reader, status="released")),
            rejected=len(await held.list_authorized(investigation_id, reader, status="rejected")),
        )
    return ReportFigures(
        period_weeks=period_weeks,
        as_of=today,
        generated_at=now,
        alerts_total=total,
        alerts_by_week=by_week,
        open_by_age=by_age,
        outcomes=outcomes,
        held=held_figures,
        kyc=await _kyc_figures(graph, compute, reader, today),
    )


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
                 for label in ("open", "claimed", "true_positive", "false_positive")]  # fmt: skip
    if figures.held is not None:
        rows += [("held_rows", label, "", "", getattr(figures.held, label))
                 for label in ("held", "released", "rejected")]  # fmt: skip
    rows += [("kyc", label, "", "", getattr(figures.kyc, label))
             for label in ("customers", "verified", "unverified")]  # fmt: skip
    rows += [("kyc_band", c.label, "", "", c.value) for c in figures.kyc.by_band]
    return rows


__all__ = ["ReportLimitExceededError", "case_report", "feed_rows"]
