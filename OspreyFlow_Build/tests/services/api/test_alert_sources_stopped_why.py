"""*What raises alerts* says why a hotlist or watch stopped (v0.6.0 #14; CARRIES 245; ADR-044
Amendment 1): `alert_sources.inventory` carries each stopped hotlist's and watch's `stopped_why`,
the stores' own fixed words (`watch_status.STOPPED_WHY`), as Hotlists and Watches say beside it on
the same tab. Never while live, and never for a rule, whose retirement records no reason (the
orchestrator's ruling, 15 November 2026). The rows listed are the reader's own watches
(`list_authorized`), so the words reach only their owner. Red first: the plant in
`process/lanes/rules/v060-i14-stopped-why/plants.py`."""

from __future__ import annotations

from datetime import UTC, date, datetime

from schemas.domain import Hotlist, Monitor, RuleSentence, SentenceRuleParams, TypologyRule
from services.api import alert_sources
from services.api.watch_status import STOPPED_WHY

NOW = datetime(2026, 11, 15, 9, 0, tzinfo=UTC)


def _hotlist(hid: str, status: str, reason: str | None) -> Hotlist:
    return Hotlist(
        id=hid, identifier="+447700900310", owner_id="me", review_date=date(2027, 1, 31),
        created_at=NOW, status=status, status_detail=reason,
        stopped_why=STOPPED_WHY[reason] if reason else None,
    )  # fmt: skip


def _monitor(mid: str, status: str, reason: str | None) -> Monitor:
    return Monitor(
        id=mid, pattern_id="p", owner_id="me", created_at=NOW, status=status,
        status_detail=reason, stopped_why=STOPPED_WHY[reason] if reason else None,
    )  # fmt: skip


def _rule(rid: str, status: str) -> TypologyRule:
    return TypologyRule(
        id=rid, name=rid, investigation_id="case", owner_id="me", created_at=NOW, status=status,
        trigger="post_commit", dataset_id="ds-1",
        params=SentenceRuleParams(
            pattern_id="p", sentence=RuleSentence.model_validate({"subject": "Person"})
        ),
    )  # fmt: skip


def _rows() -> dict[str, alert_sources.AlertSource]:
    rows = alert_sources.inventory(
        [_rule("retired", "retired"), _rule("live", "active")],
        [_hotlist("h-stopped", "stopped", "revoked"), _hotlist("h-live", "active", None)],
        [_monitor("m-stopped", "stopped", "pattern_gone"), _monitor("m-live", "active", None)],
        {}, [], {},
    )  # fmt: skip
    return {r.id: r for r in rows}


def test_a_stopped_hotlist_and_watch_say_why_in_the_owner_s_words() -> None:
    rows = _rows()
    assert rows["h-stopped"].state == "stopped"
    assert rows["h-stopped"].stopped_why == STOPPED_WHY["revoked"]
    assert rows["m-stopped"].state == "stopped"
    assert rows["m-stopped"].stopped_why == STOPPED_WHY["pattern_gone"]


def test_a_live_one_and_a_retired_rule_say_none() -> None:
    rows = _rows()
    assert rows["h-live"].stopped_why is None and rows["m-live"].stopped_why is None
    assert rows["retired"].state == "stopped" and rows["retired"].stopped_why is None
    assert rows["live"].stopped_why is None


def test_the_words_are_the_fixed_sentences_never_an_id() -> None:
    """Rule 7: only `STOPPED_WHY`'s own words reach the wire; the stored reason's key does not."""
    for row in _rows().values():
        if row.stopped_why is not None:
            assert row.stopped_why in STOPPED_WHY.values()
            assert row.stopped_why not in STOPPED_WHY
