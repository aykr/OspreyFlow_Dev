"""ArcadeDB's restore step (`deploy/backups/restore-graph.sh` and its check, ADR-148 Amendment 7):
run in ArcadeDB's own image against real databases and a real set's zip (ArcadeDB's own backup),
never a stand-in, since the refusals that matter are ArcadeDB's (the orchestrator's review of
7916044, must-fix 1). The live database is replaced only once the restored one is proven; any
failure leaves it as it was, refused in words. Docker: the test server (local_docker_guard).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from harness import cloud_platform_backups as backups
from harness.render import load_config, service_images

HERE = Path(__file__).resolve().parent / "arcadedb"


def _image() -> str:
    from tools.cp_policy_check import FIXTURES

    found = [i.image for i in service_images(load_config(FIXTURES / "development.yaml")) if i.service == "arcadedb"]
    assert found
    return str(found[0])


def _run(tmp_path: Path, script: str) -> dict[str, str]:
    src = tmp_path / "src"
    src.mkdir()
    for name in ("restore-graph.sh", "CheckDatabase.java"):
        shutil.copy(backups.RESTORE_GRAPH_SOURCES / name, src / name)
    for helper in HERE.iterdir():
        shutil.copy(helper, src / helper.name)
    work = tmp_path / "work"
    work.mkdir()
    work.chmod(0o777)  # the image's own user writes there
    done = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{src}:/src:ro", "-v", f"{work}:/work", "--entrypoint", "sh",
         _image(), f"/src/{script}"],
        capture_output=True, text=True, timeout=900, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    lines = [line for line in done.stdout.splitlines() if " exit=" in line]
    return {line.split(" ", 1)[0]: line.split(" ", 1)[1] for line in lines}


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _run(tmp_path_factory.mktemp("restore-graph"), "scenarios.sh")


def test_the_set_replaces_the_live_database_and_the_old_one_goes(scenarios: dict[str, str]) -> None:
    line = scenarios["restored"]
    assert line.startswith("exit=0 live=set 300 restoring=no before=no"), line
    assert "checked and put in place" in line


@pytest.mark.parametrize(
    ("case", "words"),
    [
        ("truncated-zip", "ArcadeDB's restore of the set's zip failed"),
        ("check-refuses", "the restored database is not the set's"),
        ("no-zip", "no set's zip at"),
    ],
)
def test_a_restore_failing_before_the_swap_leaves_the_live_database_as_it_was(
    scenarios: dict[str, str], case: str, words: str
) -> None:
    line = scenarios[case]
    assert line.startswith("exit=1 live=live 25 restoring=no before=no"), line
    assert "restore-graph refused" in line and words in line and "was not touched" in line


def test_a_restore_stopped_between_its_renames_is_never_overwritten(scenarios: dict[str, str]) -> None:
    """A `.before` left by a restore stopped between its two renames holds the old data: refused,
    the live folder and it both kept, until an operator has looked (the recovery runbook)."""
    line = scenarios["before-left"]
    assert line.startswith("exit=1 live=live 25 restoring=no before=yes"), line
    assert "a restore stopped between its renames" in line


def test_a_killed_runs_restoring_folder_is_cleared_and_the_restore_goes_on(scenarios: dict[str, str]) -> None:
    assert scenarios["restoring-left"].startswith("exit=0 live=set 300 restoring=no before=no")


def test_a_deployment_whose_database_was_lost_gets_the_set(scenarios: dict[str, str]) -> None:
    line = scenarios["live-lost"]
    assert line.startswith("exit=0 live=set 300 restoring=no before=no"), line
    assert "there was no live database" in line
    line = scenarios["no-zip-no-live"]
    assert line.startswith("exit=1 live=none restoring=no before=no"), line
    assert "there was no live database" in line and "not touched" not in line


def test_a_failed_put_in_puts_the_live_database_back_and_says_where_the_restored_one_is(
    scenarios: dict[str, str],
) -> None:
    """The restored copy's rename into place refused (a full or read-only claim): the live one is
    renamed back, and the words say so, and where the restored copy is."""
    line = scenarios["put-in-fails"]
    assert line.startswith("exit=1 live=live 25 restoring=yes before=no"), line
    assert "the live one was put back" in line and "not touched" not in line


def test_a_failed_put_back_says_where_each_copy_is_and_never_that_it_was_put_back(
    scenarios: dict[str, str],
) -> None:
    line = scenarios["put-back-fails"]
    assert line.startswith("exit=1 live=none restoring=yes before=yes"), line
    assert "nor the live one put back" in line and "the live data is at" in line
    assert "was put back" not in line and "not touched" not in line


def test_an_old_copy_that_cannot_be_removed_is_said_plainly(scenarios: dict[str, str]) -> None:
    line = scenarios["old-not-removed"]
    assert line.startswith("exit=1 live=set 300 restoring=no before=yes"), line
    assert "could not be removed" in line


def test_the_check_refuses_every_damage_arcadedb_itself_opens_with_a_warning(tmp_path: Path) -> None:
    """ArcadeDB opens a short bucket, a missing one or an empty schema with a warning (measured,
    `gates/p9_restore_graph_probe.log`): the check holds the folder to the zip's own index first."""
    found = _run(tmp_path, "check_scenarios.sh")
    assert "setup" not in found, found["setup"]
    assert found["restored"].startswith("exit=0 | opens:"), found["restored"]
    for case, words in {"bucket-cut-mid-page": "bytes, the zip's", "bucket-cut-to-one-page": "bytes, the zip's",
                        "schema-empty": "schema.json is 0 bytes", "bucket-missing": "not restored",
                        "no-database": "not restored",
                        "stray-short-page-file": "is not a whole number of pages",
                        "empty-zip": "the set's zip holds no file"}.items():  # fmt: skip
        assert found[case].startswith("exit=1 | does not open:"), (case, found[case])
        assert words in found[case], (case, found[case])
