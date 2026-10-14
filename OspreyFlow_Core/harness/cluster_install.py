"""Enterprise's install onto a Kubernetes cluster, run from the operator's machine with `kubectl`
and `helm` pointed at it (`05_DEPLOYMENT.md` §3b, ADR-114 Amendment 16).

    python -m harness.cluster_install --config osprey.yaml [--values site.yaml]

In order, each step safe to run again:

1. **Render** the chart's values and lock (`deploy/generated/cluster/`).
2. **The namespace**, made if missing.
3. **The Secret** (`ospreyflow-secrets`): what Lite's `apply` writes into its env file. A value the
   Secret already holds is kept — Keycloak's administrator and database passwords cannot change
   under a running deployment — and only what is missing is minted; what the configuration decides
   (addresses, the managed services' settings) is written each time, and a managed service's own
   password is read from the environment (or kept). Sent to `kubectl` on stdin; never written to
   disk, never printed.
4. **The chart**, `helm upgrade --install … --wait`.
5. **The identity provider**, through a port-forward to Keycloak (it is published only by name,
   and the names may not point at the cluster yet): the Conduit's client secrets and service-account
   roles, then `register_sign_in.ensure_identity` — the same step every deployment runs.
6. **The first administrator**, with a one-time code, made inside Keycloak's pod with its own admin
   tool (`kubectl exec`, the account on stdin). Never replaced: a second run says it exists.
7. **Where it answers**: the load balancer's address, and the names to point at it.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from harness.cluster import SECRET_NAME
from harness.first_admin import first_administrator, one_time_code
from harness.images import DigestResolver
from harness.realm import CONDUIT_CLIENT_ID, generate_client_secret
from harness.render import REPO_ROOT, load_config, render
from harness.site import sites
from ontology.handling import load_uk_le_scheme
from schemas.deployment import OspreyConfig, Profile

CHART = REPO_ROOT / "deploy" / "helm" / "ospreyflow"
RELEASE = "ospreyflow"
REALM = "osprey"

#: Made with Keycloak's own admin tool inside its pod: the bootstrap administrator's credentials
#: are in the pod's environment, the account arrives on stdin. `kcadm.sh` refuses an existing
#: username ("Conflict detected"), so an account is never replaced.
KCADM_CREATE_FROM_STDIN = (
    "/opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 "
    '--realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" '
    '--password "$KC_BOOTSTRAP_ADMIN_PASSWORD" --config /tmp/kcadm.config >/dev/null '
    f"&& /opt/keycloak/bin/kcadm.sh create users -r {REALM} -f - --config /tmp/kcadm.config"
)


#: `(kube, namespace, config, settings) -> lines`: the identity provider's settings (step 5).
ConfigureIdentity = Callable[["Kube", str, OspreyConfig, Mapping[str, str]], list[str]]


class ClusterInstallFailed(RuntimeError):
    """A step did not complete; the message says which, and what the tool said."""


class Kube(Protocol):
    """`kubectl` and `helm`, as the install uses them (a seam for the tests)."""

    def run(self, argv: Sequence[str], *, stdin: str | None = None) -> tuple[int, str, str]: ...

    def port_forward(
        self, namespace: str, target: str, port: int
    ) -> AbstractContextManager[int]: ...


class SystemKube:
    def run(self, argv: Sequence[str], *, stdin: str | None = None) -> tuple[int, str, str]:
        done = subprocess.run(  # noqa: S603 - the operator's own kubectl and helm
            list(argv), input=stdin, capture_output=True, text=True, check=False, timeout=3600
        )
        return done.returncode, done.stdout, done.stderr

    def port_forward(self, namespace: str, target: str, port: int) -> AbstractContextManager[int]:
        return _forwarding(namespace, target, port)


@contextmanager
def _forwarding(namespace: str, target: str, port: int) -> Iterator[int]:
    local = _free_port()
    forward = subprocess.Popen(  # noqa: S603
        ["kubectl", "-n", namespace, "port-forward", target, f"{local}:{port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(60):
            if forward.poll() is not None:
                said = forward.stderr.read() if forward.stderr else ""
                raise ClusterInstallFailed(f"the port-forward to {target} stopped: {said}")
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", local)) == 0:
                    break
            time.sleep(0.5)
        yield local
    finally:
        forward.terminate()
        forward.wait(timeout=10)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Installed:
    """What the install did, line by line, and what the operator needs from it."""

    lines: list[str] = field(default_factory=list)
    first_admin_code: str | None = None
    address: str | None = None


def _say(kube: Kube, step: str, argv: Sequence[str], *, stdin: str | None = None) -> str:
    code, out, err = kube.run(argv, stdin=stdin)
    if code != 0:
        said = (err or out).strip().splitlines()
        raise ClusterInstallFailed(f"{step}: {said[-1] if said else f'exit {code}'}")
    return out


#: Written by the install each time from the configuration, never kept from an earlier Secret.
def _derived(
    config: OspreyConfig, environ: Mapping[str, str], kept: Mapping[str, str]
) -> dict[str, str]:
    from harness.apply import managed_service_lines

    # A managed service's own password comes from the environment, or is kept from the Secret.
    sources = {**kept, **environ}
    lines = managed_service_lines(
        config,
        environ=sources,
        minted="unused: a cluster's Postgres is managed",
        object_store_password=kept.get("OSPREY_MINIO_PASSWORD") or generate_client_secret(),
    )
    derived = _pairs(lines)
    if "VALKEY_PASSWORD" in sources:
        derived["VALKEY_PASSWORD"] = sources["VALKEY_PASSWORD"]
    keycloak = f"http://keycloak:8080/realms/{REALM}"
    derived.update(
        {
            "OIDC_JWKS_URL": f"{keycloak}/protocol/openid-connect/certs",
            "OIDC_TOKEN_EXCHANGE_URL": f"{keycloak}/protocol/openid-connect/token",
            "OIDC_TOKEN_EXCHANGE_CLIENT_ID": CONDUIT_CLIENT_ID,
            "OIDC_ADMIN_USERS_URL": f"http://keycloak:8080/admin/realms/{REALM}/users",
        }
    )
    return derived


def _minted(config: OspreyConfig, environ: Mapping[str, str]) -> dict[str, str]:
    """Every secret a fresh deployment needs, freshly made; a kept value replaces each."""
    from harness.apply import analytics_secret_lines, mail_secret_lines, provider_secret_lines
    from harness.reporting import reporting_secrets

    client = generate_client_secret()
    arcadedb = generate_client_secret()
    minted = {
        "OSPREY_OIDC_CLIENT_SECRET": client,
        "OIDC_TOKEN_EXCHANGE_CLIENT_SECRET": client,
        "OSPREY_KEYCLOAK_ADMIN_PASSWORD": generate_client_secret(),
        "OSPREY_KEYCLOAK_DB_PASSWORD": generate_client_secret(),
        "OSPREY_ARCADEDB_PASSWORD": arcadedb,
        "ARCADEDB_ROOT_PASSWORD": arcadedb,
        "OSPREY_ARCADEDB_CLUSTER_TOKEN": generate_client_secret(),
    }
    minted.update(_pairs(reporting_secrets(config) + analytics_secret_lines(config)))
    minted.update(
        _pairs(mail_secret_lines(config, environ) + provider_secret_lines(config, environ))
    )
    return minted


def _pairs(text: str) -> dict[str, str]:
    return {
        name.strip(): value
        for name, _, value in (line.partition("=") for line in text.splitlines())
        if name.strip() and not name.startswith("#")
    }


def secret_values(
    config: OspreyConfig,
    *,
    values: Mapping[str, object],
    environ: Mapping[str, str],
    kept: Mapping[str, str],
) -> dict[str, str]:
    """The Secret's contents: freshly minted, then what the Secret already held, then what the
    configuration decides — so a re-run changes no password and every address follows the file."""
    secrets_section = values["secrets"]
    assert isinstance(secrets_section, dict)
    from harness.apply import ApplyRefused

    try:
        derived = _derived(config, environ, kept)
    except ApplyRefused as refused:
        raise ClusterInstallFailed(str(refused)) from None
    pairs = {**_minted(config, environ), **kept, **derived}
    for key, default in dict(secrets_section.get("defaults", {})).items():
        pairs.setdefault(str(key), str(default))
    missing = sorted(set(secrets_section.get("keys", [])) - set(pairs))
    if missing:
        raise ClusterInstallFailed(f"the Secret would not hold {', '.join(missing)}")
    return pairs


def _existing_secret(kube: Kube, namespace: str) -> dict[str, str]:
    code, out, err = kube.run(
        ["kubectl", "-n", namespace, "get", "secret", SECRET_NAME, "-o", "json"]
    )
    if code != 0:
        if "NotFound" in err or "not found" in err:
            return {}
        raise ClusterInstallFailed(f"reading the Secret: {err.strip() or out.strip()}")
    data = json.loads(out).get("data") or {}
    return {key: base64.b64decode(value).decode() for key, value in data.items()}


def _secret_manifest(namespace: str, pairs: Mapping[str, str]) -> str:
    return json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": SECRET_NAME, "namespace": namespace},
            "type": "Opaque",
            "stringData": dict(sorted(pairs.items())),
        }
    )


def install(
    config_path: Path,
    *,
    out_root: Path,
    kube: Kube,
    environ: Mapping[str, str],
    resolver: DigestResolver | None = None,
    allow_unpinned: bool = False,
    extra_values: Sequence[Path] = (),
    admin_email: str | None = None,
    timeout: str = "30m",
    configure_identity: ConfigureIdentity | None = None,
) -> Installed:
    config = load_config(config_path)
    if config.profile is not Profile.CLUSTER:
        raise ClusterInstallFailed(
            f"{config_path} is profile {config.profile.value!r}; the cluster install is for "
            "profile: cluster"
        )
    done = Installed()
    namespace = config.cluster.namespace

    # 1. Render.
    rendered = render(config, resolver=resolver, allow_unpinned=allow_unpinned)
    folder = out_root / "cluster"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in rendered.artefacts.items():
        (folder / name).write_text(text, encoding="utf-8")
    values = yaml.safe_load(rendered.artefacts["values.yaml"])
    done.lines.append(f"rendered {folder / 'values.yaml'} and its lock")

    # 2. The namespace.
    if kube.run(["kubectl", "get", "namespace", namespace])[0] != 0:
        _say(kube, "making the namespace", ["kubectl", "create", "namespace", namespace])
        done.lines.append(f"namespace {namespace} made")
    else:
        done.lines.append(f"namespace {namespace} kept")

    # 3. The Secret.
    kept = _existing_secret(kube, namespace)
    pairs = secret_values(config, values=values, environ=environ, kept=kept)
    _say(kube, "writing the Secret", ["kubectl", "apply", "-f", "-"],
         stdin=_secret_manifest(namespace, pairs))  # fmt: skip
    added = sorted(set(pairs) - set(kept))
    done.lines.append(
        f"Secret {SECRET_NAME}: {len(kept)} kept, {len(added)} added"
        if kept
        else f"Secret {SECRET_NAME} made ({len(pairs)} settings)"
    )

    # 4. The chart.
    helm = ["helm", "upgrade", "--install", RELEASE, str(CHART), "-n", namespace,
            "-f", str(folder / "values.yaml")]  # fmt: skip
    for extra in extra_values:
        helm += ["-f", str(extra)]
    helm += ["--wait", "--timeout", timeout]
    _say(kube, "installing the chart", helm)
    done.lines.append(f"chart installed as {RELEASE} in {namespace}; every workload ready")

    # 5. The identity provider.
    identity = configure_identity or _configure_identity
    done.lines += identity(kube, namespace, config, {**values["environment"], **pairs})

    # 6. The first administrator.
    code = one_time_code()
    user = first_administrator("admin", code=code, scheme=load_uk_le_scheme(), email=admin_email)
    status, out, err = kube.run(
        ["kubectl", "-n", namespace, "exec", "-i", "keycloak-0", "-c", "keycloak", "--",
         "sh", "-c", KCADM_CREATE_FROM_STDIN],
        stdin=json.dumps(user),
    )  # fmt: skip
    if status == 0:
        done.first_admin_code = code
        done.lines.append("first administrator admin made")
    elif "Conflict" in err or "exists" in err:
        done.lines.append("first administrator admin already exists; unchanged")
    else:
        said = (err or out).strip().splitlines()
        raise ClusterInstallFailed(
            f"making the first administrator: {said[-1] if said else f'exit {status}'}"
        )

    # 7. Where it answers.
    status, out, _ = kube.run(
        ["kubectl", "-n", namespace, "get", "service", "proxy", "-o",
         "jsonpath={.status.loadBalancer.ingress[0].ip}{.status.loadBalancer.ingress[0].hostname}"]
    )  # fmt: skip
    done.address = (out.strip() or None) if status == 0 else None
    return done


def _configure_identity(
    kube: Kube, namespace: str, config: OspreyConfig, values: Mapping[str, str]
) -> list[str]:
    from harness import keycloak_admin
    from harness.register_sign_in import ensure_identity

    with kube.port_forward(namespace, "service/keycloak", 8080) as port:
        issuer = f"http://127.0.0.1:{port}"
        keycloak_admin.grant_service_account_roles(
            issuer=issuer,
            realm=REALM,
            admin_user=values.get("OSPREY_KEYCLOAK_ADMIN", "admin"),
            admin_password=values["OSPREY_KEYCLOAK_ADMIN_PASSWORD"],
            client_secret=values["OSPREY_OIDC_CLIENT_SECRET"],
        )
        token = keycloak_admin.admin_token(
            issuer=issuer,
            admin_user=values.get("OSPREY_KEYCLOAK_ADMIN", "admin"),
            admin_password=values["OSPREY_KEYCLOAK_ADMIN_PASSWORD"],
        )
        lines = ensure_identity(
            issuer=issuer, realm=REALM, token=token, config=config, values=values
        )
    return ["the Conduit's client secrets and service-account roles set", *lines]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness.cluster_install", description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, default=REPO_ROOT / "deploy" / "generated")
    parser.add_argument(
        "--values", type=Path, action="append", default=[],
        help="a site's own chart values, applied over the rendered ones",
    )  # fmt: skip
    parser.add_argument("--email", help="the first administrator's email")
    parser.add_argument("--timeout", default="30m")
    parser.add_argument(
        "--allow-unpinned", action="store_true",
        help="a developer's flag: images by tag where no digest can be found",
    )  # fmt: skip
    args = parser.parse_args(argv)
    try:
        done = install(
            args.config, out_root=args.out_root, kube=SystemKube(), environ=os.environ,
            allow_unpinned=args.allow_unpinned, extra_values=args.values,
            admin_email=args.email, timeout=args.timeout,
        )  # fmt: skip
    except ClusterInstallFailed as failed:
        print(f"The install stopped: {failed}", file=sys.stderr)
        return 1
    for line in done.lines:
        print(f"  - {line}")
    config = load_config(args.config)
    names = sites(config)
    print()
    if done.address:
        print(f"OspreyFlow answers at {done.address}. Point these names at it:")
    else:
        print("The load balancer has no address yet (`kubectl get service proxy`); point at it:")
    print(
        f"  {names.host}, id.{names.host}"
        + (f", bi.{names.host}" if config.reporting.superset else "")
    )
    if done.first_admin_code:
        print(f"\nThe first administrator is admin. Their one-time code: {done.first_admin_code}")
        print("They choose their own password at their first sign-in; the code is not kept.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
