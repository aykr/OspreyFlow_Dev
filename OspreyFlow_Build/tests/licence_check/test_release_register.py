"""No release while the licence register is unsettled (PL11 item 6; the owner's rulings of 21
November 2026).

The gate in `make ci` allows an `unconfirmed` row and a name `HELD_FOR_OWNER`, so the build stays
green while the owner decides. A release is the point where it must not: `tools/release_local.py`
refuses before it builds anything, in words that name each row and each held name, the way it
already refuses while a live test is owed (`tests/test_release_owed.py`).

The refusal comes after the owed-test and GitHub-green refusals, which are cheaper to explain to a
person and are what the existing cases there already assert; each of those cases is unchanged.

**The folders this test walks:** none. It reads the register by name.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from tools import licence_register, release_local

COMMIT = "555c6b78ea45e6005aa39730b25610a797aabd34"


@pytest.fixture
def clear_before_it(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Owed tests and GitHub both clear, so that the register's refusal is the one that shows;
    anything the release would build is recorded, not run."""
    ran: list[object] = []
    monkeypatch.setattr(release_local, "owed_refusal", lambda: None)
    monkeypatch.setattr(release_local, "green_refusal", lambda sha: None)
    monkeypatch.setattr(release_local, "git_sha", lambda: COMMIT)
    monkeypatch.setattr(release_local, "_run", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(release_local, "build_and_scan", lambda *a, **k: ran.append(a) or [])
    return ran


def _settled(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The real register with every unconfirmed row made confirmed, as the real rows are shaped."""
    settled = copy.deepcopy(rows)
    for row in settled:
        if row["status"] == "unconfirmed":
            row.update(status="confirmed", licence="MIT", where_read="read", must_read=None)
    return settled


def test_a_release_is_refused_while_a_row_is_unconfirmed_naming_it_and_what_to_read() -> None:
    rows = copy.deepcopy(licence_register.load_register())
    target = next(r for r in rows if r["status"] == "confirmed" and r["kind"] == "weight")
    target.update(
        status="unconfirmed", licence=None, where_read=None, must_read="the model card at rev 1"
    )
    refusal = release_local.register_refusal(rows=rows, held=frozenset())
    assert refusal is not None
    assert (
        f"unconfirmed: {target['id']} {target['name']!r} — read: the model card at rev 1" in refusal
    )


def test_a_release_is_refused_while_a_name_is_held_for_the_owner_naming_it() -> None:
    refusal = release_local.register_refusal(
        rows=_settled(licence_register.load_register()), held=frozenset({"example/held-image"})
    )
    assert refusal is not None
    assert "held for the owner: 'example/held-image'" in refusal
    assert "unconfirmed" not in refusal


def test_a_release_names_every_row_and_every_held_name_at_once() -> None:
    rows = copy.deepcopy(licence_register.load_register())
    for row in [r for r in rows if r["status"] == "confirmed"][:2]:
        row.update(status="unconfirmed", licence=None, where_read=None, must_read="somewhere")
    refusal = release_local.register_refusal(rows=rows, held=frozenset({"a/one", "b/two"}))
    assert refusal is not None
    assert refusal.count("unconfirmed:") == 2 + sum(
        1 for r in licence_register.load_register() if r["status"] == "unconfirmed"
    )
    assert "'a/one'" in refusal and "'b/two'" in refusal


def test_a_release_goes_on_when_nothing_is_unconfirmed_or_held() -> None:
    assert (
        release_local.register_refusal(
            rows=_settled(licence_register.load_register()), held=frozenset()
        )
        is None
    )


def test_a_conditional_row_does_not_stop_a_release() -> None:
    """GDS Transport is conditional on the owner's ruling: it is settled, not owed."""
    rows = licence_register.load_register()
    assert any(r["status"] == "conditional" for r in rows)
    settled = _settled(rows)
    assert any(r["status"] == "conditional" for r in settled)
    assert release_local.register_refusal(rows=settled, held=frozenset()) is None


def test_release_local_refuses_before_building_anything_naming_what_is_unsettled_today(
    clear_before_it: list[object], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real register and the real hold, as they stand: the release is refused, and the refusal
    names each unconfirmed row and the held image, so this is also what tells the owner what is
    left."""
    assert release_local.main(["--dry-run", "--tag", "v9.9.9", "--out", str(tmp_path / "out")]) == 1
    assert clear_before_it == []
    err = capsys.readouterr().err
    assert "the licence register" in err and "not settled" in err
    for row in licence_register.load_register():
        if row["status"] == "unconfirmed":
            assert f"unconfirmed: {row['id']} {row['name']!r}" in err
    for name in licence_register.HELD_FOR_OWNER:
        assert f"held for the owner: {name!r}" in err


def test_release_local_goes_past_the_register_once_it_is_settled(
    clear_before_it: list[object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(release_local, "register_refusal", lambda **_: None)
    monkeypatch.setattr(release_local, "lock", lambda out: None)
    release_local.main(["--dry-run", "--tag", "v9.9.9", "--out", str(tmp_path / "out")])
    assert clear_before_it, "with the register settled the release reaches its first build step"
    assert "not settled" not in capsys.readouterr().err


def test_the_owed_and_green_refusals_still_come_first(
    clear_before_it: list[object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(release_local, "owed_refusal", lambda: "the line owes a test")
    assert release_local.main(["--dry-run", "--tag", "v9.9.9", "--out", str(tmp_path / "out")]) == 1
    err = capsys.readouterr().err
    assert "live tests are owed" in err and "not settled" not in err
