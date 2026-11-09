"""*What raises alerts* (`06_DECISIONS.md` ADR-146 decision 5): every rule and watch in one list,
with who made it, its dataset, its owner, whether it is live, its expiry, when it last fired, its
alerts in the last 30 days and the share closed as not of interest; and, beside each, the alerts
of it suppressed today (Amendment 1).

**What it lists (rule 3).** The case's rules (read by every member, ADR-109 ruling 3), and the
reader's own hotlists and watched patterns (a watch is its owner's: another's hotlist names an
identifier its owner may not have shared). **Every count is the reader's queue's** (rule 7): the
alerts of each rule or watch are counted from the queue as the reader may see it, all or nothing,
so an alert any of whose evidence is hidden from them is not counted, and nothing here is counted
that the queue would not show them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from schemas.domain import (
    AlertSource,
    Hotlist,
    Monitor,
    QueuedAlert,
    SavedPattern,
    SuppressedAlert,
    TypologyRule,
)

from .alert_queue import suppressed_today

_DAYS = 30


class _Held:
    __slots__ = ("closed", "last", "noi", "recent", "suppressed")

    def __init__(self) -> None:
        self.last: datetime | None = None
        self.recent = 0
        self.closed = 0
        self.noi = 0
        self.suppressed: list[SuppressedAlert] = []


def _counts(rows: Sequence[QueuedAlert]) -> dict[str, _Held]:
    since = datetime.now(UTC) - timedelta(days=_DAYS)
    by: dict[str, _Held] = defaultdict(_Held)
    for row in rows:
        alert = row.alert
        held = by[alert.rule_id]
        if held.last is None or alert.created_at > held.last:
            held.last = alert.created_at
        if alert.created_at >= since:
            held.recent += 1
        if alert.status == "closed" and alert.disposition is not None:
            held.closed += 1
            if alert.disposition == "false_positive":
                held.noi += 1
        if suppressed_today(alert) and alert.suppressed_until is not None:
            held.suppressed.append(
                SuppressedAlert(
                    alert_id=alert.id, until=alert.suppressed_until,
                    reason=alert.suppress_reason or "", by=alert.suppressed_by or "",
                )  # fmt: skip
            )
    return by


def _with_counts(source: AlertSource, counts: dict[str, _Held]) -> AlertSource:
    held = counts.get(source.rule_id)
    if held is None:
        return source
    return source.model_copy(
        update={
            "last_fired_at": held.last,
            "alerts_30_days": held.recent,
            "not_of_interest": (held.noi / held.closed) if held.closed else None,
            "suppressed": held.suppressed,
        }
    )


def inventory(
    rules: Sequence[TypologyRule],
    hotlists: Sequence[Hotlist],
    monitors: Sequence[Monitor],
    patterns: dict[str, SavedPattern],
    queue: Sequence[QueuedAlert],
    team_names: dict[str, str],
) -> list[AlertSource]:
    """The rows, each counted from `queue` (the reader's own, every status)."""
    from .sentence_rules import routed_team_of

    counts = _counts(queue)
    rows: list[AlertSource] = []
    for rule in rules:
        team = routed_team_of(rule)
        rows.append(AlertSource(
            id=rule.id, rule_id=f"typology:{rule.id}", name=rule.name, source="rule", kind="rule",
            maker=rule.owner_id, dataset_id=rule.dataset_id,
            owner=team_names.get(team, team) if team else rule.owner_id,
            state="live" if rule.status == "active" else "stopped" if rule.status == "retired"
            else "draft",
        ))  # fmt: skip
    for hotlist in hotlists:
        rows.append(AlertSource(
            id=hotlist.id, rule_id=f"hotlist:{hotlist.id}",
            name=f"Hotlist {hotlist.identifier_typed or hotlist.identifier}", source="watch",
            kind="hotlist", maker=hotlist.owner_id, dataset_id=hotlist.dataset_id,
            owner=hotlist.owner_id, state="live" if hotlist.status == "active" else "stopped",
            expires_on=hotlist.review_date,
        ))  # fmt: skip
    for monitor in monitors:
        saved = patterns.get(monitor.pattern_id)
        rows.append(AlertSource(
            id=monitor.id, rule_id=f"monitor:{monitor.id}",
            name=f"Watched pattern {saved.name}" if saved else "Watched pattern",
            source="watch", kind="watched_pattern", maker=monitor.owner_id,
            dataset_id=monitor.dataset_id, owner=monitor.owner_id,
            state="live" if monitor.status == "active" else "stopped",
        ))  # fmt: skip
    return [_with_counts(r, counts) for r in rows]


__all__ = ["inventory"]
