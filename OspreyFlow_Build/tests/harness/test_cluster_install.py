"""Enterprise's install onto a cluster (`harness.cluster_install`) — ADR-114 Amendment 16.

Against a fake `kubectl` and `helm` that refuse what the real ones refuse: a namespace or Secret that
is not there is `NotFound`, a second account of the same name is a `Conflict`, a chart that does not
come up fails the step. The identity provider's own settings are proved live (the k3s proof in the
amendment); here they are a recorded step.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness import cluster_install
from harness.cluster_install import ClusterInstallFailed, install

CONFIG = {
    "profile": "cluster",
    "components": {"analytics_engine": "clickhouse"},
    "network": {"public_origin": "https://osprey.example.org"},
    "reporting": {"sync": True, "superset": True},
    "cluster": {"namespace": "intel", "shared_storage_class": "efs-sc"},
    "external": {
        "postgres": {"host": "db.example.internal"},
        "valkey": {"host": "cache.example.internal"},
        "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
    },
    "map": {"default": "osm", "providers": [{"id": "osm", "label": "OSM", "kind": "vector",
            "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
            "source": "file:///data/tiles/osm.pmtiles", "proxy": "none",
            "attribution": "OpenStreetMap contributors"}]},
}  # fmt: skip
MANAGED = {"OSPREY_POSTGRES_PASSWORD": "managed-db-password"}


class FakeKube:
    def __init__(self) -> None:
        self.namespaces: set[str] = set()
        self.secret: dict[str, str] | None = None
        self.users: set[str] = set()
        self.calls: list[tuple[list[str], str | None]] = []
        self.helm_fails = False
        self.forwarded: list[str] = []

    def run(self, argv: Sequence[str], *, stdin: str | None = None) -> tuple[int, str, str]:
        argv = list(argv)
        self.calls.append((argv, stdin))
        if argv[:3] == ["kubectl", "get", "namespace"]:
            found = argv[3] in self.namespaces
            return (0, argv[3], "") if found else (1, "", f'namespaces "{argv[3]}" not found')
        if argv[:3] == ["kubectl", "create", "namespace"]:
            if argv[3] in self.namespaces:
                return 1, "", "AlreadyExists"
            self.namespaces.add(argv[3])
            return 0, "", ""
        if "secret" in argv and "get" in argv:
            if self.secret is None:
                return 1, "", 'Error from server (NotFound): secrets "ospreyflow-secrets" not found'
            data = {k: base64.b64encode(v.encode()).decode() for k, v in self.secret.items()}
            return 0, json.dumps({"data": data}), ""
        if argv[:3] == ["kubectl", "apply", "-f"]:
            manifest = json.loads(stdin or "")
            if manifest["metadata"]["namespace"] not in self.namespaces:
                return 1, "", 'namespaces "intel" not found'
            self.secret = dict(manifest["stringData"])
            return 0, "secret/ospreyflow-secrets configured", ""
        if argv[0] == "helm":
            return (1, "", "Error: context deadline exceeded") if self.helm_fails else (0, "", "")
        if "exec" in argv:
            user = json.loads(stdin or "")
            if user["username"] in self.users:
                return 1, "", "Conflict detected: User exists with same username"
            self.users.add(user["username"])
            return 0, "", ""
        if "service" in argv and "proxy" in argv:
            return 0, "203.0.113.7", ""
        raise AssertionError(f"unexpected call {argv}")

    def port_forward(self, namespace: str, target: str, port: int) -> AbstractContextManager[int]:
        self.forwarded.append(target)

        @contextmanager
        def forward() -> Iterator[int]:
            yield 18080

        return forward()


def _identity(record: list[Mapping[str, str]]) -> cluster_install.ConfigureIdentity:
    def configure(kube: Any, namespace: str, config: Any, values: Mapping[str, str]) -> list[str]:
        record.append(dict(values))
        return ["identity configured"]

    return configure


def _resolver(ref: str) -> str:
    return "sha256:" + "0" * 64


def _install(tmp_path: Path, kube: FakeKube, environ: Mapping[str, str] = MANAGED,
             seen: list[Mapping[str, str]] | None = None, **more: Any) -> cluster_install.Installed:  # fmt: skip
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return install(config, out_root=tmp_path / "generated", kube=kube, environ=environ,
                   resolver=_resolver, configure_identity=_identity(seen if seen is not None else []),
                   **more)  # fmt: skip


def test_a_fresh_install_makes_everything_in_order(tmp_path: Path) -> None:
    kube, seen = FakeKube(), []
    done = _install(tmp_path, kube, seen=seen)
    order = [c[0][0] + " " + c[0][1] for c in kube.calls]
    assert order.index("kubectl create") < order.index("kubectl apply") < order.index("helm upgrade")
    helm = next(argv for argv, _ in kube.calls if argv[0] == "helm")
    assert helm[:4] == ["helm", "upgrade", "--install", "ospreyflow"]
    assert helm[helm.index("-n") + 1] == "intel" and "--wait" in helm
    assert helm[helm.index("-f") + 1] == str(tmp_path / "generated" / "cluster" / "values.yaml")
    assert (tmp_path / "generated" / "cluster" / "versions.lock").is_file()
    assert done.first_admin_code is not None and done.address == "203.0.113.7"
    # The identity step had the Secret and the rendered environment together.
    assert seen[0]["OSPREY_KEYCLOAK_ADMIN_PASSWORD"] == kube.secret["OSPREY_KEYCLOAK_ADMIN_PASSWORD"]  # type: ignore[index]
    assert seen[0]["ARCADEDB_HA"] == "true"


def test_the_secret_holds_every_key_the_workloads_read(tmp_path: Path) -> None:
    kube = FakeKube()
    _install(tmp_path, kube)
    values = yaml.safe_load((tmp_path / "generated" / "cluster" / "values.yaml").read_text())
    assert kube.secret is not None and set(values["secrets"]["keys"]) <= set(kube.secret)
    assert kube.secret["POSTGRES_HOST"] == "db.example.internal"
    assert kube.secret["OSPREY_POSTGRES_PASSWORD"] == "managed-db-password"
    assert kube.secret["OSPREY_ARCADEDB_PASSWORD"] == kube.secret["ARCADEDB_ROOT_PASSWORD"]
    assert kube.secret["OSPREY_OIDC_CLIENT_SECRET"] == kube.secret["OIDC_TOKEN_EXCHANGE_CLIENT_SECRET"]


def test_a_second_run_changes_no_password_and_replaces_no_account(tmp_path: Path) -> None:
    kube = FakeKube()
    _install(tmp_path, kube)
    first = dict(kube.secret or {})
    again = _install(tmp_path, kube, environ={})  # the managed password kept, not asked again
    assert kube.secret == first
    assert again.first_admin_code is None
    assert "first administrator admin already exists; unchanged" in again.lines
    assert "namespace intel kept" in again.lines


def test_a_managed_password_from_the_environment_replaces_the_kept_one(tmp_path: Path) -> None:
    kube = FakeKube()
    _install(tmp_path, kube)
    _install(tmp_path, kube, environ={"OSPREY_POSTGRES_PASSWORD": "rotated"})
    assert kube.secret is not None and kube.secret["OSPREY_POSTGRES_PASSWORD"] == "rotated"


def test_a_managed_password_neither_given_nor_kept_is_refused_before_anything_is_made(
    tmp_path: Path,
) -> None:
    kube = FakeKube()
    with pytest.raises(ClusterInstallFailed, match="OSPREY_POSTGRES_PASSWORD is not set"):
        _install(tmp_path, kube, environ={})
    assert kube.secret is None and not [c for c in kube.calls if c[0][0] == "helm"]


def test_a_chart_that_does_not_come_up_stops_the_install(tmp_path: Path) -> None:
    kube = FakeKube()
    kube.helm_fails = True
    seen: list[Mapping[str, str]] = []
    with pytest.raises(ClusterInstallFailed, match="installing the chart: Error: context deadline"):
        _install(tmp_path, kube, seen=seen)
    assert not seen and not kube.users


def test_no_secret_reaches_a_command_line_or_the_lines_said(tmp_path: Path) -> None:
    kube = FakeKube()
    done = _install(tmp_path, kube)
    secrets = {v for k, v in (kube.secret or {}).items()
               if k.endswith(("PASSWORD", "SECRET", "TOKEN", "_KEY")) and len(v) > 8}  # fmt: skip
    argvs = " ".join(" ".join(argv) for argv, _ in kube.calls)
    said = " ".join(done.lines)
    assert secrets and not [s for s in secrets if s in argvs or s in said]
    assert done.first_admin_code not in argvs  # the account went on stdin


def test_a_site_s_own_values_follow_the_rendered_ones(tmp_path: Path) -> None:
    kube = FakeKube()
    site = tmp_path / "site.yaml"
    site.write_text("storage: {sharedSize: 1Ti}\n", encoding="utf-8")
    _install(tmp_path, kube, extra_values=[site])
    helm = next(argv for argv, _ in kube.calls if argv[0] == "helm")
    files = [helm[i + 1] for i, a in enumerate(helm) if a == "-f"]
    assert files[-1] == str(site) and files[0].endswith("values.yaml")


def test_another_profile_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "osprey.yaml"
    config.write_text("profile: small\n", encoding="utf-8")
    with pytest.raises(ClusterInstallFailed, match="profile: cluster"):
        install(config, out_root=tmp_path, kube=FakeKube(), environ={}, resolver=_resolver)
