"""`ospreyflow uninstall` (ADR-114 Amendment 3 decision 4): it says exactly what it removes, asks
unless told, and keeps the stored data when asked to.

What a mistake would do, and the case that catches it:
- the data volumes deleted without the person agreeing —
  `test_it_asks_unless_yes_and_a_no_removes_nothing`;
- `--keep-data` still deleting the volumes, or the default keeping them —
  `test_volumes_go_unless_keep_data`;
- a vague prompt — `test_the_prompt_says_what_is_removed_and_what_is_never_touched`.
"""

from __future__ import annotations

from .conftest import Rig


def _compose(rig: Rig) -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(rig.deployment / "deployment.env"),
        "-f", str(rig.deployment / "compose.yaml"),
    ]  # fmt: skip


def test_it_asks_unless_yes_and_a_no_removes_nothing(rig: Rig) -> None:
    rig.install_deployment()
    rig.replies = ["n"]
    assert rig("uninstall") == 1
    assert len(rig.questions) == 1
    assert rig.runner.calls == []
    rig.replies = ["y"]
    assert rig("uninstall") == 0
    assert rig.runner.argvs() == [[*_compose(rig), "down", "-v"]]
    rig.questions.clear()
    rig.runner.calls.clear()
    assert rig("uninstall", "--yes") == 0
    assert rig.questions == []
    assert rig.runner.argvs() == [[*_compose(rig), "down", "-v"]]


def test_volumes_go_unless_keep_data(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("uninstall", "--yes", "--keep-data") == 0
    assert rig.runner.argvs() == [[*_compose(rig), "down"]]


def test_the_prompt_says_what_is_removed_and_what_is_never_touched(rig: Rig) -> None:
    rig.install_deployment()
    rig.replies = ["n"]
    rig("uninstall")
    wipe = rig.questions[0]
    assert "containers" in wipe and "data" in wipe
    for kept in ("checkout", "osprey.yaml", "folders"):
        assert kept in wipe
    rig.questions.clear()
    rig.replies = ["n"]
    rig("uninstall", "--keep-data")
    kept_prompt = rig.questions[0]
    assert "containers" in kept_prompt and "kept" in kept_prompt
