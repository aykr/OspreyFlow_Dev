"""`scripts/decision_log_publication_check.py` — its own docstring has the full reasoning for why
this gate exists and how it differs from `scripts/product_tree_link_check.py`.
"""

from __future__ import annotations

from pathlib import Path

from scripts.decision_log_publication_check import ALLOWLIST_PATH, find_violations


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
