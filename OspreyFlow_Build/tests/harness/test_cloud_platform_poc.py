"""The `cloud-platform` profile's proof-of-concept shape, `cloud_platform.shape: poc`
(`spec/06_DECISIONS.md` ADR-148 Amendment 5): one ArcadeDB and one ClickHouse whose Keeper runs
inside the server, no PodDisruptionBudgets, the Ingest root on a claim of its own, and the install
and decommission runbooks rendered for the deployment. The standard shape stays as P7 built it.

What a mistake would do, and the case that catches it (rule 12):
- a poc that still runs a Keeper StatefulSet, or a ClickHouse with no Keeper to reach (its
  Replicated database cannot start) — `test_the_clickhouse_server_runs_its_own_keeper`;
- uploads filling the disk the settings files and recipes live on —
  `test_the_ingest_root_is_on_a_claim_of_its_own`;
- a shape setting that changes the standard render — `test_the_standard_shape_is_the_default`;
- a production namespace in the poc shape, which would run one copy of each store and call it
  production — `test_the_poc_shape_is_refused_in_production`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from harness.cloud_platform.runbooks import command_blocks
from harness.render import render
from pydantic import ValidationError
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig


def _config(name: str = "poc", **changes: Any) -> OspreyConfig:
    raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
    for key, value in changes.items():
        raw[key] = {**raw.get(key, {}), **value} if isinstance(value, dict) else value
    return OspreyConfig.model_validate(raw)


def _artefacts(config: OspreyConfig) -> dict[str, str]:
    return render(config, resolver=_resolver).artefacts


def _values(config: OspreyConfig) -> dict[str, Any]:
    return yaml.safe_load(_artefacts(config)["values.yaml"])


@pytest.fixture(scope="module")
def poc() -> dict[str, Any]:
    return _values(_config())


def _by_name(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {w["name"]: w for w in values["workloads"]}


# ---- the setting ------------------------------------------------------------------------------


def test_the_standard_shape_is_the_default() -> None:
    """Naming the standard shape renders exactly what leaving it out does, so every P7 deployment
    is unchanged."""
    for name in ("development", "production"):
        raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
        assert "shape" not in raw["cloud_platform"]
        named = _config(name, cloud_platform={**raw["cloud_platform"], "shape": "standard"})
        assert _artefacts(named) == _artefacts(_config(name))


def test_the_poc_shape_is_refused_in_production() -> None:
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    raw["cloud_platform"]["environment"] = "production"
    with pytest.raises(ValidationError, match="shape: poc is a development namespace's"):
        OspreyConfig.model_validate(raw)


def test_a_shape_the_profile_does_not_know_is_refused() -> None:
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    raw["cloud_platform"]["shape"] = "tiny"
    with pytest.raises(ValidationError):
        OspreyConfig.model_validate(raw)


# ---- the stores -------------------------------------------------------------------------------


def test_one_arcadedb_one_clickhouse_and_no_keeper_of_its_own(poc: dict[str, Any]) -> None:
    workloads = _by_name(poc)
    assert workloads["arcadedb"]["replicas"] == 1
    assert workloads["clickhouse"]["replicas"] == 1
    assert "clickhouse-keeper" not in workloads
    assert "keeper.xml" not in poc["files"]


def test_the_clickhouse_server_runs_its_own_keeper(poc: dict[str, Any]) -> None:
    """The cluster's ClickHouse holds a Replicated database, which needs a Keeper: in this shape
    the server runs one itself (`keeper_server` in its own configuration), a Raft of one, its log
    on the server's own claim, and the server's `zookeeper` is that Keeper."""
    config = poc["files"]["clickhouse.xml"]
    keeper = re.search(r"<keeper_server>(.*?)</keeper_server>", config, re.S)
    assert keeper, config
    assert "<tcp_port>9181</tcp_port>" in keeper.group(1)
    assert "<server_id>1</server_id>" in keeper.group(1)
    assert keeper.group(1).count("<server>") == 1
    claim = next(c for c in _by_name(poc)["clickhouse"]["claims"] if c["name"] == "data")
    for path in re.findall(r"<(?:log|snapshot)_storage_path>([^<]+)<", keeper.group(1)):
        assert path.startswith(claim["mountPath"] + "/"), path
    zookeeper = re.search(r"<zookeeper>(.*?)</zookeeper>", config, re.S)
    assert zookeeper and re.findall(r"<host>([^<]+)</host>", zookeeper.group(1)) == ["127.0.0.1"]
    assert "<port>9181</port>" in zookeeper.group(1)
    assert "clickhouse-keeper" not in config


def test_no_disruption_budgets(poc: dict[str, Any]) -> None:
    assert not [w["name"] for w in poc["workloads"] if "disruptionBudget" in w]


# ---- the Ingest root --------------------------------------------------------------------------


def test_the_ingest_root_is_on_a_claim_of_its_own(poc: dict[str, Any]) -> None:
    """ADR-148 Amendment 5: uploads and the drop folder on a disk of their own, so they cannot fill
    the one the settings files and the recipes are on; the other shared folders stay where P7 put
    them."""
    api = _by_name(poc)["api"]
    ingest = [s for s in api["shared"] if s["mountPath"].startswith("/var/lib/osprey/ingest")]
    assert ingest and all(s.get("claim") == "ingest" for s in ingest)
    # A folder on its claim, not the claim's root, which holds the file system's lost+found.
    assert all(s["subPath"].startswith("ingest") for s in ingest)
    others = [s for s in api["shared"] if s not in ingest]
    assert others and not [s for s in others if "claim" in s]
    claims = poc["storage"]["claims"]
    assert [c["name"] for c in claims] == ["ingest"]
    assert claims[0]["size"]
    # Only the shape adds it: the standard shape's values carry no claims of their own.
    assert "claims" not in _values(_config("development"))["storage"]


# ---- the runbooks -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def runbooks() -> dict[str, str]:
    artefacts = _artefacts(_config())
    return {name: artefacts[name] for name in ("INSTALL.md", "DECOMMISSION.md")}


def test_the_runbooks_are_rendered_for_the_poc_shape_alone() -> None:
    assert {"INSTALL.md", "DECOMMISSION.md"} <= set(_artefacts(_config()))
    assert not {"INSTALL.md", "DECOMMISSION.md"} & set(_artefacts(_config("development")))


def test_a_platform_block_is_left_to_the_platform() -> None:
    from harness.cloud_platform.runbooks import command_blocks

    text = "x\n```sh\necho everywhere\n```\n\n```sh platform\necho there\n```\n```python\nno\n```\n"
    assert command_blocks(text, on_the_platform=True) == ["echo everywhere\n", "echo there\n"]
    assert command_blocks(text, on_the_platform=False) == ["echo everywhere\n"]


@pytest.mark.parametrize("on_the_platform", [True, False], ids=["platform", "rehearsal"])
def test_every_block_is_shell_that_parses_and_never_exits_the_shell(
    runbooks: dict[str, str], on_the_platform: bool, tmp_path: Any
) -> None:
    """Pasted into one shell by a person, or run as one script by the rehearsal: each parses, and
    none ends the person's shell (`exit`) on a failure; `false` stops a script run with `set -e`."""
    import subprocess

    from harness.cloud_platform.runbooks import command_blocks

    for name, text in runbooks.items():
        blocks = command_blocks(text, on_the_platform=on_the_platform)
        assert blocks, name
        script = tmp_path / f"{name}.sh"
        script.write_text("".join(blocks), encoding="utf-8")
        done = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert done.returncode == 0, (name, done.stderr)
        assert not re.search(r"(^|[;&|{ ])exit\b", "".join(blocks), re.M), name


def test_the_rehearsal_reaches_no_aws_account_and_no_terraform(runbooks: dict[str, str]) -> None:
    """What the kind rehearsal runs never calls the AWS command line or Terraform: those are the
    platform's blocks, which it stands in for."""
    from harness.cloud_platform.runbooks import command_blocks

    for name, text in runbooks.items():
        rehearsed = "".join(command_blocks(text, on_the_platform=False))
        assert not re.search(r"(^|\s)(aws|tofu|terraform)\s", rehearsed, re.M), name
        assert (
            re.search(r"(^|\s)aws\s", "".join(command_blocks(text, on_the_platform=True)))
            or name == "INSTALL.md"
        )


def test_the_runbooks_carry_the_deployment_s_own_names(runbooks: dict[str, str]) -> None:
    for text in runbooks.values():
        assert "export NS=ospreyflow-poc " in text
    assert "123456789012.dkr.ecr.eu-west-2.amazonaws.com" in runbooks["INSTALL.md"]


def test_the_decommission_removes_every_claim_the_render_makes(
    poc: dict[str, Any], runbooks: dict[str, str]
) -> None:
    """`helm uninstall` keeps every claim. The runbook removes the StatefulSets' claims by the
    release's label (the StatefulSet controller gives each claim its selector's labels, the
    release's among them) and the kept claims by name; the decommission check (its last block)
    names anything still left, the disks among them."""
    text = runbooks["DECOMMISSION.md"]
    assert 'delete pvc -l app.kubernetes.io/instance="$RELEASE"' in text
    names = ["ospreyflow-shared", *(f"ospreyflow-{c['name']}" for c in poc["storage"]["claims"])]
    line = next(x for x in text.splitlines() if "delete pvc ospreyflow-shared" in x)
    assert all(n in line.split() for n in names), line
    last = command_blocks(text, on_the_platform=False)[-1]
    assert "-m harness.cloud_platform.decommission_check" in last
    assert (
        text.index("helm uninstall") < text.index("delete pvc") < text.index("decommission_check")
    )


def test_no_command_needs_more_than_a_namespace_s_rights(runbooks: dict[str, str]) -> None:
    """The client's team is the namespace's tenant: no block lists or changes anything cluster-wide
    (volumes, every kind there is), and the disks are read from the account, by the claims'
    namespace tag, in a block of the platform's (the self-review of P7b, point 2)."""
    for name, text in runbooks.items():
        everything = "".join(command_blocks(text, on_the_platform=True))
        assert not re.search(r"kubectl (get|delete) (pv|persistentvolume)s?\b", everything), name
        assert "--namespaced" not in everything, name
        for command in re.findall(
            r"^\s*kubectl (?!api-resources|config|auth)(.*)$", everything, re.M
        ):
            assert '-n "$NS"' in command, (name, command)
    platform = "".join(command_blocks(runbooks["DECOMMISSION.md"], on_the_platform=True))
    rehearsal = "".join(command_blocks(runbooks["DECOMMISSION.md"], on_the_platform=False))
    assert "aws ec2 describe-volumes" in platform and "aws ec2" not in rehearsal


def test_the_install_signs_in_to_the_registry_and_pins_before_it_installs(
    runbooks: dict[str, str],
) -> None:
    """Between the push and the install: the registry's sign-in before the push (the platform's
    block), and a pinned render after it, so the values name ours by the digest the registry holds
    (decision 8), before `helm` reads them; then the first administrator."""
    text = runbooks["INSTALL.md"]
    order = [
        text.index("--allow-unpinned"),
        text.index("aws ecr get-login-password"),
        text.index("ospreyflow images push"),
        text.index('-m harness.render --config "$CONFIG"\n```\n\n## 5'),
        text.index("helm upgrade --install"),
        text.index("-m harness.cloud_platform.identity"),
    ]
    assert order == sorted(order), order
    assert "aws ecr get-login-password" in "".join(command_blocks(text, on_the_platform=True))
    assert "aws ecr" not in "".join(command_blocks(text, on_the_platform=False))


# ---- CPU limits (the orchestrator's D2c finding on LimitRanges) --------------------------------


def _cpu(quantity: str) -> float:
    return float(quantity[:-1]) / 1000 if quantity.endswith("m") else float(quantity)


def test_every_poc_container_names_a_cpu_limit_at_or_above_its_request(poc: dict[str, Any]) -> None:
    """A LimitRange's default CPU limit is given to exactly the containers that name none, and a
    ResourceQuota on `limits.cpu` refuses a pod with none; so in the poc shape, which goes onto the
    client's namespace before their team has said which they set, each container names its own."""
    for pod in [*poc["workloads"], *poc["jobs"]]:
        for container in [pod, *pod.get("initContainers", [])]:
            resources = container["resources"]
            assert "cpu" in resources["limits"], container["name"]
            assert _cpu(resources["limits"]["cpu"]) >= _cpu(resources["requests"]["cpu"])


def test_the_standard_shape_names_no_cpu_limit() -> None:
    values = _values(_config("development"))
    for pod in [*values["workloads"], *values["jobs"]]:
        for container in [pod, *pod.get("initContainers", [])]:
            assert "cpu" not in container["resources"]["limits"], container["name"]


def test_a_cpu_limit_below_its_request_is_refused_in_words(monkeypatch: pytest.MonkeyPatch) -> None:
    import harness.cloud_platform as cp
    from harness.cloud_platform import CloudPlatformNotRenderable
    from harness.cloud_platform.settings import load_profile

    profile = load_profile()
    low = profile.model_copy(
        update={"poc": profile.poc.model_copy(update={"cpu_limits": {"default": "50m"}})}
    )
    monkeypatch.setattr(cp, "load_profile", lambda: low)
    with pytest.raises(CloudPlatformNotRenderable, match="CPU limit 50m is below its request"):
        _artefacts(_config())


def test_the_poc_shape_makes_no_opensearch_domain() -> None:
    """The orchestrator's ruling: no pod reads the domain (`opensearch-output`), and it is a paid
    domain on the client's own install, so the poc shape's Terraform makes none; the standard
    shape's is carried (ADR-148 Amendment 5, "Left")."""
    poc = _artefacts(_config())
    assert "terraform/opensearch.tf" not in poc
    assert not [n for n, t in poc.items() if n.startswith("terraform/") and "opensearch" in t]
    assert "terraform/opensearch.tf" in _artefacts(_config("development"))


def test_the_lock_names_only_the_images_a_poc_pod_runs() -> None:
    """The self-review of P7b, point 11: the poc shape runs no Keeper of its own, so its lock names
    none (and a pinned render need not resolve one); the standard shape's still does."""
    lock = yaml.safe_load(_artefacts(_config())["versions.lock"])
    services = {entry["service"] for entry in lock["images"]}
    assert "clickhouse-keeper" not in services and "clickhouse" in services
    standard = yaml.safe_load(_artefacts(_config("development"))["versions.lock"])
    assert "clickhouse-keeper" in {entry["service"] for entry in standard["images"]}
