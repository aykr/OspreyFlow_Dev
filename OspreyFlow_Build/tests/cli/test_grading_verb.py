"""`ospreyflow grading change` (`06_DECISIONS.md` ADR-143 decision 11 and Amendment 6; the owner's ruling
C13): a thin verb over `scripts/grading_change.py`, run in a one-shot from the Conduit's image, then,
after a change and only then, the setting, the render and the start.

What a mistake would do, and the case that catches it (rule 12):
- the change run beside a running Conduit (a drawing during it, or before the restart, in the old
  scheme) — `test_the_change_is_refused_while_the_conduit_runs_unless_told_to_stop_it`;
- the setting left in the old scheme after a change, or changed without one —
  `test_a_change_stops_the_conduit_then_sets_the_scheme_renders_and_starts_it`,
  `test_a_refused_change_leaves_the_setting_and_starts_the_conduit_again`;
- a run stopped part way started again in the old scheme —
  `test_a_change_stopped_part_way_leaves_the_conduit_stopped_and_the_setting_as_it_was`;
- the owner's `osprey.yaml` dumped again, losing its comments — `test_the_setting_is_edited_in_place`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ospreyflow.grading import with_grading_scheme

from .conftest import Rig

SCRIPT = "scripts.grading_change"


def _compose(rig: Rig) -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(rig.deployment / "deployment.env"),
        "-f", str(rig.deployment / "compose.yaml"),
    ]  # fmt: skip


def _ready(rig: Rig, tmp_path: Path, *, running: bool) -> Path:
    rig.install_deployment()
    rig.ps_output = '{"Service": "api", "State": "running"}' if running else ""
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text("from: 5x5x5\nto: 3x5x2\n", encoding="utf-8")
    config = rig.product / "osprey.yaml"
    config.write_text("# the owner's own note\nprofile: local-lite  # kept\n", encoding="utf-8")
    return mapping


def _script_call(rig: Rig) -> list[str]:
    (call,) = rig.runner.with_word(SCRIPT)
    return call.argv


def test_the_dry_run_runs_in_a_one_shot_beside_a_running_conduit_and_changes_nothing(
    rig: Rig, tmp_path: Path
) -> None:
    mapping = _ready(rig, tmp_path, running=True)
    assert rig("grading", "change", "--to", "3x5x2", "--mapping", str(mapping), "--dry-run") == 0
    argv = _script_call(rig)
    assert argv[: len(_compose(rig)) + 5] == [
        *_compose(rig), "run", "--rm", "--no-deps", "--entrypoint", "python"
    ]  # fmt: skip
    assert f"{mapping.resolve()}:/grading/mapping.yaml:ro" in argv
    assert argv[argv.index("api") :][:3] == ["api", "-m", SCRIPT]
    assert "--dry-run" in argv and argv[-2] == "--changed-by" and argv[-1].startswith("cli:")
    # Nothing stopped, rendered or started; the setting untouched.
    assert [c.argv for c in rig.runner.calls] == [argv]
    assert "grading" not in (rig.product / "osprey.yaml").read_text(encoding="utf-8")


def test_the_change_is_refused_while_the_conduit_runs_unless_told_to_stop_it(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = _ready(rig, tmp_path, running=True)
    code = rig("grading", "change", "--to", "3x5x2", "--mapping", str(mapping), "--confirm", "t")
    assert code != 0
    assert "--stop-api" in capsys.readouterr().err
    assert rig.runner.calls == []


def test_a_change_stops_the_conduit_then_sets_the_scheme_renders_and_starts_it(
    rig: Rig, tmp_path: Path
) -> None:
    mapping = _ready(rig, tmp_path, running=True)
    assert rig("grading", "change", "--to", "3x5x2", "--mapping", str(mapping),
               "--confirm", "tok", "--stop-api") == 0  # fmt: skip
    argvs = [c.argv for c in rig.runner.calls]
    assert argvs[0] == [*_compose(rig), "stop", "api"]
    assert SCRIPT in argvs[1] and argvs[1][argvs[1].index("--confirm") + 1] == "tok"
    assert "harness.apply" in argvs[2] and "--reapply" in argvs[2]
    assert argvs[3] == [*_compose(rig), "up", "-d", "--wait", "api"]
    assert len(argvs) == 4
    config = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    assert config == (
        "# the owner's own note\nprofile: local-lite  # kept\ngrading:\n  scheme: 3x5x2\n"
    )


def test_a_change_with_the_conduit_already_stopped_starts_it_in_the_new_scheme(
    rig: Rig, tmp_path: Path
) -> None:
    mapping = _ready(rig, tmp_path, running=False)
    assert rig("grading", "change", "--to", "3x5x2", "--mapping", str(mapping),
               "--confirm", "tok") == 0  # fmt: skip
    argvs = [c.argv for c in rig.runner.calls]
    assert SCRIPT in argvs[0] and "harness.apply" in argvs[1]
    assert argvs[2] == [*_compose(rig), "up", "-d", "--wait", "api"]


def test_a_refused_change_leaves_the_setting_and_starts_the_conduit_again(
    rig: Rig, tmp_path: Path
) -> None:
    mapping = _ready(rig, tmp_path, running=True)
    rig.runner.fail[SCRIPT] = 1
    assert rig("grading", "change", "--to", "3x5x2", "--mapping", str(mapping),
               "--confirm", "tok", "--stop-api") == 1  # fmt: skip
    argvs = [c.argv for c in rig.runner.calls]
    assert argvs[-1] == [*_compose(rig), "up", "-d", "--wait", "api"]
    assert not any("harness.apply" in a for a in argvs)
    assert "grading" not in (rig.product / "osprey.yaml").read_text(encoding="utf-8")


def test_a_change_stopped_part_way_leaves_the_conduit_stopped_and_the_setting_as_it_was(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = _ready(rig, tmp_path, running=True)
    rig.runner.fail[SCRIPT] = 2
    assert rig("grading", "change", "--to", "3x5x2", "--mapping", str(mapping),
               "--confirm", "tok", "--stop-api") == 2  # fmt: skip
    argvs = [c.argv for c in rig.runner.calls]
    assert argvs[-1] == _script_call(rig)  # nothing after: the Conduit stays stopped
    assert "left stopped" in capsys.readouterr().out
    assert "grading" not in (rig.product / "osprey.yaml").read_text(encoding="utf-8")


def test_a_scheme_file_is_mounted_and_kept_beside_osprey_yaml(rig: Rig, tmp_path: Path) -> None:
    mapping = _ready(rig, tmp_path, running=False)
    scheme = tmp_path / "force.yaml"
    scheme.write_text("scheme: force-4x3\n", encoding="utf-8")
    assert rig("grading", "change", "--to", str(scheme), "--mapping", str(mapping),
               "--confirm", "tok") == 0  # fmt: skip
    argv = _script_call(rig)
    assert f"{scheme.resolve()}:/grading/scheme.yaml:ro" in argv
    assert argv[argv.index("--to") + 1] == "/grading/scheme.yaml"
    kept = rig.product / "grading-scheme.yaml"
    assert kept.read_text(encoding="utf-8") == "scheme: force-4x3\n"
    assert "  scheme: grading-scheme.yaml\n" in (rig.product / "osprey.yaml").read_text("utf-8")


def test_a_missing_mapping_is_refused_before_anything_runs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ready(rig, tmp_path, running=False)
    absent = tmp_path / "absent.yaml"
    assert rig("grading", "change", "--to", "3x5x2", "--mapping", str(absent), "--dry-run") != 0
    assert "no mapping file" in capsys.readouterr().err and rig.runner.calls == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "grading:\n  scheme: 3x5x2\n"),
        ("profile: small\n", "profile: small\ngrading:\n  scheme: 3x5x2\n"),
        ("profile: small", "profile: small\ngrading:\n  scheme: 3x5x2\n"),
        (
            "grading:  # the scheme\n  scheme: 5x5x5   # chosen at install\nmap: {}\n",
            "grading:  # the scheme\n  scheme: 3x5x2   # chosen at install\nmap: {}\n",
        ),
        ("grading:\nmap: {}\n", "grading:\n  scheme: 3x5x2\nmap: {}\n"),
        (
            "map:\n  scheme: keep\ngrading:\n  scheme: 5x5x5\n",
            "map:\n  scheme: keep\ngrading:\n  scheme: 3x5x2\n",
        ),
    ],
)
def test_the_setting_is_edited_in_place(text: str, expected: str) -> None:
    assert with_grading_scheme(text, "3x5x2") == expected
