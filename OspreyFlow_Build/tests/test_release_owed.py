"""No release while a live test is owed (the owner, 18 November 2026).

A slice the v0.6.2 slice line merged with its live step off leaves the live test files its change reaches owed
(`OspreyFlow_Build/scripts/slice_line/owed.py`). Both release paths refuse while any is owed:
`OspreyFlow_Build/tools/release_local.py` before it builds anything, and
`OspreyFlow_Build/scripts/publish_user_repo_update.sh` before it exports the product. The line's own records sit in
`OSPREY_SLICE_HOME`, a temporary folder here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools import release_local

BUILD = Path(__file__).resolve().parents[1]
OWED = "tests/services/api/test_route_rights.py"


@pytest.fixture
def line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OSPREY_SLICE_HOME", str(tmp_path))
    (tmp_path / "records/S1").mkdir(parents=True)
    return tmp_path


def _owe(line: Path) -> None:
    (line / "records/S1/merged.json").write_text(
        json.dumps({"slice": "S1", "merge": "a" * 40, "at": "2026-11-18T09:00:00Z",
                    "live_step": {"live_step": "off", "not_run": [OWED]}})
    )  # fmt: skip


def test_release_local_refuses_before_building_anything_while_a_live_test_is_owed(
    line: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _owe(line)
    ran: list[object] = []
    monkeypatch.setattr(release_local, "_run", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(release_local, "build_and_scan", lambda *a, **k: ran.append(a) or [])
    assert release_local.main(["--dry-run", "--tag", "v9.9.9", "--out", str(line / "out")]) == 1
    assert ran == []
    err = capsys.readouterr().err
    assert "live tests are owed" in err and OWED in err


def test_release_local_goes_on_once_the_owed_test_has_run(line: Path) -> None:
    _owe(line)
    assert release_local.owed_refusal() is not None
    (line / "live-paid.json").write_text(json.dumps({OWED: {"at": "2026-11-18T10:00:00Z"}}))
    assert release_local.owed_refusal() is None


def test_release_local_refuses_when_the_line_s_records_cannot_be_read(line: Path) -> None:
    (line / "records/S1/merged.json").write_text("{not json")
    refusal = release_local.owed_refusal()
    assert refusal is not None and "cannot be read" in refusal


def test_the_publish_script_checks_what_is_owed_before_it_exports_the_product() -> None:
    text = (BUILD / "scripts/publish_user_repo_update.sh").read_text()
    check = re.search(r'python3 "\$ROOT/ospreyflow/OspreyFlow_Build/scripts/slice_line/owed\.py" check \\\n\s*\|\| \{[^}]*exit 1; \}', text)
    export = text.find("publish-user-repo COMMIT=HEAD")
    assert check is not None and 0 < check.start() < export
