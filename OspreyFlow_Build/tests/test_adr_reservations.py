"""`tools/adr_reservations_check.py` (ADR-142 decision 5): every heading above the baseline in
`spec/06_DECISIONS.md` has a reservation row in `spec/ADR_RESERVATIONS.md`.

Rule 15: each planted violation is the shape a lane actually writes — a heading appended to the real
decision log, checked against the real reservations file — not a hand-made miniature.
"""

from __future__ import annotations

from tools.adr_reservations_check import (
    DECISIONS_PATH,
    RESERVATIONS_PATH,
    find_unreserved,
    parse_baseline,
)

DECISIONS = DECISIONS_PATH.read_text(encoding="utf-8")
RESERVATIONS = RESERVATIONS_PATH.read_text(encoding="utf-8")


def _appended(*headings: str) -> str:
    body = "".join(f"\n\n{h}\n\nStatus: accepted from a planted ruling.\n" for h in headings)
    return DECISIONS + body


def test_the_real_decision_log_has_no_unreserved_heading() -> None:
    assert find_unreserved(DECISIONS, RESERVATIONS) == []


def test_an_unreserved_adr_heading_is_reported() -> None:
    planted = _appended("## ADR-199 — A planted record — ACCEPTED (design)")
    assert find_unreserved(planted, RESERVATIONS) == [
        "ADR-199 has a heading but no reservation row"
    ]


def test_an_unreserved_amendment_to_an_old_adr_is_reported() -> None:
    last = parse_baseline(RESERVATIONS).last_amendment[110]
    planted = _appended(f"### ADR-110, Amendment {last + 40} (7 November 2026) — planted")
    assert find_unreserved(planted, RESERVATIONS) == [
        f"ADR-110 Amendment {last + 40} has a heading but no reservation row"
    ]


def test_an_amendment_to_an_adr_with_none_at_the_baseline_is_reported() -> None:
    baseline = parse_baseline(RESERVATIONS)
    never_amended = next(n for n in range(1, baseline.last_adr) if n not in baseline.last_amendment)
    planted = _appended(f"### ADR-{never_amended:03d}, Amendment 1 (7 November 2026) — planted")
    assert find_unreserved(planted, RESERVATIONS) == [
        f"ADR-{never_amended:03d} Amendment 1 has a heading but no reservation row"
    ]


def test_an_amendment_heading_in_another_form_is_reported() -> None:
    planted = _appended("### Amendment 2 (7 November 2026): a planted amendment without its ADR")
    [problem] = find_unreserved(planted, RESERVATIONS)
    assert "not in the form '### ADR-n, Amendment m'" in problem


def test_a_reserved_heading_passes() -> None:
    reservations = RESERVATIONS + (
        "\n| ADR-199 | A planted record | studio | 2026-11-07 | reserved |\n"
    )
    planted = _appended("## ADR-199 — A planted record — ACCEPTED (design)")
    assert find_unreserved(planted, reservations) == []


def test_a_number_reserved_twice_is_reported() -> None:
    row = "| ADR-199 | A planted record | {lane} | 2026-11-07 | reserved |\n"
    reservations = RESERVATIONS + "\n" + row.format(lane="studio") + row.format(lane="glass")
    assert find_unreserved(DECISIONS, reservations) == ["ADR-199 is reserved 2 times"]
