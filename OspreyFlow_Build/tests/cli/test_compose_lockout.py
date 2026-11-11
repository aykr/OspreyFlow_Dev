"""The command on a deployment whose compose file names a required value `deployment.env` does not
hold (CARRIES, the v0.5.0 upgrade rehearsal, 10 November 2026: once refresh had written such a file,
`stop` failed with Compose's own error, and the only way out found was copying the backup set's
compose file back). Every verb acting on the deployment now refuses before Compose is asked, naming
the value, the way out (`ospreyflow apply`, which renders the file again) and how to stop the
containers meanwhile; `status` says so rather than "Is Docker running?"; and `switch` stops another
deployment in that state by its label (the lane review of the carries, item 12).
- `test_each_verb_names_the_missing_value_and_what_to_do`
- `test_switch_stops_another_locked_out_deployment_by_its_label`
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.cli.conftest import Rig
from tests.cli.test_lifecycle import _other_deployment

LOCKED = (
    "name: osprey-upg\nservices:\n  postgres:\n    environment:\n"
    "      POSTGRES_PASSWORD: ${OSPREY_POSTGRES_PASSWORD:?set in the deployment env file}\n"
)


VERBS = {
    "stop": ["stop"],
    "start": ["start"],
    "logs": ["logs"],
    "status": ["status"],
    "uninstall": ["uninstall", "--yes"],
    # The orchestrator's review of c5209b1, item 6: the draft named these, untested, and the
    # harness-delegating verbs reached Compose (in their child) unguarded. `start --build` is not
    # here: it hands to refresh, which refuses such a file in its own words
    # (`test_refusal_words_reach_the_operator.py`).
    "map list": ["map", "list"],
    "grading change": ["grading", "change", "--to", "3x5x2", "--mapping", "MAPPING", "--dry-run"],
    "models": ["models"],
    "models key": ["models", "key", "gemini"],
    "backup": ["backup"],
    "restore": ["restore", "set-1"],
    "update": ["update", "--yes"],
    "demo add": ["demo", "add", "pid"],
    "repair-sign-in": ["repair-sign-in"],
}


@pytest.mark.parametrize("argv", list(VERBS.values()), ids=list(VERBS))
def test_each_verb_names_the_missing_value_and_what_to_do(
    rig: Rig, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    rig.install_deployment()
    (rig.deployment / "compose.yaml").write_text(LOCKED, encoding="utf-8")
    mapping = rig.deployment.parent / "mapping.yaml"  # the verb's own checks pass, to reach Compose
    mapping.write_text("{}\n", encoding="utf-8")
    argv = [str(mapping) if a == "MAPPING" else a for a in argv]
    assert rig(*argv) != 0
    said = capsys.readouterr()
    words = said.out + said.err
    assert "OSPREY_POSTGRES_PASSWORD" in words and "ospreyflow apply" in words, words
    assert (
        "docker ps -q --filter label=com.docker.compose.project=osprey-upg | xargs -r docker stop"
        in words
    )
    assert "Is Docker running" not in words
    assert rig.runner.argvs() == []  # Compose was never asked
    assert not any("compose" in argv for argv in rig.captured)


def test_switch_stops_another_locked_out_deployment_by_its_label(rig: Rig, tmp_path: Path) -> None:
    rig.install_deployment()
    other = _other_deployment(tmp_path / "second", "osprey-govuk")
    (other / "compose.yaml").write_text(LOCKED.replace("osprey-upg", "osprey-govuk"), "utf-8")
    config = str(other / "compose.yaml")
    row = {"Name": "osprey-govuk", "Status": "running(16)", "ConfigFiles": config}
    rig.responses["ls"] = [(0, json.dumps([row]))]
    rig.responses["ps"] = [(0, "c0ffee1\nc0ffee2\n")]
    assert rig("switch") == 0
    assert ["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=osprey-govuk"] in (
        rig.captured
    )
    assert rig.runner.argvs()[0] == ["docker", "stop", "c0ffee1", "c0ffee2"]


def test_start_build_refuses_a_value_the_shell_sets_empty(
    rig: Rig, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refresh's own check reads deployment.env alone (Am 39 decision 2), so a value the shell sets
    empty passed it, and Compose's own refusal at the build was then hidden by the redactor (my own
    lane review of the round, item 5). The command refuses that case before refresh runs."""
    rig.install_deployment()
    (rig.deployment / "compose.yaml").write_text(LOCKED, encoding="utf-8")
    (rig.deployment / "deployment.env").write_text("OSPREY_POSTGRES_PASSWORD=held\n", "utf-8")
    monkeypatch.setenv("OSPREY_POSTGRES_PASSWORD", "")
    assert rig("start", "--build") != 0
    said = capsys.readouterr()
    assert "OSPREY_POSTGRES_PASSWORD, which this shell sets empty" in said.err
    assert rig.runner.argvs() == []


def test_start_build_leaves_a_value_deployment_env_lacks_to_refresh(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the shell's case: a value deployment.env lacks is refresh's to refuse, in its words."""
    rig.install_deployment()
    (rig.deployment / "compose.yaml").write_text(LOCKED, encoding="utf-8")
    monkeypatch.delenv("OSPREY_POSTGRES_PASSWORD", raising=False)
    rig("start", "--build")
    assert any("scripts.refresh" in argv for argv in rig.runner.argvs())


@pytest.mark.parametrize(
    "argv",
    [
        ["update", "--check"],
        ["update", "--make-bundle", "b.tar"],
        ["update", "--make-bundle=b.tar"],
    ],
)
def test_an_update_that_asks_no_compose_is_not_refused(rig: Rig, argv: list[str]) -> None:
    rig.install_deployment()
    (rig.deployment / "compose.yaml").write_text(LOCKED, encoding="utf-8")
    rig(*argv)
    assert any("harness.update" in a for a in rig.runner.argvs())
