"""`ospreyflow install --mode small --cloud aws|azure` on the operator's machine (ADR-114
Amendment 10 points 1, 3 and 4): plan, apply only on confirmation, wait for the name and the server,
then the first administrator's code shown once and deleted from the secret store.

OpenTofu, the cloud CLIs, DNS and the server are stood in for: the commands are recorded and their
answers queued, refusals included — a secret not there yet answers as the real CLI does, non-zero.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml
from ospreyflow import cloud

from .conftest import Rig

ADDRESS = "203.0.113.7"
AWS_OUTPUTS = {"address": ADDRESS, "domain": "osprey.example.org", "region": "eu-west-2",
               "first_admin_secret": "arn:aws:secretsmanager:eu-west-2:1:secret:first-admin"}  # fmt: skip


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []
    monkeypatch.setattr(cloud, "_sleep", lambda _: None)
    monkeypatch.setattr(cloud, "_answers", lambda url: asked.append(url) or True)
    monkeypatch.setattr(cloud, "_resolve", lambda name: {ADDRESS})
    return asked


def _module(rig: Rig, provider: str = "aws") -> None:
    (rig.product / "deploy" / "opentofu" / "small" / provider).mkdir(parents=True)


def _answers(tmp_path: Path, provider: str = "aws", **cloud_extra: str) -> Path:
    path = tmp_path / "answers.yaml"
    path.write_text(yaml.safe_dump({"mode": "small", "cloud": {
        "provider": provider, "region": "eu-west-2", "domain": "osprey.example.org", **cloud_extra,
    }}), encoding="utf-8")  # fmt: skip
    return path


def _outputs(values: dict[str, Any]) -> tuple[int, str]:
    return 0, json.dumps({key: {"value": value} for key, value in values.items()})


def _ready(rig: Rig, outputs: dict[str, Any], code_answers: list[tuple[int, str]]) -> None:
    rig.responses = {
        "get-url": [(0, "https://github.com/acme/ospreyflow.git\n")],
        "output": [_outputs(outputs)],
        "get-secret-value": code_answers,
        "show": code_answers,
    }


def _tofu(rig: Rig) -> list[list[str]]:
    return [argv for argv in rig.runner.argvs() if argv[0] == "tofu"]


def test_it_plans_then_builds_on_confirmation_and_keeps_the_state_private(
    rig: Rig, tmp_path: Path
) -> None:
    _module(rig)
    _ready(rig, AWS_OUTPUTS, [(0, "ABCD-EFGH-JKLM-NPQR")])
    rig.replies = ["yes"]
    assert rig("install", "--mode", "small", "--cloud", "aws", "--config",
               str(_answers(tmp_path))) == 0  # fmt: skip
    init, plan, apply = _tofu(rig)
    module = rig.product / "deploy" / "opentofu" / "small" / "aws"
    state = rig.product / ".cloud" / "small-aws"
    assert init[:3] == ["tofu", f"-chdir={module}", "init"]
    assert plan[2] == "plan" and f"-state={state / 'terraform.tfstate'}" in plan
    assert "-var=domain=osprey.example.org" in plan and "-var=region=eu-west-2" in plan
    assert "-var=repository=https://github.com/acme/ospreyflow.git" in plan
    assert apply[2] == "apply" and apply[-1] == str(state / "plan.bin")
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    tofu_calls = [c for c in rig.runner.calls if c.argv[0] == "tofu"]
    assert all(c.env and c.env["TF_DATA_DIR"] == str(state / ".terraform") for c in tofu_calls)


def test_declining_builds_nothing(rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _module(rig)
    _ready(rig, AWS_OUTPUTS, [(0, "X")])
    rig.replies = ["no"]
    assert rig("install", "--mode", "small", "--cloud", "aws", "--config",
               str(_answers(tmp_path))) == 0  # fmt: skip
    assert [argv[2] for argv in _tofu(rig)] == ["init", "plan"]
    assert "Nothing was built" in capsys.readouterr().out


def test_without_a_zone_it_says_the_record_and_waits_for_it(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _module(rig)
    _ready(rig, AWS_OUTPUTS, [(0, "CODE")])
    looked: list[str] = []
    answers = iter([set(), {"198.51.100.1"}, {ADDRESS}])
    monkeypatch.setattr(cloud, "_resolve", lambda name: looked.append(name) or next(answers))
    assert rig("install", "--mode", "small", "--cloud", "aws", "--yes", "--config",
               str(_answers(tmp_path))) == 0  # fmt: skip
    assert looked == ["osprey.example.org"] * 3  # until it resolves to the server, not just any
    assert f"an A record for osprey.example.org, value {ADDRESS}" in capsys.readouterr().out


def test_with_a_zone_opentofu_made_the_record_and_nothing_waits_on_dns(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _module(rig)
    _ready(rig, AWS_OUTPUTS, [(0, "CODE")])
    monkeypatch.setattr(cloud, "_resolve", lambda name: pytest.fail("no DNS wait with a zone"))
    assert rig("install", "--mode", "small", "--cloud", "aws", "--yes", "--config",
               str(_answers(tmp_path, dns_zone="example.org"))) == 0  # fmt: skip
    (plan,) = [argv for argv in _tofu(rig) if argv[2] == "plan"]
    assert "-var=dns_zone=example.org" in plan


def test_the_code_is_awaited_shown_once_and_deleted_from_the_store(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str], quick: list[str]
) -> None:
    _module(rig)
    not_yet = (254, "ResourceNotFoundException: Secrets Manager can't find the specified secret value")
    _ready(rig, AWS_OUTPUTS, [not_yet, (0, "pending\n"), (0, "ABCD-EFGH-JKLM-NPQR\n")])
    assert rig("install", "--mode", "small", "--cloud", "aws", "--yes", "--config",
               str(_answers(tmp_path))) == 0  # fmt: skip
    assert quick == ["https://osprey.example.org/"]
    out = capsys.readouterr().out
    assert out.count("ABCD-EFGH-JKLM-NPQR") == 1
    reads = [argv for argv in rig.captured if "get-secret-value" in argv]
    assert len(reads) == 3
    (delete,) = rig.runner.with_word("delete-secret")
    assert "--force-delete-without-recovery" in delete.argv
    assert AWS_OUTPUTS["first_admin_secret"] in delete.argv


def test_on_azure_the_code_comes_from_key_vault(rig: Rig, tmp_path: Path) -> None:
    _module(rig, "azure")
    outputs = {"address": ADDRESS, "domain": "osprey.example.org", "key_vault": "osprey-kv-1a2b"}
    _ready(rig, outputs, [(0, "CODE")])
    assert rig("install", "--mode", "small", "--cloud", "azure", "--yes", "--config",
               str(_answers(tmp_path, "azure"))) == 0  # fmt: skip
    (read,) = [argv for argv in rig.captured if "show" in argv]
    assert read[:3] == ["az", "keyvault", "secret"] and "osprey-kv-1a2b" in read
    assert rig.runner.with_word("delete")


def test_answers_with_no_domain_are_refused_before_opentofu_runs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig)
    _ready(rig, AWS_OUTPUTS, [(0, "CODE")])
    path = tmp_path / "answers.yaml"
    path.write_text(yaml.safe_dump({"mode": "small", "cloud": {"provider": "aws",
                                                               "region": "eu-west-2"}}))  # fmt: skip
    assert rig("install", "--mode", "small", "--cloud", "aws", "--yes", "--config", str(path)) == 1
    assert "domain" in capsys.readouterr().err
    assert _tofu(rig) == [] or [argv[2] for argv in _tofu(rig)] == ["init"]


def test_a_server_that_never_answers_is_given_up_on_in_words(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _module(rig)
    _ready(rig, AWS_OUTPUTS, [(0, "CODE")])
    clock = iter(range(0, 10**7, 600))
    monkeypatch.setattr(cloud, "_now", lambda: float(next(clock)))
    monkeypatch.setattr(cloud, "_answers", lambda url: False)
    assert rig("install", "--mode", "small", "--cloud", "aws", "--yes", "--config",
               str(_answers(tmp_path))) == 1
    assert "gave up waiting for https://osprey.example.org to answer" in capsys.readouterr().err
    assert not rig.runner.with_word("delete-secret")
