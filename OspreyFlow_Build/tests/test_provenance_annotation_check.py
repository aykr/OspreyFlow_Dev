"""The provenance-annotation gate — `tools/provenance_annotation_check.py`'s own docstring has
the full reasoning, including why `06_DECISIONS.md` is deliberately out of its scope."""

from __future__ import annotations

import sys
from pathlib import Path

from tools.layout import CORE
from tools.layout import REPO as REPO_ROOT

sys.path.insert(0, str(CORE))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from tools.provenance_annotation_check import (  # noqa: E402
    ALLOWLIST_PATH,
    _load_allowlist,
    find_violations,
)
from tools.route_coverage_check import APACHE_DOC_PATHS  # noqa: E402


def test_no_new_provenance_annotations_beyond_the_allowlist() -> None:
    violations = find_violations()
    allowlisted = _load_allowlist()
    new_violations = [
        (path, lineno, matched)
        for path, lineno, matched in violations
        if (path, matched) not in allowlisted
    ]
    assert new_violations == [], (
        f"new build-calendar annotation(s) in an Apache-scoped document: {new_violations}. "
        f"Rewrite it, or add it to {ALLOWLIST_PATH.relative_to(REPO_ROOT)} if it is a genuine "
        f"false positive."
    )


def test_the_checker_actually_flags_a_planted_annotation(tmp_path: Path) -> None:
    """Non-vacuous, the same discipline this repository's other allowlist-based gates are already
    held to: a deliberately planted annotation, proving the pattern can fail, not only that it
    currently passes. A real, isolated fixture file — not this repository's own real docs — so
    this test's own result never depends on what the live allowlist happens to contain."""
    clean_doc = tmp_path / "clean.md"
    clean_doc.write_text(
        "# A clean document\n\nStates a rule and its reasoning with no build-calendar coordinate "
        "anywhere in this file.\n",
        encoding="utf-8",
    )
    dirty_doc = tmp_path / "dirty.md"
    dirty_doc.write_text(
        "# A document with a real violation\n\nFixed during Phase 6a of the build.\n",
        encoding="utf-8",
    )

    clean_violations = find_violations((clean_doc,))
    assert clean_violations == []

    dirty_violations = find_violations((dirty_doc,))
    assert len(dirty_violations) == 1
    (path, lineno, matched) = dirty_violations[0]
    assert path == str(dirty_doc)
    assert lineno == 3
    assert matched == "Phase 6a"


def test_a_round_number_and_a_found_while_phrase_are_both_caught(tmp_path: Path) -> None:
    """Two of the five real shapes this gate targets, planted together, since a regex built to
    catch one can silently miss the others — checked directly rather than assumed from the first
    case alone."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "A gap in this section, found while building the renderer (round 09).\n",
        encoding="utf-8",
    )
    violations = find_violations((doc,))
    matched_texts = {matched for _, _, matched in violations}
    assert "found while" in matched_texts
    assert "round 09" in matched_texts


def test_a_bare_use_of_stage_or_round_with_no_number_is_not_flagged(tmp_path: Path) -> None:
    """The pattern requires a number to follow — an unrelated use of "stage" or "round" as an
    ordinary English word (a deployment stage, a round of testing) with no digit attached is not a
    build-calendar coordinate and must not be flagged."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "Each deployment stage runs its own preflight round before promotion.\n",
        encoding="utf-8",
    )
    assert find_violations((doc,)) == []


def test_a_capitalised_round_at_a_sentence_start_is_caught(tmp_path: Path) -> None:
    """Round 14c: `spec/03_CONDUIT_MIDDLEWARE.md` opened a sentence with "Round 09: ..." and the
    pattern, matching lowercase `round` only, missed it — the class this test pins, not just the
    one instance. Checked against `Phase`/`Stage`/`Checkpoint` too, so a future lowercase-at-
    sentence-start variant of any of the four is caught the same way."""
    cases = (
        ("Round 09: the two actions are unreachable from the harness image.\n", "Round 09"),
        ("phase 3 work is not yet scheduled.\n", "phase 3"),
        ("stage 2 of the pipeline was skipped.\n", "stage 2"),
        ("checkpoint 4 recorded the same finding.\n", "checkpoint 4"),
    )
    for i, (text, expected) in enumerate(cases):
        doc = tmp_path / f"doc{i}.md"
        doc.write_text(text, encoding="utf-8")
        violations = find_violations((doc,))
        matched_texts = {matched for _, _, matched in violations}
        assert expected in matched_texts, (
            f"{expected!r} in {text!r} was not caught — the pattern is still case-sensitive"
        )


def test_apache_doc_paths_is_the_same_set_route_coverage_check_uses() -> None:
    """The two gates share one definition of "Apache-scoped" (`scripts/provenance_annotation_
    check.py`'s own docstring: imported, not redeclared) — this pins that they cannot silently
    diverge."""
    from tools.provenance_annotation_check import find_violations as _find

    assert _find.__defaults__[0] == APACHE_DOC_PATHS


def test_06_decisions_is_deliberately_out_of_scope() -> None:
    """`06_DECISIONS.md`'s own dated ADR status lines are not provenance annotations — checked
    directly that the gate's own default scope excludes it, not assumed from the docstring alone."""
    assert not any(p.name == "06_DECISIONS.md" for p in APACHE_DOC_PATHS)
