"""The code's own version file is well formed (ADR-114 Amendment 47 point 5): `OspreyFlow_Core/VERSION` is one line,
a release (v0.5.2) or the release the code is heading to (v0.5.2-dev). A malformed file is never shown as the
version (`tests/harness/test_code_version.py`), so without this check a bad cut would pass unseen. Run by CI's test
job; shown red with planted files (`process/lanes/platform-b/v052-codeversion/red-first.txt`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.release import VERSION_FILE, version_file_problem

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"


@pytest.mark.parametrize("text", ["0.5.2", "v0.5", "v0.5.2-rc1", "v0.5.2\nv0.5.3", ""])
def test_a_malformed_version_file_is_flagged(tmp_path: Path, text: str) -> None:
    (tmp_path / VERSION_FILE).write_text(text)
    assert version_file_problem(tmp_path) is not None


def test_the_repositorys_own_version_file_is_well_formed() -> None:
    """The gate on the committed file: a release or the release the code is heading to, one line."""
    assert version_file_problem(CORE) is None, version_file_problem(CORE)
