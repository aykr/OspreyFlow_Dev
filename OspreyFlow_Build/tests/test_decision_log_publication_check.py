"""`tools/decision_log_publication_check.py` — its own docstring has the full reasoning for why
this gate exists and how it differs from `tools/product_tree_link_check.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools import decision_log_publication_check as gate
from tools.decision_log_publication_check import (
    ALLOWLIST_PATH,
    DECISIONS_PATH,
    find_duplicate_headings,
    find_violations,
)


def _load_allowlist() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        a, _, b = line.partition("\t")
        pairs.add((a, b))
    return pairs


def test_the_real_decision_log_has_no_new_product_adr_citing_a_process_adr() -> None:
    """Every violation in the live decision log is already known and allowlisted -- no new one
    has crept in unnoticed."""
    allowlisted = _load_allowlist()
    new_violations = [v for v in find_violations() if v not in allowlisted]
    assert new_violations == []


def test_the_checker_actually_flags_a_product_adr_citing_a_process_adr(tmp_path: Path) -> None:
    """Non-vacuous: plants a real PRODUCT-cites-PROCESS reference in an isolated fixture document
    and asserts the checker reports it — proving the pattern can fail, not only that it currently
    passes."""
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-006 — Entity resolution is a query-time projection, never a merge\n\n"
        "Some real architectural decision, citing ADR-034 for no good reason.\n\n"
        "---\n\n"
        "## ADR-034 — Publication and licence boundary\n\n"
        "The private, process-only decision this fixture plants a bad reference to.\n",
        encoding="utf-8",
    )

    violations = find_violations(decisions_path=fixture)

    assert violations == [("006", "034")]


def test_a_process_adr_may_cite_another_process_adr_without_violation(tmp_path: Path) -> None:
    """The gate only fires when a PRODUCT section cites a PROCESS one — two PROCESS ADRs citing
    each other is not a publication-boundary violation, since neither publishes."""
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-019 — Scenario A's exit criterion split\n\n"
        "Cites ADR-022, another process ADR.\n\n"
        "---\n\n"
        "## ADR-022 — Scenario B's exit criterion split\n\n"
        "Cites ADR-019 back.\n",
        encoding="utf-8",
    )

    assert find_violations(decisions_path=fixture) == []


# --- ADR-049's own classification, both directions ---------------------------
#
# `PROCESS_ADR_NUMBERS` gaining `"049"` (24 September 2026) needs a proof that exercises *that
# element*, not one the set's existing members would satisfy anyway — `CLAUDE.md` rule 15's second
# clause, and the lesson `06_DECISIONS.md` ADR-034 §B12 records from `licence_check.mjs`: a planted
# violation that any other branch already catches proves nothing about the branch under test. A
# fixture citing ADR-034 from ADR-006 (the case above) passes identically with or without `"049"`
# in the set. Both cases below fail if `"049"` is removed, and each fails for its own reason — one
# for the false positive the omission causes, one for the false negative.


def test_adr_049_is_process_so_its_own_process_citations_are_not_flagged(tmp_path: Path) -> None:
    """The real shape the live decision log produces, not an approximation of it: ADR-049's own
    section cites ADR-034 and ADR-042 by number, both PROCESS, and that is not a violation because
    ADR-049 does not publish either. With `"049"` absent from `PROCESS_ADR_NUMBERS` this is exactly
    the pair of false positives `make decision-log-publication-check` reported on 24 September
    2026."""
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-049 — The harness / packaging pipeline\n\n"
        "Cites ADR-034 §B7 for the artefact-hygiene assertions and ADR-042 for the alpha gate.\n\n"
        "---\n\n"
        "## ADR-034 — Publication and licence boundary\n\n"
        "The private, process-only record ADR-049 legitimately depends on.\n\n"
        "---\n\n"
        "## ADR-042 — The alpha gate\n\n"
        "Also private, also process.\n",
        encoding="utf-8",
    )

    assert find_violations(decisions_path=fixture) == []


def test_a_product_adr_citing_adr_049_is_flagged(tmp_path: Path) -> None:
    """The converse, which the test above alone does not prove: `"049"` is actually *in* the set,
    not merely absent from the violations because nothing looked. A PRODUCT record depending on
    ADR-049 is a real publication-boundary violation — ADR-049 stays private, so a published ADR
    resting on it dangles for every reader of the published artefact."""
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-006 — Entity resolution is a query-time projection, never a merge\n\n"
        "Leans on ADR-049's own packaging assertions, which is the mistake this case plants.\n\n"
        "---\n\n"
        "## ADR-049 — The harness / packaging pipeline\n\n"
        "The private, process-only record the section above should not depend on.\n",
        encoding="utf-8",
    )

    assert find_violations(decisions_path=fixture) == [("006", "049")]


def test_an_amendment_belongs_to_the_adr_its_heading_names_not_the_one_above_it(
    tmp_path: Path,
) -> None:
    """Amendments are appended where the log ends, so ADR-049's sat under ADR-055: read as ADR-055's
    text, ADR-049 naming itself was reported as ADR-055 citing a private ADR. An amendment is its
    own ADR's, whatever stands above it."""
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-055 — A product decision\n\nIts own text cites nothing private.\n\n"
        "### ADR-049, Amendment 2 (29 September 2026) — a process note\n\n"
        "This repairs what ADR-049 Amendment 1 began.\n",
        encoding="utf-8",
    )
    assert find_violations(fixture) == []


def test_an_amendment_to_a_product_adr_filed_under_a_process_one_is_still_checked(
    tmp_path: Path,
) -> None:
    """The other direction, which the old reading hid: a product ADR's amendment standing under a
    process ADR was skipped with it, so its citation of a private ADR went unseen."""
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-049 — A process decision\n\nIt may cite ADR-034.\n\n"
        "### ADR-052, Amendment 3 (29 September 2026) — a product change\n\n"
        "This depends on ADR-034, which is private.\n",
        encoding="utf-8",
    )
    assert find_violations(fixture) == [("052", "034")]


# --- a heading written twice (slice BL1b) ------------------------------------------------------
#
# `_sections` joins two sections of one number, so a block repeated by a union merge or a repeated
# commit was read as one longer section and nothing said so. The planted shape is the real one: a
# whole amendment block appended again after the log's end.


def test_the_real_decision_log_has_no_heading_written_twice_beyond_the_known_one() -> None:
    assert find_duplicate_headings() == []


def test_an_amendment_block_written_twice_is_reported(tmp_path: Path) -> None:
    block = (
        "### ADR-055, Amendment 10 (20 November 2026) — a planted amendment\n\n"
        "Status: accepted from a planted ruling.\n"
    )
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-055 — A product decision\n\nIts own text.\n\n" + block + "\n" + block,
        encoding="utf-8",
    )
    assert find_duplicate_headings(fixture) == [
        "ADR-055 Amendment 10 has 2 headings in 06_DECISIONS.md (a block written twice)"
    ]


def test_an_adr_heading_written_twice_is_reported(tmp_path: Path) -> None:
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-199 — A planted record — ACCEPTED\n\nText.\n\n---\n\n"
        "## ADR-199 — A planted record — ACCEPTED\n\nText.\n",
        encoding="utf-8",
    )
    assert find_duplicate_headings(fixture) == [
        "ADR-199 has 2 headings in 06_DECISIONS.md (a block written twice)"
    ]


def test_the_real_log_path_is_the_one_the_gate_reads() -> None:
    assert find_duplicate_headings(DECISIONS_PATH) == find_duplicate_headings()


# The gate `make decision-log-publication-check` runs is `main()`; the cases above reach the finder
# alone, so a `main()` that dropped the finding or its `return 1` would still pass them.


def test_main_returns_1_and_names_the_heading_when_a_block_is_written_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    block = "### ADR-055, Amendment 10 (20 November 2026) — a planted one\n\nStatus: planted.\n"
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-055 — A product decision\n\nText.\n\n" + block + "\n" + block, encoding="utf-8"
    )
    monkeypatch.setattr(gate, "DECISIONS_PATH", fixture)
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "headings written twice" in out
    assert "ADR-055 Amendment 10 has 2 headings" in out


def test_main_returns_0_for_a_log_with_each_block_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = tmp_path / "06_DECISIONS.md"
    fixture.write_text(
        "## ADR-055 — A product decision\n\nText.\n\n### ADR-055, Amendment 10 (a day)\n\nx\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "DECISIONS_PATH", fixture)
    assert gate.main() == 0
    assert "headings written twice" not in capsys.readouterr().out
