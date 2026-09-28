"""`licence-check`'s third leg — round 14a (Trigger A), `process/07_BUILD_PLAN.md`'s own close-step
addition: this project's own `LICENSE`/`NOTICE` are checked, not only third-party dependencies'.

`scripts.packaging_gate.check_license_and_notice` already existed and was already unit-tested
against fabricated text for a *bundle's* own copy — what was missing was wiring the same
comparison to this repository's real root files, which is what `find_own_licence_violations` does
and this file proves. Each case below points `find_own_licence_violations` at a temporary
directory holding a planted defect, never at this repository's real `LICENSE`/`NOTICE`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from licence_check import find_own_licence_violations  # noqa: E402

_REAL_LICENSE = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
_REAL_NOTICE = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")


def test_this_repositorys_own_files_pass() -> None:
    """The real, current state — a green result the round's other tests below don't otherwise
    prove, since they only ever plant defects."""
    assert find_own_licence_violations(REPO_ROOT) == []


def test_a_missing_license_file_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "NOTICE").write_text(_REAL_NOTICE, encoding="utf-8")
    violations = find_own_licence_violations(tmp_path)
    assert violations == ["LICENSE is missing"]


def test_a_truncated_license_file_is_flagged(tmp_path: Path) -> None:
    """Not a hand-written fake string — the real reference text with its own last line removed,
    the shape a real accidental truncation would take."""
    truncated = "\n".join(_REAL_LICENSE.splitlines()[:-1])
    (tmp_path / "LICENSE").write_text(truncated, encoding="utf-8")
    (tmp_path / "NOTICE").write_text(_REAL_NOTICE, encoding="utf-8")
    violations = find_own_licence_violations(tmp_path)
    assert violations == ["LICENSE does not match the reference Apache-2.0 text"]


def test_a_missing_notice_file_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(_REAL_LICENSE, encoding="utf-8")
    violations = find_own_licence_violations(tmp_path)
    assert violations == ["NOTICE is missing"]


def test_a_notice_missing_the_holder_string_is_flagged(tmp_path: Path) -> None:
    """The real shape: this project's own NOTICE, with the one line naming the holder deleted —
    not a fabricated NOTICE that happens to lack the string for an unrelated reason."""
    without_holder = "\n".join(
        line for line in _REAL_NOTICE.splitlines() if "OspreyFlow Authors" not in line
    )
    (tmp_path / "LICENSE").write_text(_REAL_LICENSE, encoding="utf-8")
    (tmp_path / "NOTICE").write_text(without_holder, encoding="utf-8")
    violations = find_own_licence_violations(tmp_path)
    assert violations == ["NOTICE does not name 'The OspreyFlow Authors'"]
