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

    text = "x\n```bash\necho everywhere\n```\n\n```bash platform\necho there\n```\n```sh\nno\n```\n"
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


#: What the runbooks read from the operator's shell and never set themselves: each named in the
#: runbook's own words as something to give (`STATE`, `DISKS`, ...), or bash's and the system's.
_GIVEN = {
    "BASH_VERSION", "TMPDIR", "OSPREY_CURL_OPTS", "STATE", "DISKS", "CLUSTER_ACCOUNT",
    "BACKUP_RETENTION_DAYS", "TF_MODULE",
}  # fmt: skip


def test_every_variable_a_runbook_reads_is_one_it_sets_or_asks_for(
    runbooks: dict[str, str],
) -> None:
    """R1's reading of P7b's decommission: `s3://$PREFIXbackups/` is read by bash as the variable
    `PREFIXbackups`, which is empty, so the last backup was named `s3://backups/...` and the
    bucket in steps 7 and 9 was `""`; the line after it repeated the same text, so its check could
    not fail. Every `$NAME` in either runbook, as bash reads the name (the longest run of word
    characters), is a variable the runbook sets, or one it asks the operator for; the text after
    a variable is fenced off by `${NAME}` where a word character follows."""
    for name, text in runbooks.items():
        blocks = "".join(command_blocks(text, on_the_platform=True))
        set_here = set(re.findall(r"(?:^|[\s;(]|export )([A-Za-z_]\w*)=", blocks, re.M))
        set_here |= set(re.findall(r"\bfor ([A-Za-z_]\w*) in\b", blocks))
        set_here |= set(re.findall(r"\bread -r ([A-Za-z_]\w*)", blocks))
        read = set(re.findall(r"\$\{?([A-Za-z_]\w*)", text))
        assert read - set_here - _GIVEN == set(), name


def test_the_last_backup_is_named_in_the_backups_bucket(
    runbooks: dict[str, str], tmp_path: Any
) -> None:
    """The decommission's step 2, run under bash as written, with a `kubectl` that answers as a
    finished backup Job does: `LAST_BACKUP` names the set in `<prefix>backups`, the bucket the
    decommission keeps (rule 12: the line's own `case` check could not see the empty name)."""
    import subprocess
    import sys

    text = runbooks["DECOMMISSION.md"]
    step = text[text.index("## 2.") : text.index("## 3.")]
    (block,) = command_blocks(step, on_the_platform=False)
    stub = tmp_path / "kubectl"
    stub.write_text(
        "#!/bin/sh\n"
        'case "$*" in *"get cronjob"*) exit 1;; *"-o jsonpath={.status.succeeded}"*) echo 1;; esac\n'
    )
    stub.chmod(0o755)
    done = subprocess.run(
        ["bash", "-c", f'set -e\n{block}\necho "$LAST_BACKUP"'],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{tmp_path}:/usr/bin:/bin",
            "NS": "ospreyflow-poc",
            "PREFIX": "ospreyflow-poc-1a2b3c4d-",
            "PY": sys.executable,
        },
    )
    assert done.returncode == 0, done.stderr
    assert re.fullmatch(
        r"s3://ospreyflow-poc-1a2b3c4d-backups/sets/\d{8}T\d{6}Z/",
        done.stdout.strip().splitlines()[-1],
    ), done.stdout


def test_the_entra_registrations_are_asked_for_before_the_deployment(
    runbooks: dict[str, str],
) -> None:
    """R1's reading of the install: step 6 said "Before step 5, the client's Entra administrator
    registers ...", read after step 5 by anyone running the blocks in order. The registrations,
    with the tenant and both application ids, are asked for in what the install needs, before its
    first block."""
    text = runbooks["INSTALL.md"]
    needs = text[text.index("**What it needs.**") : text.index("## 1.")]
    for named in (
        "00000000-1111-4222-8333-444444444444",
        "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff",
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    ):
        assert named in needs, named
    assert "Before step 5" not in text[text.index("## 5.") :]


def test_the_install_check_says_what_its_curl_options_are(runbooks: dict[str, str]) -> None:
    """Step 7's `OSPREY_CURL_OPTS` was named nowhere: a team whose ingress certificate is not
    publicly trusted had no way to know it is where curl's `--cacert` goes."""
    text = runbooks["INSTALL.md"]
    step = text[text.index("## 7.") :]
    prose = step[: step.index("```")]
    assert "OSPREY_CURL_OPTS" in prose and "--cacert" in prose


def test_no_command_needs_more_than_a_namespace_s_rights(runbooks: dict[str, str]) -> None:
    """The client's team is the namespace's tenant: no block lists or changes anything cluster-wide
    (volumes, every kind there is), and the disks are read from the account, by the claims'
    namespace tag, in a block of the platform's (the self-review of P7b, point 2)."""
    for name, text in runbooks.items():
        # One logical line a command, continuations joined, wherever in the line it stands.
        everything = "".join(command_blocks(text, on_the_platform=True)).replace("\\\n", " ")
        everything = re.sub(r'echo "[^"]*"', "echo", everything)  # words said, not commands run
        assert not re.search(r"kubectl (get|delete) (pv|persistentvolume)s?\b", everything), name
        assert "--namespaced" not in everything, name
        kubectl = re.findall(
            r"(?<!-v )\bkubectl (?!api-resources|config|auth)([^\n|;)]*)", everything
        )
        assert kubectl, name
        for command in kubectl:
            assert '-n "$NS"' in command, (name, command)
        for command in re.findall(r"(?<!-v )\bhelm (?!version)([^\n|;)]*)", everything):
            assert '-n "$NS"' in command, (name, command)
        # Every AWS call names its region: without one, the profile's default answers, and an
        # empty answer from the wrong region reads as nothing there.
        for command in re.findall(r"\baws ([a-z0-9]+ [a-z-]+[^\n|;)]*)", everything):
            assert '--region "$REGION"' in command, (name, command)
    platform = "".join(command_blocks(runbooks["DECOMMISSION.md"], on_the_platform=True))
    rehearsal = "".join(command_blocks(runbooks["DECOMMISSION.md"], on_the_platform=False))
    assert "aws ec2 describe-volumes" in platform and "aws ec2" not in rehearsal


def test_the_install_signs_in_to_the_registry_and_pins_before_it_installs(
    runbooks: dict[str, str],
) -> None:
    """Between the push and the install: the registry's sign-in before the push (the platform's
    block), and a pinned render after it, so the values name ours by the digest the registry holds
    (decision 8), before `helm` reads them; then the check that the Conduit reads Entra ID's
    sign-in (P10 part 2: no sign-in service of ours, the first administrators named in the
    settings)."""
    text = runbooks["INSTALL.md"]
    order = [
        text.index('"$CONFIG" --allow-unpinned\n```'),
        text.index("aws ecr get-login-password"),
        text.index("ospreyflow images push"),
        text.index('-m harness.render --config "$CONFIG"\n```\n\n## 5'),
        text.index("helm upgrade --install"),
        text.index("printenv OSPREY_IDENTITY_PROVIDER"),
    ]
    assert order == sorted(order), order
    assert "aws ecr get-login-password" in "".join(command_blocks(text, on_the_platform=True))
    assert "aws ecr" not in "".join(command_blocks(text, on_the_platform=False))


def test_the_install_runbook_signs_in_with_entra_and_runs_no_realm_step(
    runbooks: dict[str, str],
) -> None:
    """P7b's install runbook, step 6, on Entra ID (ADR-148 Amendment 8; the orchestrator's ruling):
    the client's app registrations and the first administrators the settings name, a check that
    the Conduit reads Entra's settings, and nothing of the realm (no identity module, no
    Keycloak)."""
    text = runbooks["INSTALL.md"]
    step = text[text.index("## 6.") : text.index("## 7.")]
    # The two registrations are asked for before step 5, in what the install needs (R1;
    # `test_the_entra_registrations_are_asked_for_before_the_deployment`).
    named = (
        "00000000-1111-4222-8333-444444444444",  # the tenant
        "50000000-0000-4000-8000-000000000001",  # the first administrator
    )
    assert [n for n in named if n not in step] == []
    assert "printenv OSPREY_IDENTITY_PROVIDER" in step
    assert "keycloak" not in text.lower() and "cloud_platform.identity" not in text


def test_the_install_runbook_says_how_to_recover_when_no_administrator_is_left(
    runbooks: dict[str, str],
) -> None:
    """The orchestrator's review of P10 part 2, item 4(c): an administrator locked out of Admin is
    recovered by naming a person in `first_administrators`, rendering again and restarting the
    Conduit, which gives each one named Admin at start when nobody can manage people (the second
    review's amended ruling; `seed_first_administrators`; its live case,
    `test_when_nobody_can_manage_people_the_named_first_administrators_get_admin_again`)."""
    text = runbooks["INSTALL.md"]
    step = text[text.index("## 6.") : text.index("## 7.")]
    recovery = step[step.index("If no administrator is left") :]
    assert "cloud_platform.claims.first_administrators" in recovery
    assert "only when nobody can manage people" in " ".join(recovery.split())
    assert "grant_first_administrator" in recovery
    # R1: the list is in the ConfigMap, so a render and a restart alone read the old list; the
    # recovery renders pinned, installs the values, then waits for the Conduit.
    (block,) = command_blocks(recovery, on_the_platform=False)
    lines = block.splitlines()
    assert [i for i, x in enumerate(lines) if "harness.render" in x] == [0], block
    assert "--allow-unpinned" not in block
    assert lines[1].startswith('helm upgrade --install "$RELEASE" "$CHART" -n "$NS" -f "$FOLDER/values.yaml"')
    assert 'kubectl -n "$NS" rollout status deploy/api' in lines[-1]
    assert "(step 4)" in recovery


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


def test_a_poc_naming_opensearch_is_refused_in_words() -> None:
    """The poc shape makes no OpenSearch domain, so a deployment that names OpenSearch as its search
    would start a Conduit reaching for a domain that is not there (the orchestrator's review)."""
    from harness.cloud_platform import CloudPlatformNotRenderable

    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    raw["components"]["search"] = "opensearch"
    with pytest.raises(CloudPlatformNotRenderable, match="postgres-fulltext"):
        _artefacts(OspreyConfig.model_validate(raw))


def test_the_standard_shape_leaves_the_configuration_s_copy_as_it_was() -> None:
    """The orchestrator's review: the values carry the deployment's own configuration, whose
    ConfigMap's checksum restarts every pod when it changes. A P7 deployment upgraded to this
    release must not restart for a setting it never wrote, so the default shape is left out of
    the copy; a poc deployment's copy names its shape."""
    for name in ("development", "production"):
        copy_ = yaml.safe_load(_values(_config(name))["files"]["osprey.yaml"])
        assert "shape" not in copy_["cloud_platform"], name
    assert (
        yaml.safe_load(_values(_config())["files"]["osprey.yaml"])["cloud_platform"]["shape"]
        == "poc"
    )
