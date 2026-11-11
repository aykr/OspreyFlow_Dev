"""`ospreyflow stop` on a deployment whose compose file names a required value `deployment.env` does
not hold (CARRIES, the v0.5.0 upgrade rehearsal, 10 November 2026: once refresh had written such a
file, `stop` failed with Compose's own error, and the only way out found was copying the backup
set's compose file back). It now refuses before Compose is asked, naming the value, where to find
it, and how to stop the containers meanwhile.
- `test_stop_names_the_missing_value_and_what_to_do`
"""

from __future__ import annotations

import pytest

from tests.cli.conftest import Rig


def test_stop_names_the_missing_value_and_what_to_do(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.install_deployment()
    (rig.deployment / "compose.yaml").write_text(
        "name: osprey-upg\nservices:\n  postgres:\n    environment:\n"
        "      POSTGRES_PASSWORD: ${OSPREY_POSTGRES_PASSWORD:?set in the deployment env file}\n",
        encoding="utf-8",
    )
    assert rig("stop") != 0
    said = capsys.readouterr()
    words = said.out + said.err
    assert "OSPREY_POSTGRES_PASSWORD" in words and "backup set" in words, words
    assert (
        "docker stop $(docker ps -q --filter label=com.docker.compose.project=osprey-upg)" in words
    )
    assert rig.runner.argvs() == []  # Compose was never asked
