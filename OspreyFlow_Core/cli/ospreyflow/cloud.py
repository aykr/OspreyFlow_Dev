"""`ospreyflow install --mode small --cloud aws|azure`, run on the operator's own machine
(`06_DECISIONS.md` ADR-114 Amendment 10 points 1, 3 and 4).

1. **Plan, then apply on confirmation**, with OpenTofu, the module for the cloud
   (`deploy/opentofu/small/<cloud>`); the state is kept in `.cloud/small-<cloud>/` of the checkout,
   readable only by its owner — on Azure it holds the database password, so it is a secret to keep.
2. **The server installs itself** on its first boot, from the answers OpenTofu wrote into it.
3. **DNS:** when the answers name a zone, OpenTofu made the record; otherwise the record to make is
   printed, and this waits until the name resolves to the server.
4. **The first administrator's one-time code** is read from the cloud's secret store once the
   server has put it there, shown once, and deleted from the store.

`ospreyflow install --mode enterprise --cloud aws|azure` (ADR-114 Amendment 19) builds the cluster
the same way (`deploy/opentofu/cluster/<cloud>`, state in `.cloud/enterprise-<cloud>/`), then runs
the cluster install from what OpenTofu made: the module's answers (the cluster's storage classes and
every managed service) joined to the operator's, a kubeconfig of the install's own in the state
folder (the operator's `~/.kube/config` is not touched), and the managed services' passwords and
keys read from the cloud's secret store into the cluster install's environment — never onto a
command line, into `osprey.yaml` or onto the screen.

Nothing here holds a cloud credential: OpenTofu and the cloud's own command line use whatever the
operator is signed in as.
"""

from __future__ import annotations

import dataclasses
import json
import os
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import yaml

from .home import CommandRefused

if TYPE_CHECKING:
    import argparse

    from .answers import Answers
    from .main import _Context

#: How long to wait for the name to resolve and for the server to answer (its first boot pulls
#: images and starts every service).
DNS_WAIT_SECONDS = 60 * 60
SERVER_WAIT_SECONDS = 45 * 60
POLL_SECONDS = 15
#: What the server's first boot leaves in the secret store until the code is there.
PENDING = "pending"


class CloudRefused(CommandRefused):
    """The cloud build cannot go on; the message says why and what to do."""


def _resolve(name: str) -> set[str]:
    try:
        found = socket.getaddrinfo(name, 443, proto=socket.IPPROTO_TCP)
        return {str(info[4][0]) for info in found}
    except OSError:
        return set()


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - https, our name
            return bool(response.status < 500)
    except (urllib.error.URLError, OSError):
        return False


_sleep: Callable[[float], None] = time.sleep
_now: Callable[[], float] = time.monotonic


def _wait(what: str, ready: Callable[[], bool], seconds: int) -> None:
    deadline = _now() + seconds
    while not ready():
        if _now() >= deadline:
            raise CloudRefused(f"gave up waiting for {what} after {seconds // 60} minutes")
        _sleep(POLL_SECONDS)


def tofu_variables(answers: Answers, *, repository: str, release: str | None) -> list[str]:
    cloud = answers.cloud
    for needed in ("region", "domain"):
        if not cloud.get(needed):
            raise CloudRefused(f"the answers give no cloud {needed}; a Small server needs one")
    values: dict[str, str] = {
        "region": cloud["region"],
        "domain": cloud["domain"],
        "repository": repository,
        "release": release or "",
        "dns_zone": cloud.get("dns_zone", ""),
        "admin_email": cloud.get("admin_email", ""),
    }
    if cloud.get("size"):
        values["size"] = cloud["size"]
    return [f"-var={key}={value}" for key, value in values.items()]


def _code_commands(provider: str, outputs: dict[str, Any]) -> tuple[list[str], list[str]]:
    """How to read, and then delete, the first administrator's code from the secret store."""
    if provider == "aws":
        secret, region = outputs["first_admin_secret"], outputs["region"]
        return (
            ["aws", "secretsmanager", "get-secret-value", "--secret-id", secret, "--region",
             region, "--query", "SecretString", "--output", "text"],
            ["aws", "secretsmanager", "delete-secret", "--secret-id", secret, "--region", region,
             "--force-delete-without-recovery"],
        )  # fmt: skip
    vault = outputs["key_vault"]
    return (
        ["az", "keyvault", "secret", "show", "--vault-name", vault, "--name", "first-admin-code",
         "--query", "value", "--output", "tsv"],
        ["az", "keyvault", "secret", "delete", "--vault-name", vault, "--name",
         "first-admin-code"],
    )  # fmt: skip


def build_small(ctx: _Context, args: argparse.Namespace, answers: Answers) -> int:
    provider = str(args.cloud)
    module = ctx.product / "deploy" / "opentofu" / "small" / provider
    if not module.is_dir():
        raise CloudRefused(f"this checkout has no OpenTofu module for {provider} ({module})")
    state = ctx.product / ".cloud" / f"small-{provider}"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    code, remote = ctx.capture(["git", "-C", str(ctx.product), "remote", "get-url", "origin"])
    repository = remote.strip() if code == 0 else ""
    if not repository:
        raise CloudRefused(
            "the checkout has no `origin` remote, so the server would have nothing to install from"
        )
    from .main import _release_at_head

    variables = tofu_variables(answers, repository=repository, release=_release_at_head(ctx))
    tofu_env = {"TF_DATA_DIR": str(state / ".terraform")}
    chdir = f"-chdir={module}"
    state_file = f"-state={state / 'terraform.tfstate'}"
    plan_file = str(state / "plan.bin")

    def tofu(name: str, *argv: str) -> None:
        ctx.step(name, ["tofu", chdir, *argv], env=tofu_env)

    tofu("prepare OpenTofu", "init", "-input=false")
    tofu("plan the server", "plan", "-input=false", state_file, f"-out={plan_file}", *variables)
    if not args.yes and ctx.ask("Build this in your cloud account? (yes/no)", "no") != "yes":
        print("Nothing was built. The plan is above; run the install again to build it.")
        return 0
    tofu("build the server", "apply", "-input=false", state_file, plan_file)
    code, said = ctx.capture(["tofu", chdir, "output", state_file, "-json"], env=tofu_env)
    if code != 0:
        raise CloudRefused("OpenTofu built the server but would not say what it built")
    outputs = {key: value["value"] for key, value in json.loads(said).items()}
    address, domain = str(outputs["address"]), str(outputs["domain"])

    if not answers.cloud.get("dns_zone"):
        print(f"\nPoint your name at the server: an A record for {domain}, value {address}.")
        print("Waiting for it to resolve (it can take a few minutes after you make it)…")
        _wait(f"{domain} to resolve to {address}", lambda: address in _resolve(domain),
              DNS_WAIT_SECONDS)  # fmt: skip
    print(f"Waiting for the server to install itself and answer at https://{domain} …")
    _wait(f"https://{domain} to answer", lambda: _answers(f"https://{domain}/"),
          SERVER_WAIT_SECONDS)  # fmt: skip

    read, delete = _code_commands(provider, outputs)
    holder: dict[str, str] = {}

    def code_ready() -> bool:
        status, value = ctx.capture(read)
        holder["code"] = value.strip()
        return status == 0 and holder["code"] not in ("", PENDING)

    _wait("the first administrator's code", code_ready, SERVER_WAIT_SECONDS)
    ctx.step("remove the code from the secret store", delete)
    print()
    print(f"OspreyFlow is installed at https://{domain}")
    print(f"The first administrator signs in as admin with this one-time code: {holder['code']}")
    print("It is shown once and is gone from the secret store; they choose a password at sign-in.")
    print(f"OpenTofu's state is in {state}: keep it, privately — it is how the server is changed.")
    return 0


# ---- Enterprise: the cluster (ADR-114 Amendment 19) --------------------------------------------


def cluster_variables(answers: Answers) -> list[str]:
    cloud = answers.cloud
    for needed in ("region", "domain"):
        if not cloud.get(needed):
            raise CloudRefused(f"the answers give no cloud {needed}; a cluster needs one")
    if not answers.api_cidrs:
        raise CloudRefused(
            "the answers give no cloud api_cidrs: the addresses this machine and the other "
            "operators work from, the only ones the cluster's API will answer"
        )
    values: dict[str, str] = {
        "region": cloud["region"],
        "domain": cloud["domain"],
        "namespace": answers.cluster.get("namespace", "ospreyflow"),
        "admin_email": cloud.get("admin_email", ""),
        "api_cidrs": json.dumps(list(answers.api_cidrs)),
    }
    if cloud.get("size"):
        values["size"] = cloud["size"]
    return [f"-var={key}={value}" for key, value in values.items()]


def _check_cluster_answers(provider: str, answers: Answers) -> None:
    given = answers.cloud.get("provider")
    if given and given != provider:
        raise CloudRefused(
            f"the answers' cloud provider is {given}, but --cloud {provider} was given; "
            "they must agree"
        )
    if answers.external:
        raise CloudRefused(
            "with --cloud, OpenTofu makes the managed services and names them itself: take "
            "external: out of the answers (or leave out --cloud to install onto services of "
            "your own)"
        )
    made = sorted({"storage_class", "shared_storage_class"} & set(answers.cluster))
    if made:
        raise CloudRefused(
            f"with --cloud, OpenTofu makes the storage classes: take {', '.join(made)} out of "
            "cluster: in the answers"
        )


def _secret_commands(provider: str, outputs: dict[str, Any]) -> dict[str, tuple[str, list[str]]]:
    """Each environment variable the cluster install reads, with the secret it comes from and the
    command that reads that secret's value."""
    if provider == "aws":
        region = str(outputs["region"])

        def read(secret: str) -> list[str]:
            return ["aws", "secretsmanager", "get-secret-value", "--secret-id", secret,
                    "--region", region, "--query", "SecretString", "--output", "text"]  # fmt: skip

        names = {"OSPREY_POSTGRES_PASSWORD": "database_password_secret",
                 "VALKEY_PASSWORD": "valkey_token_secret"}  # fmt: skip
    else:

        def read(secret: str) -> list[str]:
            return ["az", "keyvault", "secret", "show", "--id", secret, "--query", "value",
                    "--output", "tsv"]  # fmt: skip

        names = {"OSPREY_POSTGRES_PASSWORD": "database_password_secret",
                 "VALKEY_PASSWORD": "valkey_token_secret",
                 "AZURE_STORAGE_KEY": "media_key_secret"}  # fmt: skip
    return {env: (str(outputs[key]), read(str(outputs[key]))) for env, key in names.items()}


def _read_secrets(ctx: _Context, provider: str, outputs: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for env, (secret, argv) in _secret_commands(provider, outputs).items():
        code, said = ctx.capture(argv)
        value = said.strip() if code == 0 else ""
        if value and provider == "aws" and env == "OSPREY_POSTGRES_PASSWORD":
            # RDS keeps its password as JSON: {"username": …, "password": …}.
            try:
                held = json.loads(value)
                value = str(held["password"]) if isinstance(held, dict) else ""
            except (ValueError, KeyError):
                value = ""
        if not value:
            raise CloudRefused(
                f"could not read {env}'s value from {secret}: check this machine's signed-in "
                "identity may read it, and run the install again (OpenTofu will change nothing)"
            )
        values[env] = value
    return values


def _kubeconfig_steps(provider: str, outputs: dict[str, Any], path: str) -> list[list[str]]:
    name = str(outputs["cluster_name"])
    if provider == "aws":
        return [["aws", "eks", "update-kubeconfig", "--name", name, "--region",
                 str(outputs["region"]), "--kubeconfig", path]]  # fmt: skip
    return [
        ["az", "aks", "get-credentials", "--name", name, "--resource-group",
         str(outputs["resource_group"]), "--file", path, "--overwrite-existing"],
        # AKS here has no local accounts: kubectl signs in as the operator's own Entra ID identity.
        ["kubelogin", "convert-kubeconfig", "-l", "azurecli", "--kubeconfig", path],
    ]  # fmt: skip


def build_enterprise(ctx: _Context, args: argparse.Namespace, answers: Answers) -> int:
    provider = str(args.cloud)
    _check_cluster_answers(provider, answers)
    variables = cluster_variables(answers)
    module = ctx.product / "deploy" / "opentofu" / "cluster" / provider
    if not module.is_dir():
        raise CloudRefused(f"this checkout has no OpenTofu module for {provider} ({module})")
    state = ctx.product / ".cloud" / f"enterprise-{provider}"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    tofu_env = {"TF_DATA_DIR": str(state / ".terraform")}
    chdir = f"-chdir={module}"
    state_file = f"-state={state / 'terraform.tfstate'}"
    plan_file = str(state / "plan.bin")

    def tofu(name: str, *argv: str) -> None:
        ctx.step(name, ["tofu", chdir, *argv], env=tofu_env)

    tofu("prepare OpenTofu", "init", "-input=false")
    tofu("plan the cluster", "plan", "-input=false", state_file, f"-out={plan_file}", *variables)
    if not args.yes and ctx.ask("Build this in your cloud account? (yes/no)", "no") != "yes":
        print("Nothing was built. The plan is above; run the install again to build it.")
        return 0
    tofu("build the cluster", "apply", "-input=false", state_file, plan_file)
    code, said = ctx.capture(["tofu", chdir, "output", state_file, "-json"], env=tofu_env)
    if code != 0:
        raise CloudRefused("OpenTofu built the cluster but would not say what it built")
    outputs = {key: value["value"] for key, value in json.loads(said).items()}

    made = yaml.safe_load(str(outputs["install_answers"])) or {}
    answers = dataclasses.replace(
        answers,
        cluster={**answers.cluster, **{k: str(v) for k, v in made.get("cluster", {}).items()}},
        external=made.get("external", {}),
    )
    kubeconfig = str(state / "kubeconfig")
    for argv in _kubeconfig_steps(provider, outputs, kubeconfig):
        ctx.step("point the install at the cluster", argv)
    environ = {"KUBECONFIG": kubeconfig, **_read_secrets(ctx, provider, outputs)}

    from .main import _install_on_cluster

    _install_on_cluster(ctx, args, answers, env=environ)
    print(f"OpenTofu's state is in {state}: keep it, privately — it is how the cluster is changed,")
    print("and it holds secrets. kubectl reaches the cluster with KUBECONFIG=" + kubeconfig + ".")
    return 0
