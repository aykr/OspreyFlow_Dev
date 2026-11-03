"""`ospreyflow install --mode small --config install.yaml`, run on a server of your own with a
`server:` section and no `--cloud` (`06_DECISIONS.md` ADR-114 Amendment 33 decision 1, unit 4).

Driven through `ospreyflow.main.main` with the fakes of `conftest.py`: a runner that records each
step, and probes standing in for the machine (each of which can be told to refuse, rule 15).

What a mistake would do, and the case that catches it:
- the self-contained Small still refused as it was before this amendment, or installed as Lite —
  `test_small_on_a_server_with_its_own_certificate_installs_without_cloud`;
- a refusal that names only the two ways that existed before (`--cloud`, the first boot's managed
  services) — `test_small_with_no_server_cloud_or_external_is_refused_naming_all_three`;
- `server:` beside `--cloud` built in the cloud anyway —
  `test_server_and_the_cloud_flag_together_are_refused`;
- the install going ahead past a refused certificate or a machine that cannot run it —
  `test_a_refused_certificate_stops_the_install_before_anything_runs`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .conftest import Rig

SERVER_ANSWERS = {
    "mode": "small",
    "server": {
        "address": "https://osprey.example.internal",
        "certificate": "/etc/ospreyflow/tls/osprey.crt",
        "key": "/etc/ospreyflow/tls/osprey.key",
        "ca": "/etc/ospreyflow/tls/org-root.pem",
        "ingest": "/srv/ospreyflow/ingest",
    },
    "admin_email": "ops@example.internal",
    "components": {"dashboards": False},
}


def _answers(tmp_path: Path, answers: dict[str, object] = SERVER_ANSWERS) -> Path:
    path = tmp_path / "install.yaml"
    path.write_text(yaml.safe_dump(answers), encoding="utf-8")
    return path


def test_small_on_a_server_with_its_own_certificate_installs_without_cloud(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = _answers(tmp_path)
    assert rig("install", "--mode", "small", "--config", str(answers), "--force") == 0
    config = rig.config()
    assert config["profile"] == "small"
    assert "external" not in config
    network = config["network"]
    assert isinstance(network, dict)
    assert network["public_origin"] == "https://osprey.example.internal"
    assert network["tls"] == {
        "certificate": "/etc/ospreyflow/tls/osprey.crt",
        "key": "/etc/ospreyflow/tls/osprey.key",
        "ca": "/etc/ospreyflow/tls/org-root.pem",
    }
    # The server's own checks ran — the certificate among them — not Lite's nor the cloud's.
    asked = rig.probes.asked
    assert ("certificate", "/etc/ospreyflow/tls/osprey.crt") in asked
    assert ("port-everywhere", 443) in asked
    python = str(rig.product / ".venv" / "bin" / "python")
    apply, identity, admin = rig.runner.argvs()
    assert apply == [python, "-m", "harness.apply", "--build"]  # no demo accounts on a server
    assert identity == [python, "-m", "harness.register_sign_in", "--profile", "small",
                        "--no-demo-accounts"]  # fmt: skip
    assert admin[:3] == [python, "-m", "harness.first_admin"]
    assert admin[admin.index("--email") + 1] == "ops@example.internal"
    assert "--code-file" not in admin  # the code is printed once on this terminal
    out = capsys.readouterr().out
    assert "https://osprey.example.internal" in out
    # What the organisation's DNS must point at this server (dashboards off: two names).
    assert "osprey.example.internal, id.osprey.example.internal" in out
    assert "bi.osprey.example.internal" not in out
    assert not any("tofu" in argv for argv in rig.runner.argvs())


def test_small_with_no_server_cloud_or_external_is_refused_naming_all_three(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = _answers(tmp_path, {"mode": "small"})
    assert rig("install", "--mode", "small", "--config", str(answers), "--yes") == 1
    said = capsys.readouterr().err
    assert "server:" in said and "--cloud aws" in said and "external:" in said
    assert "first boot" in said
    assert rig.runner.calls == []


def test_server_and_the_cloud_flag_together_are_refused(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = _answers(tmp_path)
    assert rig("install", "--mode", "small", "--config", str(answers), "--cloud", "aws") == 1
    said = capsys.readouterr().err
    assert "--cloud" in said and "server:" in said and "not both" in said
    assert rig.runner.calls == []


def test_a_refused_certificate_stops_the_install_before_anything_runs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.probes.certificate_says = (1, "refused: the key does not match the certificate\n")
    answers = _answers(tmp_path)
    before = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    assert rig("install", "--mode", "small", "--config", str(answers), "--force") == 1
    out = capsys.readouterr().out
    assert "✘" in out and "does not match" in out and "Nothing was installed" in out
    assert rig.runner.calls == []
    assert (rig.product / "osprey.yaml").read_text(encoding="utf-8") == before
