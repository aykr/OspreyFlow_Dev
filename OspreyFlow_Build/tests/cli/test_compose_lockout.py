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


@pytest.mark.parametrize(
    "argv", [["stop"], ["start"], ["logs"], ["status"], ["uninstall", "--yes"]],
    ids=["stop", "start", "logs", "status", "uninstall"],
)  # fmt: skip
def test_each_verb_names_the_missing_value_and_what_to_do(
    rig: Rig, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    rig.install_deployment()
    (rig.deployment / "compose.yaml").write_text(LOCKED, encoding="utf-8")
    assert rig(*argv) != 0
    said = capsys.readouterr()
    words = said.out + said.err
    assert "OSPREY_POSTGRES_PASSWORD" in words and "ospreyflow apply" in words, words
    assert (
        "docker stop $(docker ps -q --filter label=com.docker.compose.project=osprey-upg)" in words
    )
    assert "Is Docker running" not in words
    assert rig.runner.argvs() == []  # Compose was never asked
    assert not any("compose" in argv for argv in rig.captured)


def test_switch_stops_another_locked_out_deployment_by_its_label(
    rig: Rig, tmp_path: Path
) -> None:
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
