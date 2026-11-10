"""ADR-114 Amendment 39's staged refresh, its carries (CARRIES, the reviews of 10 November 2026).

The move into place:
- what must restart outlives a run that dies after the files moved —
  `test_a_run_that_dies_after_the_move_still_restarts_what_changed_next_time`;
- a file renamed into place keeps the old one's owner — `test_a_file_moved_into_place_keeps_its_owner`.

The staged pass:
- a stage left behind is never taken for a deployment —
  `test_a_stage_left_behind_is_never_a_deployment`;
- two refreshes of one deployment never share a stage — `test_a_second_refresh_at_once_is_refused`;
- a symlinked file is written through its link — `test_a_symlinked_file_is_written_through_its_link`;
- a required value Compose would take from the shell or an `export` line is not refused —
  `test_a_value_from_the_shell_or_an_export_line_is_held`.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from scripts import refresh
from tests.test_refresh import Recorder, Registrar
from tests.test_refresh_before_the_gateway import (  # noqa: F401 - the fixture, by name
    _after_the_gateway_database,
    _checkout,
    deployment,
)


def _restarts(run: Recorder) -> list[str]:
    return [c[-1] for c in run.calls if "restart" in c]


def test_a_run_that_dies_after_the_move_still_restarts_what_changed_next_time(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gateway's routing table changed and was moved into place; the run then died (its build
    failed) before the gateway was restarted. The next `start --build` finds the files current, so
    without a record it restarts nothing and the gateway keeps the old table."""
    _after_the_gateway_database(deployment)
    monkeypatch.setattr(refresh.store_volumes, "move", lambda *a, **k: None)
    with pytest.raises(refresh.RefreshFailed):
        refresh.refresh(_checkout(deployment), run=Recorder(fail_on="build"), register=Registrar())
    again = Recorder()
    refresh.refresh(_checkout(deployment), run=again, register=Registrar())
    assert "litellm" in _restarts(again)
    once_more = Recorder()
    refresh.refresh(_checkout(deployment), run=once_more, register=Registrar())
    assert "litellm" not in _restarts(once_more)  # done, so not again
    assert not (deployment / "state" / refresh.PENDING_RESTARTS).exists()


def test_a_file_moved_into_place_keeps_its_owner(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under sudo a rename leaves the file root's: each file renamed into place first takes the
    owner of the one it replaces."""
    _after_the_gateway_database(deployment)
    owners = {p.name: (p.stat().st_uid, p.stat().st_gid) for p in deployment.iterdir() if p.is_file()}
    given: dict[str, tuple[int, int]] = {}
    monkeypatch.setattr(refresh.os, "geteuid", lambda: 0)
    monkeypatch.setattr(refresh.os, "chown", lambda p, u, g: given.update({Path(p).name: (u, g)}))
    refresh.files_up_to_date(_checkout(deployment))
    assert given, "nothing was given an owner"
    assert {name: owners[name] for name in given} == given


def test_a_stage_left_behind_is_never_a_deployment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refresh killed outright leaves `.<name>.refresh-staging/compose.yaml`; it must not count as
    a second rendered deployment ("no single deployment")."""
    generated = tmp_path / "deploy" / "generated"
    for folder in ("lab", ".lab.refresh-staging"):
        (generated / folder).mkdir(parents=True)
        (generated / folder / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "osprey.yaml").write_text("deployment:\n  name: other\n", encoding="utf-8")
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE, raising=False)
    assert refresh._find_deployment_dir(tmp_path) == generated / "lab"


def test_a_second_refresh_at_once_is_refused(deployment: Path) -> None:
    _after_the_gateway_database(deployment)
    lock = deployment.parent / f".{deployment.name}.refresh-lock"
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another refresh of it, under way
        with pytest.raises(refresh.RefreshFailed, match="another refresh of this deployment"):
            refresh.files_up_to_date(_checkout(deployment))
    refresh.files_up_to_date(_checkout(deployment))  # released: it goes ahead


def test_a_symlinked_file_is_written_through_its_link(deployment: Path) -> None:
    """An operator keeps `compose.yaml` elsewhere and links it in: the pass reads it through the link
    (it was silently left out of the stage) and brings it up to date there, and the link stays a
    link. (`litellm.yaml`, which a service mounts, is written in place and so through a link too.)"""
    _after_the_gateway_database(deployment)
    elsewhere = deployment.parent / "compose-kept-elsewhere.yaml"
    (deployment / "compose.yaml").rename(elsewhere)
    (deployment / "compose.yaml").symlink_to(elsewhere)
    before = elsewhere.read_text(encoding="utf-8")
    refresh.files_up_to_date(_checkout(deployment))
    assert (deployment / "compose.yaml").is_symlink()
    assert elsewhere.read_text(encoding="utf-8") != before  # the mounts it gained, written there
    assert "map-settings" in elsewhere.read_text(encoding="utf-8")


@pytest.mark.parametrize("where", ["the shell", "an export line"])
def test_a_value_from_the_shell_or_an_export_line_is_held(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """Compose takes a required value from the shell before the env file, and reads `export NAME=v`
    in it; so must the check, or it refuses what Compose would run."""
    _after_the_gateway_database(deployment)
    env = deployment / "deployment.env"
    lines = env.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith("OSPREY_LITELLM_SALT_SECRET=")]
    if where == "an export line":
        kept.append("export OSPREY_LITELLM_SALT_SECRET=held-salt")
    else:
        monkeypatch.setenv("OSPREY_LITELLM_SALT_SECRET", "held-salt")
    env.write_text("\n".join(kept) + "\n", encoding="utf-8")
    assert refresh._unset_required(deployment) == []
    refresh.files_up_to_date(_checkout(deployment))
    assert os.environ.get("OSPREY_LITELLM_SALT_SECRET", "held-salt") == "held-salt"
