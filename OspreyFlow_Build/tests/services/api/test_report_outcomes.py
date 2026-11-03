"""The Reports view's Outcomes table (ADR-111; build order step 18c): where each typology's
alerts of the period stand. Found at the 3 November rehearsal (D12): the viewer's Figures had the
columns Open, Claimed, True and False only, and an alert closed as Referred, as a Duplicate or with
No further action (ADR-133 Amendment 5's closing reasons), or taken back with no outcome, was
counted as **open**.

Pure: `_alert_figures` over alerts already read as their reader (the access filter is the store's
and the referent check's, `test_reports.py`'s live cases). What a mistake would do, and the case
that catches it: a closed alert counted as open, or a closing reason with no figure of its own:
`test_every_closing_reason_has_its_own_figure_and_none_is_open`."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from services.api.reports import _alert_figures

from conduit_common.identity import new_id
from schemas.domain import CLOSING_REASONS, Alert, AlertMode

ALERT_DISPOSITIONS = tuple(CLOSING_REASONS)


def _alert(status: str, disposition: str | None = None) -> Alert:
    return Alert(
        id=new_id(), rule_id="sentence:r1", owner_id="deployer", mode=AlertMode.FULL,
        referent_node_ids=["n"], investigation_id="c", dataset_id="d",
        created_at=datetime.now(UTC) - timedelta(days=1), typology="sentence", words="w",
        status=status, disposition=disposition,  # type: ignore[arg-type]
    )  # fmt: skip


def test_every_closing_reason_has_its_own_figure_and_none_is_open() -> None:
    alerts = [
        _alert("open"),
        _alert("claimed"),
        *(_alert("closed", d) for d in ALERT_DISPOSITIONS),
        _alert("closed", None),
    ]
    _, _, outcomes, total = _alert_figures(alerts, start=date.today() - timedelta(days=30),
                                           now=datetime.now(UTC))  # fmt: skip
    assert total == len(alerts)
    (row,) = outcomes
    assert (row.open, row.claimed) == (1, 1)
    for disposition in ALERT_DISPOSITIONS:
        assert getattr(row, disposition) == 1, disposition
    assert row.closed == 1, "taken back with no outcome: closed, not open"
    counted = row.open + row.claimed + row.closed + sum(getattr(row, d) for d in ALERT_DISPOSITIONS)
    assert counted == len(alerts)
