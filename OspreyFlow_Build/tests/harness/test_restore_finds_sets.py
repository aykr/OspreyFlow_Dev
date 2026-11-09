"""`ospreyflow restore` finds a deployment's sets (ADR-114 Amendment 37 decision 3): in
`<backups folder>/<deployment name>/` first, and still in the places sets were written before —
the checkout's `backups/`, a named deployment's `~/.ospreyflow/deployments/<name>/backups`
(ADR-138), and the top of a server's backups folder (Amendment 33) — each listed and restorable
with the one command that moves it.

What a mistake would do, and the case that catches it:
- a set in an old place lost to the operator once the default moves —
  `test_a_set_in_an_old_place_is_listed_and_restorable_with_the_move_command`;
- an old copy restored over the one in the deployment's folder —
  `test_restore_looks_in_the_deployments_folder_first`;
- another deployment's set offered for this one (ADR-138's rule) —
  `test_another_deployments_set_in_a_shared_old_place_is_not_offered`.

The filesystem is real (`tmp_path`); only the checkout and the home folder are stand-ins, so a
regression cannot write into the real checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from harness import backup, restore


def _set(folder: Path, name: str) -> Path:
    """A set as `harness.backup` leaves one: a stamped folder holding its manifest."""
    folder.mkdir(parents=True, exist_ok=True)
    made = folder / name
    made.mkdir()
    (made / "manifest.json").write_text(json.dumps({"files": [], "empty": []}))
    return made


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    home = tmp_path / "home"
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(backup, "REPO_ROOT", checkout)
    folder = tmp_path / "backups"
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump({
        "deployment": {"name": "alpha"},
        "components": {"storage": {"backups": str(folder)}},
    }))  # fmt: skip
    generated = tmp_path / "generated"
    (generated / "alpha").mkdir(parents=True)
    (generated / "alpha" / "compose.yaml").write_text("services: {}\n")
    return {"home": home, "checkout": checkout, "folder": folder, "config": config,
            "generated": generated}  # fmt: skip


def _main(rig: dict[str, Path], *argv: str) -> int:
    return restore.main(
        [*argv, "--config", str(rig["config"]), "--generated-root", str(rig["generated"])]
    )


@pytest.fixture
def restored(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The set `run_restore` was given; it stops there, as the stores are the live test's."""
    seen: list[Path] = []

    def run_restore(**kwargs: object) -> object:
        seen.append(Path(str(kwargs["directory"])))
        raise restore.RestoreRefused("stopped by the test", "")

    monkeypatch.setattr(restore, "run_restore", run_restore)
    return seen


def test_restore_looks_in_the_deployments_folder_first(
    rig: dict[str, Path], restored: list[Path]
) -> None:
    name = "20261109T100000Z-alpha-abc1234"
    _set(rig["checkout"] / "backups", name)
    new = _set(rig["folder"] / "alpha", name)
    assert _main(rig, name) == 2
    assert restored == [new]


def test_a_set_in_an_old_place_is_listed_and_restorable_with_the_move_command(
    rig: dict[str, Path], restored: list[Path], capsys: pytest.CaptureFixture[str]
) -> None:
    in_checkout = _set(rig["checkout"] / "backups", "20261101T000000Z-alpha-abc1234")
    in_named = _set(rig["home"] / ".ospreyflow" / "deployments" / "alpha" / "backups",
                    "20261102T000000Z-alpha-abc1234")  # fmt: skip
    at_top = _set(rig["folder"], "20261103T000000Z-alpha-abc1234")
    current = _set(rig["folder"] / "alpha", "20261104T000000Z-alpha-abc1234")
    destination = rig["folder"] / "alpha"

    # Listed, every one, newest first; each old one with the command that moves it.
    assert _main(rig) == 0
    listing = capsys.readouterr().out
    lines = listing.splitlines()
    order = [next(i for i, line in enumerate(lines) if s.name in line)
             for s in (current, at_top, in_named, in_checkout)]  # fmt: skip
    assert order == sorted(order), listing
    for old in (in_checkout, in_named, at_top):
        assert f"mv {old} {destination}/" in listing, listing
    assert f"mv {current}" not in listing

    # Restorable by its name, and said where it is and how to move it.
    for old in (in_checkout, in_named, at_top):
        assert _main(rig, old.name) == 2
        assert restored[-1] == old
        assert f"mv {old} {destination}/" in capsys.readouterr().out
    # By its path as well.
    assert _main(rig, str(in_checkout)) == 2
    assert restored[-1] == in_checkout
    assert all(s.exists() for s in (in_checkout, in_named, at_top, current))


def test_another_deployments_set_in_a_shared_old_place_is_not_offered(
    rig: dict[str, Path], restored: list[Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """The checkout's `backups/` and the top of a shared folder held every deployment's sets; only
    this one's are offered (by the name each set carries), and a name not found says where it
    looked."""
    other = _set(rig["checkout"] / "backups", "20261101T000000Z-beta-abc1234")
    # A failed backup's set is never a set (`harness.backup` names it `<set>.incomplete`).
    _set(rig["folder"] / "alpha", "20261103T000000Z-alpha-abc1234.incomplete")
    _set(rig["folder"], "20261102T000000Z-local-lite-abc1234")
    assert _main(rig) == 0
    listing = capsys.readouterr().out
    assert "beta" not in listing and "local-lite" not in listing and "incomplete" not in listing
    assert _main(rig, other.name) == 2
    assert restored == []
    said = capsys.readouterr().err
    assert other.name in said and str(rig["folder"] / "alpha") in said
