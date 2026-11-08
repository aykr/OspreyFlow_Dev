"""The *Alerts* panel's and the *Alert monitoring* board's own figures (`spec/06_DECISIONS.md`
ADR-146 decision 9; ADR-145 Amendment 4 decisions 8 and 9): open alerts by source and age, and the
team view (unassigned, mine, older than seven days, closed and closed as not of interest), by rule
group.

Hermetic: `reports._monitoring_figures` is fed the rows the reader's queue holds whole, as
`alert_report` feeds it. That the queue leaves a hidden alert out, so no figure moves for it, is
`test_monitoring_dashboard.py`'s `test_a_hidden_alert_changes_no_dashboard_figure` (real Postgres),
which compares the whole `monitoring` section and so holds these two sections too.

What a mistake would do, and the case that catches it:
- a closed alert counted as open, or an age band wrong —
  `test_open_by_source_counts_what_is_still_in_the_queue_by_group_and_age`;
- `mine` counting every claimed alert, not the reader's —
  `test_mine_is_the_readers_own_claims_only`;
- the team view's counts wrong —
  `test_the_team_view_counts_unassigned_older_closed_and_not_of_interest`;
- the feed leaving them out or carrying a person's id —
  `test_the_feed_carries_the_panel_sections_as_figures_only`;
- the drawing figures invented before promotions exist —
  `test_no_drawing_figures_are_served_before_promotions`;
- a band the report counts in that the schema refuses —
  `test_the_closed_age_bands_are_the_report_s_own`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.api import reports

from schemas.domain import Alert, AlertMode, QueuedAlert, ReportFigures

NOW = datetime.now(UTC)
START = (NOW - timedelta(weeks=12)).date()


def _row(kind: str, *, age: timedelta, status: str = "open", assignee: str | None = None,
         typology: str | None = None, disposition: str | None = None) -> QueuedAlert:  # fmt: skip
    created = NOW - age
    alert = Alert(
        id=f"a-{kind}-{age}-{status}-{assignee}",
        rule_id=f"{kind}:r",
        owner_id="raiser",
        mode=AlertMode.FULL,
        created_at=created,
        typology=typology,
        status=status,  # type: ignore[arg-type]
        assignee=assignee,
        disposition=disposition,  # type: ignore[arg-type]
        decided_at=created + timedelta(hours=1) if status == "closed" else None,
    )
    return QueuedAlert(alert=alert, summary="", kind=kind)  # type: ignore[arg-type]


_S = "structuring"
ROWS = [
    _row("typology", age=timedelta(hours=2), typology=_S),
    _row("typology", age=timedelta(days=3), typology=_S, status="claimed", assignee="me"),
    _row("typology", age=timedelta(days=10), typology=_S, status="claimed", assignee="other"),
    _row("typology", age=timedelta(days=2), typology=_S, status="closed",
         disposition="false_positive"),
    _row("hotlist", age=timedelta(days=40), status="closing", assignee="me"),
    _row("hotlist", age=timedelta(days=5), status="closed", disposition="no_further_action"),
    _row("monitor", age=timedelta(days=8), status="closed", disposition="true_positive"),
    _row("monitor", age=timedelta(days=9)),
]  # fmt: skip


def _figures(reader: str = "me") -> reports.MonitoringFigures:
    return reports._monitoring_figures(ROWS, start=START, now=NOW, reader_id=reader)


def test_open_by_source_counts_what_is_still_in_the_queue_by_group_and_age() -> None:
    rows = _figures().open_by_source
    got = sorted((c.label, c.typology, c.age, c.count) for c in rows if c.count)
    assert got == [
        ("hotlists", "", "over 30 days", 1),
        ("monitors", "", "7 to 30 days", 1),
        ("typology", "structuring", "1 to 7 days", 1),
        ("typology", "structuring", "7 to 30 days", 1),
        ("typology", "structuring", "under a day", 1),
    ]


def test_mine_is_the_readers_own_claims_only() -> None:
    mine = {(t.label, t.typology): t.mine for t in _figures("me").team}
    assert mine == {("typology", "structuring"): 1, ("hotlists", ""): 1, ("monitors", ""): 0}
    others = {(t.label, t.typology): t.mine for t in _figures("other").team}
    assert others == {("typology", "structuring"): 1, ("hotlists", ""): 0, ("monitors", ""): 0}


def test_the_team_view_counts_unassigned_older_closed_and_not_of_interest() -> None:
    team = {(t.label, t.typology): t for t in _figures().team}

    def counts(key: tuple[str, str]) -> tuple[int, int, int, int]:
        t = team[key]
        return (t.unassigned, t.older_than_week, t.closed, t.not_of_interest)

    assert counts(("typology", _S)) == (1, 1, 1, 1)
    assert counts(("hotlists", "")) == (0, 1, 1, 1)
    assert counts(("monitors", "")) == (1, 1, 1, 0)


def test_the_feed_carries_the_panel_sections_as_figures_only() -> None:
    figures = ReportFigures(period_weeks=12, as_of=NOW.date(), generated_at=NOW, alerts_total=0,
                            monitoring=_figures())  # fmt: skip
    rows = reports.feed_rows(figures)
    sections = {r[0] for r in rows}
    assert {"open_by_source", "team_unassigned", "team_mine", "team_older_than_week",
            "team_closed", "team_not_of_interest"} <= sections  # fmt: skip
    assert ("open_by_source", "hotlists:over 30 days", "", "", 1) in rows
    assert {r[3] for r in rows if r[0].startswith(("open_by_source", "team_"))} == {""}
    assert "me" not in {str(cell) for row in rows for cell in row}, "figures only: no person's id"
    assert all(isinstance(r[4], int) for r in rows)


def test_no_drawing_figures_are_served_before_promotions() -> None:
    """ADR-145 Amendment 4 decision 8's drawing figures wait for promotions (L3.4): the report
    serves none, so the Figures tab draws no Drawing panel, rather than a zero that says nothing
    was drawn."""
    figures = ReportFigures(period_weeks=12, as_of=NOW.date(), generated_at=NOW, alerts_total=0)
    assert figures.drawing is None


def test_the_closed_age_bands_are_the_report_s_own() -> None:
    """`AgeBand` is closed so the feed can carry nothing else in its place; it must name exactly the
    bands the report counts in, or a band would fail validation at the route."""
    from typing import get_args

    from schemas.domain import AgeBand

    assert get_args(AgeBand) == reports.AGE_LABELS
