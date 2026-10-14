"""`ospreyflow install --mode enterprise --cloud aws|azure` on the operator's machine (ADR-114
Amendment 19): the cluster and its managed services built with OpenTofu on confirmation
(`deploy/opentofu/cluster/<cloud>`, Amendment 18), then the cluster install (Amendment 16) run from
what OpenTofu made — its answers, a kubeconfig of the install's own, and the managed services'
secrets read from the cloud's secret store into the install's environment only.

OpenTofu and the cloud CLIs are stood in for: the commands are recorded and their answers queued,
refusals included — a secret that cannot be read answers as the real CLI does, non-zero.

What a mistake would do, and the case that catches it:
- a cluster built without being asked — `test_declining_builds_nothing_and_installs_nothing`;
- the module's answers not reaching the deployment —
  `test_the_modules_answers_and_the_operators_become_one_osprey_yaml`;
- a secret on a command line, in `osprey.yaml` or on the screen —
  `test_the_secrets_reach_the_install_through_its_environment_only`;
- the operator's own kubeconfig changed — `test_the_install_has_a_kubeconfig_of_its_own`, and on
  Azure `test_on_azure_the_kubeconfig_signs_in_through_entra_id_and_three_secrets_are_read`;
- an install carried on without a secret — `test_a_secret_that_cannot_be_read_stops_the_install_in_words`;
- a cluster API open to the world, or no addresses at all —
  `test_without_api_cidrs_nothing_runs` and `test_answers.py`'s cases;
- answers that fight the module — `test_answers_naming_their_own_managed_services_are_refused`,
  `test_the_cloud_flag_and_the_answers_provider_must_agree`.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml

from .conftest import Rig

PG_SECRET = "arn:aws:secretsmanager:eu-west-2:1:secret:rds!db-1"
VALKEY_SECRET = "arn:aws:secretsmanager:eu-west-2:1:secret:osprey/valkey-token"
PG_PASSWORD = "pg-Secret-Value-1"
VALKEY_TOKEN = "valkey-Token-Value-2"
MEDIA_KEY = "media-Key-Value-3"

AWS_MODULE_ANSWERS = {
    "mode": "enterprise",
    "cloud": {"provider": "aws", "region": "eu-west-2", "domain": "osprey.example.org"},
    "cluster": {"namespace": "ospreyflow", "storage_class": "ospreyflow-volumes",
                "shared_storage_class": "ospreyflow-shared"},
    "external": {
        "postgres": {"host": "osprey.x.eu-west-2.rds.amazonaws.com", "port": 5432,
                     "database": "ospreyflow", "user": "osprey", "sslmode": "require"},
        "valkey": {"host": "master.osprey.x.cache.amazonaws.com", "port": 6379, "tls": True},
        "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2",
                         "credentials": "instance", "bucket_prefix": "osprey-x-"},
        "search": {"url": "https://vpc-osprey.eu-west-2.es.amazonaws.com"},
    },
}  # fmt: skip
AWS_OUTPUTS = {
    "cluster_name": "osprey",
    "region": "eu-west-2",
    "database_password_secret": PG_SECRET,
    "valkey_token_secret": VALKEY_SECRET,
    "shared_file_system": "fs-1",
    "install_answers": yaml.safe_dump(AWS_MODULE_ANSWERS),
}

VAULT = "https://ospreyx.vault.azure.net/secrets"
AZURE_MODULE_ANSWERS = {
    "mode": "enterprise",
    "cloud": {"provider": "azure", "region": "uksouth", "domain": "osprey.example.org"},
    "cluster": {"namespace": "ospreyflow", "storage_class": "ospreyflow-volumes",
                "shared_storage_class": "ospreyflow-shared"},
    "external": {
        "postgres": {"host": "osprey-x.postgres.database.azure.com", "sslmode": "require"},
        "valkey": {"host": "osprey-x.redis.cache.windows.net", "port": 6380, "tls": True},
        "media": {"blob_account": "ospreyx", "blob_container": "ospreyflow-media"},
    },
}  # fmt: skip
AZURE_OUTPUTS = {
    "cluster_name": "osprey",
    "resource_group": "osprey",
    "region": "uksouth",
    "key_vault": "ospreyx",
    "database_password_secret": f"{VAULT}/database-password",
    "valkey_token_secret": f"{VAULT}/valkey-token",
    "media_key_secret": f"{VAULT}/media-storage-key",
    "install_answers": yaml.safe_dump(AZURE_MODULE_ANSWERS),
}


def _module(rig: Rig, provider: str = "aws") -> Path:
    module = rig.product / "deploy" / "opentofu" / "cluster" / provider
    module.mkdir(parents=True)
    return module


def _answers(tmp_path: Path, provider: str = "aws", **extra: Any) -> Path:
    region = "eu-west-2" if provider == "aws" else "uksouth"
    raw: dict[str, Any] = {
        "mode": "enterprise",
        "cloud": {"provider": provider, "region": region, "domain": "osprey.example.org",
                  "admin_email": "ops@example.org", "api_cidrs": ["203.0.113.0/24"]},
        **extra,
    }  # fmt: skip
    path = tmp_path / "answers.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def _outputs(values: dict[str, Any]) -> tuple[int, str]:
    return 0, json.dumps({key: {"value": value} for key, value in values.items()})


def _ready_aws(rig: Rig) -> None:
    rig.responses = {
        "output": [_outputs(AWS_OUTPUTS)],
        # RDS keeps its password as JSON; the Valkey token is the secret's whole value.
        PG_SECRET: [
            (0, json.dumps({"username": "osprey", "password": PG_PASSWORD}) + "\n")
        ],
        VALKEY_SECRET: [(0, VALKEY_TOKEN + "\n")],
    }


def _ready_azure(rig: Rig) -> None:
    rig.responses = {
        "output": [_outputs(AZURE_OUTPUTS)],
        f"{VAULT}/database-password": [(0, PG_PASSWORD + "\n")],
        f"{VAULT}/valkey-token": [(0, VALKEY_TOKEN + "\n")],
        f"{VAULT}/media-storage-key": [(0, MEDIA_KEY + "\n")],
    }


def _install(
    rig: Rig, tmp_path: Path, provider: str = "aws", *flags: str, **extra: Any
) -> int:
    return rig("install", "--mode", "enterprise", "--cloud", provider, "--force", "--config",
               str(_answers(tmp_path, provider, **extra)), *flags)  # fmt: skip


def _tofu(rig: Rig) -> list[list[str]]:
    return [argv for argv in rig.runner.argvs() if argv[0] == "tofu"]


def _cluster_install(rig: Rig) -> list[Any]:
    return [c for c in rig.runner.calls if "harness.cluster_install" in c.argv]


def test_it_plans_then_builds_on_confirmation_and_keeps_the_state_private(
    rig: Rig, tmp_path: Path
) -> None:
    module = _module(rig)
    _ready_aws(rig)
    rig.replies = ["yes"]
    assert _install(rig, tmp_path) == 0
    init, plan, apply = _tofu(rig)
    state = rig.product / ".cloud" / "enterprise-aws"
    assert init[:3] == ["tofu", f"-chdir={module}", "init"]
    assert plan[2] == "plan" and f"-state={state / 'terraform.tfstate'}" in plan
    assert "-var=region=eu-west-2" in plan and "-var=domain=osprey.example.org" in plan
    assert '-var=api_cidrs=["203.0.113.0/24"]' in plan
    assert (
        "-var=namespace=ospreyflow" in plan
        and "-var=admin_email=ops@example.org" in plan
    )
    assert apply[2] == "apply" and apply[-1] == str(state / "plan.bin")
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    tofu_calls = [c for c in rig.runner.calls if c.argv[0] == "tofu"]
    assert all(
        c.env and c.env["TF_DATA_DIR"] == str(state / ".terraform") for c in tofu_calls
    )
    assert len(_cluster_install(rig)) == 1


def test_declining_builds_nothing_and_installs_nothing(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig)
    _ready_aws(rig)
    rig.replies = ["no"]
    assert _install(rig, tmp_path) == 0
    assert [argv[2] for argv in _tofu(rig)] == ["init", "plan"]
    assert _cluster_install(rig) == []
    assert "Nothing was built" in capsys.readouterr().out


def test_the_modules_answers_and_the_operators_become_one_osprey_yaml(
    rig: Rig, tmp_path: Path
) -> None:
    _module(rig)
    _ready_aws(rig)
    assert (
        _install(
            rig,
            tmp_path,
            "aws",
            "--yes",
            mail={"host": "smtp.example.org", "from": "osprey@example.org"},
        )
        == 0
    )
    config = rig.config()
    assert config["profile"] == "cluster"
    assert config["cluster"] == {"namespace": "ospreyflow", "storage_class": "ospreyflow-volumes",
                                 "shared_storage_class": "ospreyflow-shared"}  # fmt: skip
    assert config["external"] == AWS_MODULE_ANSWERS["external"]
    assert config["network"] == {"public_origin": "https://osprey.example.org"}  # type: ignore[comparison-overlap]
    assert config["mail"]["host"] == "smtp.example.org"  # type: ignore[index]
    (step,) = _cluster_install(rig)
    assert step.argv[step.argv.index("--email") + 1] == "ops@example.org"


def test_the_install_has_a_kubeconfig_of_its_own(rig: Rig, tmp_path: Path) -> None:
    _module(rig)
    _ready_aws(rig)
    assert _install(rig, tmp_path, "aws", "--yes") == 0
    kubeconfig = str(rig.product / ".cloud" / "enterprise-aws" / "kubeconfig")
    (update,) = rig.runner.with_word("update-kubeconfig")
    assert update.argv[:3] == ["aws", "eks", "update-kubeconfig"]
    assert update.argv[update.argv.index("--name") + 1] == "osprey"
    assert update.argv[update.argv.index("--region") + 1] == "eu-west-2"
    assert update.argv[update.argv.index("--kubeconfig") + 1] == kubeconfig
    (step,) = _cluster_install(rig)
    assert step.env and step.env["KUBECONFIG"] == kubeconfig
    order = [c.argv for c in rig.runner.calls]
    assert order.index(update.argv) < order.index(step.argv)


def test_the_secrets_reach_the_install_through_its_environment_only(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig)
    _ready_aws(rig)
    assert _install(rig, tmp_path, "aws", "--yes") == 0
    (step,) = _cluster_install(rig)
    assert step.env and step.env["OSPREY_POSTGRES_PASSWORD"] == PG_PASSWORD
    assert step.env["VALKEY_PASSWORD"] == VALKEY_TOKEN
    reads = [argv for argv in rig.captured if "get-secret-value" in argv]
    assert {argv[argv.index("--secret-id") + 1] for argv in reads} == {
        PG_SECRET,
        VALKEY_SECRET,
    }
    said = capsys.readouterr()
    for secret in (PG_PASSWORD, VALKEY_TOKEN):
        assert all(secret not in " ".join(c.argv) for c in rig.runner.calls)
        assert secret not in (rig.product / "osprey.yaml").read_text(encoding="utf-8")
        assert secret not in said.out + said.err
    # Only the cluster install is given them, not OpenTofu or the cloud's command line.
    others = [c for c in rig.runner.calls if c is not step]
    assert all("OSPREY_POSTGRES_PASSWORD" not in (c.env or {}) for c in others)


def test_on_azure_the_kubeconfig_signs_in_through_entra_id_and_three_secrets_are_read(
    rig: Rig, tmp_path: Path
) -> None:
    _module(rig, "azure")
    _ready_azure(rig)
    assert _install(rig, tmp_path, "azure", "--yes") == 0
    kubeconfig = str(rig.product / ".cloud" / "enterprise-azure" / "kubeconfig")
    (credentials,) = rig.runner.with_word("get-credentials")
    assert credentials.argv[:3] == ["az", "aks", "get-credentials"]
    assert credentials.argv[credentials.argv.index("--resource-group") + 1] == "osprey"
    assert credentials.argv[credentials.argv.index("--file") + 1] == kubeconfig
    (convert,) = rig.runner.with_word("convert-kubeconfig")
    assert convert.argv[0] == "kubelogin" and "azurecli" in convert.argv
    assert convert.argv[convert.argv.index("--kubeconfig") + 1] == kubeconfig
    order = [c.argv for c in rig.runner.calls]
    assert order.index(credentials.argv) < order.index(convert.argv)
    (step,) = _cluster_install(rig)
    assert step.env and step.env["KUBECONFIG"] == kubeconfig
    assert step.env["OSPREY_POSTGRES_PASSWORD"] == PG_PASSWORD
    assert step.env["VALKEY_PASSWORD"] == VALKEY_TOKEN
    assert step.env["AZURE_STORAGE_KEY"] == MEDIA_KEY
    reads = [
        argv
        for argv in rig.captured
        if argv[:4] == ["az", "keyvault", "secret", "show"]
    ]
    assert len(reads) == 3
    assert rig.config()["external"]["media"]["blob_account"] == "ospreyx"  # type: ignore[index]


def test_a_secret_that_cannot_be_read_stops_the_install_in_words(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig)
    _ready_aws(rig)
    rig.responses[VALKEY_SECRET] = [(254, "AccessDeniedException: not authorised\n")]
    assert _install(rig, tmp_path, "aws", "--yes") == 1
    err = capsys.readouterr().err
    assert (
        VALKEY_SECRET in err
        and "AccessDeniedException" not in err.split(VALKEY_SECRET)[0]
    )
    assert _cluster_install(rig) == []


def test_an_rds_secret_with_no_password_in_it_is_refused(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig)
    _ready_aws(rig)
    rig.responses[PG_SECRET] = [(0, json.dumps({"username": "osprey"}))]
    assert _install(rig, tmp_path, "aws", "--yes") == 1
    assert PG_SECRET in capsys.readouterr().err
    assert _cluster_install(rig) == []


def test_without_api_cidrs_nothing_runs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig)
    _ready_aws(rig)
    path = tmp_path / "answers.yaml"
    path.write_text(yaml.safe_dump({"mode": "enterprise", "cloud": {
        "provider": "aws", "region": "eu-west-2", "domain": "osprey.example.org"}}))  # fmt: skip
    assert rig("install", "--mode", "enterprise", "--cloud", "aws", "--yes", "--config",
               str(path)) == 1  # fmt: skip
    assert "api_cidrs" in capsys.readouterr().err
    assert _tofu(rig) == []


def test_answers_naming_their_own_managed_services_are_refused(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig)
    _ready_aws(rig)
    external = {"postgres": {"host": "elsewhere.example.org"}}
    assert _install(rig, tmp_path, "aws", "--yes", external=external) == 1
    assert "OpenTofu" in capsys.readouterr().err
    assert _tofu(rig) == []


def test_the_cloud_flag_and_the_answers_provider_must_agree(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _module(rig, "azure")
    _ready_azure(rig)
    path = _answers(tmp_path, "aws")
    assert rig("install", "--mode", "enterprise", "--cloud", "azure", "--yes", "--config",
               str(path)) == 1  # fmt: skip
    assert "azure" in capsys.readouterr().err
    assert _tofu(rig) == []
