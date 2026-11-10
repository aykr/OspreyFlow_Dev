"""`profile: cloud-platform` (`spec/06_DECISIONS.md` ADR-148 decisions 1–5, 7, 8, 12): the chart's
values into a namespace on a shared platform, and that namespace's Terraform. The chart's own
manifests from these values are held to the platform's rules by `make cp-policy-check`
(`tests/cp_policy_check/`); these are the values' and the Terraform's promises.

What a mistake would do, and the case that catches it (rule 12):
- a managed store's detail read from a secret the Terraform never writes, or a key it does not
  hold — `test_every_secret_the_values_read_is_one_the_terraform_writes`;
- a store's password handed to a pod that does not read the store —
  `test_only_the_readers_are_given_the_managed_stores_details`;
- a `$(VAR)` in a command Kubernetes leaves unexpanded (defined after it, or escaped) —
  `test_a_variable_a_command_names_is_defined_before_it`;
- a host an enabled feature reaches left open or silently dropped —
  `test_an_enabled_host_without_networks_is_refused_in_words`;
- our image pinned by the source's digest though the registry's copy differs —
  `test_ours_are_refused_until_the_registry_holds_their_copy`.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest
import yaml
from harness.cloud_platform import CloudPlatformNotRenderable, managed_variables
from harness.cloud_platform.settings import load_platform
from harness.render import UnpinnedImagesError, load_config, render
from pydantic import ValidationError
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

REGISTRY = "123456789012.dkr.ecr.eu-west-2.amazonaws.com"


def _config(name: str = "development", **changes: Any) -> OspreyConfig:
    raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
    for key, value in changes.items():
        raw[key] = {**raw.get(key, {}), **value} if isinstance(value, dict) else value
    return OspreyConfig.model_validate(raw)


def _artefacts(config: OspreyConfig) -> dict[str, str]:
    return render(config, resolver=_resolver).artefacts


def _values(config: OspreyConfig) -> dict[str, Any]:
    return yaml.safe_load(_artefacts(config)["values.yaml"])


def _pods(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [*values["workloads"], *values["jobs"]]


def _containers(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for p in _pods(values) for c in [p, *p.get("initContainers", [])]]


def _by_name(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {w["name"]: w for w in values["workloads"]}


@pytest.fixture(scope="module", params=["development", "production"])
def values(request: pytest.FixtureRequest) -> dict[str, Any]:
    return _values(_config(request.param))


# ---- what is rendered -------------------------------------------------------------------------


def test_the_render_is_values_a_lock_the_image_plan_and_the_namespace_s_terraform() -> None:
    names = set(_artefacts(_config()))
    assert {"values.yaml", "versions.lock", "images.yaml"} <= names
    assert {f"terraform/{f}.tf" for f in ("main", "variables", "rds", "elasticache", "s3", "ecr",
                                         "irsa", "secrets")} <= names  # fmt: skip


def test_none_of_the_stores_the_platform_manages_and_no_caddy_or_local_model(
    values: dict[str, Any],
) -> None:
    names = {p["name"] for p in _pods(values)}
    assert not names & {"postgres", "valkey", "objectstore", "opensearch", "proxy", "ollama",
                        "ollama-models", "whisper", "whisper-models"}  # fmt: skip
    assert "Caddyfile" not in values["files"]


def test_the_gateway_only_with_an_engine_enabled() -> None:
    assert "litellm" not in _by_name(_values(_config("development")))
    assert "litellm" in _by_name(_values(_config("production")))


def test_development_runs_one_of_each_and_production_the_cluster_s_copies() -> None:
    dev, prod = _by_name(_values(_config("development"))), _by_name(_values(_config("production")))
    stores = ("arcadedb", "clickhouse", "clickhouse-keeper")
    assert [dev[s]["replicas"] for s in stores] == [1, 1, 1]
    assert [prod[s]["replicas"] for s in stores] == [3, 2, 3]
    # The stores' own clustering follows the count: ArcadeDB's server list, ClickHouse's Keepers.
    java = next(e["value"] for e in dev["arcadedb"]["env"] if e["name"] == "JAVA_OPTS")
    assert "arcadedb-0.arcadedb-headless" in java and "arcadedb-1." not in java
    assert _values(_config("development"))["files"]["keeper.xml"].count("<server>") == 1


def test_every_store_is_a_statefulset_on_the_platform_s_class_with_a_budget(
    values: dict[str, Any],
) -> None:
    workloads = _by_name(values)
    for store in ("arcadedb", "clickhouse", "clickhouse-keeper"):
        assert workloads[store]["kind"] == "StatefulSet" and workloads[store]["claims"]
        assert workloads[store]["disruptionBudget"] == {"maxUnavailable": 1}
    assert values["storage"]["className"] == load_platform("client").storage.class_name
    assert workloads["arcadedb"]["terminationGracePeriodSeconds"] >= 60


def test_every_pod_runs_as_10001_and_none_keeps_a_user_of_its_own(values: dict[str, Any]) -> None:
    assert values["podSecurity"] == {"user": 10001, "group": 10001}
    assert not [p["name"] for p in _pods(values) if "runAs" in p]


def test_keycloak_alone_takes_its_image_s_group_as_a_supplementary_one(
    values: dict[str, Any],
) -> None:
    """Keycloak's image is built for any user in group 0 (`/opt/keycloak` is `1000:0`,
    group-writable) and writes its own build there at start; as 10001:10001 alone it cannot
    (measured on the kind cluster, 10 November 2026). Its pod alone adds group 0 as a
    supplementary group: the user stays 10001 and non-root. Entra ID replaces it in P10 (ADR-148
    decision 9)."""
    groups = {p["name"]: p.get("supplementalGroups") for p in _pods(values)}
    assert groups.pop("keycloak") == [0]
    assert set(groups.values()) == {None}


def test_the_shared_folders_are_one_read_write_once_claim_its_mounters_on_one_node(
    values: dict[str, Any],
) -> None:
    assert values["storage"]["sharedAccessMode"] == "ReadWriteOnce"
    for pod in _pods(values):
        mounts = pod.get("shared") or any(c.get("shared") for c in pod.get("initContainers", []))
        assert bool(pod.get("sharedAffinity")) == bool(mounts), pod["name"]


# ---- the managed stores' details --------------------------------------------------------------


def _secret_refs(values: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (e["secretKeyRef"]["name"], e["secretKeyRef"]["key"])
        for c in _containers(values)
        for e in c.get("env", [])
        if "secretKeyRef" in e
    }


def _terraform_secrets(artefacts: dict[str, str]) -> dict[str, set[str]]:
    """Each `kubernetes_secret`'s name and the keys of its data, from the rendered Terraform."""
    found: dict[str, set[str]] = {}
    for name, text in artefacts.items():
        if not name.startswith("terraform/"):
            continue
        for block in re.findall(r'resource "kubernetes_secret" "[^"]+" \{(.*?)\n\}', text, re.S):
            secret = re.search(r'name\s+= "([^"]+)"', block)
            data = re.search(r"data = \{(.*?)\n  \}", block, re.S)
            assert secret and data, block
            found[secret[1]] = set(re.findall(r"^\s+([A-Za-z0-9_]+)\s+=", data[1], re.M))
    return found


@pytest.mark.parametrize("fixture", ["development", "production"])
def test_every_secret_the_values_read_is_one_the_terraform_writes(fixture: str) -> None:
    artefacts = _artefacts(_config(fixture))
    values = yaml.safe_load(artefacts["values.yaml"])
    written = _terraform_secrets(artefacts)
    for secret, key in _secret_refs(values):
        assert key in written.get(secret, set()), (secret, key)
    # And our own Secret holds every key a workload names in it.
    assert set(values["secrets"]["keys"]) <= written[values["secrets"]["name"]]


def test_every_key_a_pod_names_in_our_secret_is_in_it(values: dict[str, Any]) -> None:
    """A pod naming a key our Secret lacks never starts (`CreateContainerConfigError`; found on the
    kind cluster, 10 November 2026: the Conduit's gateway key, dropped when no engine is
    enabled)."""
    named = {e["secret"] for c in _containers(values) for e in c.get("env", []) if "secret" in e}
    assert named <= set(values["secrets"]["keys"]), named - set(values["secrets"]["keys"])


def _what_a_cluster_s_install_writes(config: OspreyConfig) -> dict[str, str]:
    """Our Secret as `ospreyflow install` writes it for the same deployment on the cluster profile
    (`harness.cluster_install`): every key the Conduit and the workers read through `envFrom`. A
    key a person gives is given a value of its own here, as the installer's terminal would."""
    from harness import cluster_install
    from harness.cloud_platform import _as_cluster, _cp

    as_cluster = _as_cluster(config, load_platform(_cp(config).platform))
    given = {config.models.key_variable(p.name): f"given-{p.name}"
             for p in config.models.enabled_providers}  # fmt: skip
    given |= {"OSPREY_SMTP_PASSWORD": "given-smtp", "OSPREY_POSTGRES_PASSWORD": "managed"}
    return {
        **cluster_install._minted(as_cluster, given),
        **cluster_install._derived(as_cluster, given, {}),
    }


@pytest.mark.parametrize("fixture", ["development", "production"])
def test_every_key_a_cluster_s_install_writes_reaches_the_pods(fixture: str) -> None:
    """The cluster's install writes the Conduit's settings into our Secret (the OIDC addresses, the
    object store's, the database's TLS mode) and this profile has no install: each must arrive by
    the ConfigMap (a setting), our Secret's keys (a secret), or the platform's secret (a managed
    store's detail), or the Conduit exits at start (found on the kind cluster, 10 November 2026:
    no `OIDC_JWKS_URL`)."""
    config = _config(fixture)
    values = _values(config)
    written = _what_a_cluster_s_install_writes(config)
    managed = set(managed_variables(config))
    missing = sorted(
        k for k in written
        if k not in managed
        and k not in values["environment"]
        and k not in values["secrets"]["keys"]
    )  # fmt: skip
    assert missing == [], missing
    secret_looking = re.compile(r"(PASSWORD|SECRET|SECRET_KEY|ACCESS_KEY|TOKEN)$|_KEY_")
    in_the_configmap = [k for k in values["environment"] if secret_looking.search(k)]
    assert in_the_configmap == [], in_the_configmap
    assert values["environment"]["OIDC_JWKS_URL"].endswith("/protocol/openid-connect/certs")


@pytest.mark.parametrize("fixture", ["development", "production"])
def test_a_password_the_install_writes_under_two_names_is_one_password(fixture: str) -> None:
    """The install writes one password under two names where two readers name it differently (the
    Conduit's client secret and the token exchange's; ArcadeDB's and its root's; ClickHouse's): the
    namespace's Terraform must write both from one `random_password`, or the Conduit's token
    exchange and the store's own sign-in disagree."""
    config = _config(fixture)
    artefacts = _artefacts(config)
    values = yaml.safe_load(artefacts["values.yaml"])
    written = _what_a_cluster_s_install_writes(config)
    pairs = [
        (a, b) for a in written for b in written
        if a < b and written[a] == written[b] and a in values["secrets"]["keys"]
        and b in values["secrets"]["keys"]
    ]  # fmt: skip
    assert pairs, "the install writes no password twice; this test proves nothing"
    secrets_tf = artefacts["terraform/secrets.tf"]
    for a, b in pairs:
        source_a = re.search(rf"^\s+{a}\s+=\s+(\S+)$", secrets_tf, re.M)
        source_b = re.search(rf"^\s+{b}\s+=\s+(\S+)$", secrets_tf, re.M)
        assert source_a and source_b, (a, b)
        assert source_a[1] == source_b[1], (a, source_a[1], b, source_b[1])


def test_no_managed_detail_is_in_a_file_or_our_own_secret(values: dict[str, Any]) -> None:
    variables = managed_variables(_config())
    assert not set(values["environment"]) & set(variables)
    assert not set(values["secrets"]["keys"]) & set(variables)
    assert "$(POSTGRES_HOST)" not in yaml.safe_dump(values["environment"])


def _on_the_cluster(fixture: str) -> dict[tuple[str, str], dict[str, Any]]:
    """The same deployment's containers as the cluster profile renders them, by (pod, container)."""
    from harness.cloud_platform import _as_cluster, _cp

    config = _config(fixture)
    as_cluster = _as_cluster(config, load_platform(_cp(config).platform))
    cluster = yaml.safe_load(render(as_cluster, resolver=_resolver).artefacts["values.yaml"])
    return {
        (pod["name"], c["name"]): c for pod in _pods(cluster)
        for c in [pod, *pod.get("initContainers", [])]
    }  # fmt: skip


@pytest.mark.parametrize("fixture", ["development", "production"])
def test_only_the_readers_are_given_the_managed_stores_details(fixture: str) -> None:
    """Every container, init containers among them, is given a managed store's detail only if it
    read it on the cluster: a reader taking the whole env (the Conduit, the workers, the report
    sync, Superset) every one; any other only those its env names or its command refers to
    (Keycloak's and the gateway's database, their init containers' `psql`). So the workspace's
    nginx, which takes the whole env, never holds the database's password."""
    from harness.cloud_platform import READERS

    values = _values(_config(fixture))
    variables = set(managed_variables(_config(fixture)))
    cluster = _on_the_cluster(fixture)
    for pod in _pods(values):
        for container in [pod, *pod.get("initContainers", [])]:
            given = {e["name"] for e in container.get("env", []) if "secretKeyRef" in e}
            if pod["name"] in READERS and container.get("envFrom"):
                assert given == variables, (container["name"], variables - given)
                continue
            before = cluster[(pod["name"], container["name"])]
            text = yaml.safe_dump(before)
            read = {e["name"] for e in before.get("env", [])} | {
                v for v in variables if re.search(rf"\$(\({v}\)|\{{{v}\}}|{v}\b)", text)
            }  # fmt: skip
            assert given <= read, (pod["name"], container["name"], given - read)
    assert "ingest" not in READERS  # never rendered on this profile


def test_a_variable_a_command_names_is_defined_before_it(values: dict[str, Any]) -> None:
    for container in _containers(values):
        env = container.get("env", [])
        for index, entry in enumerate(env):
            for name in re.findall(r"\$\(([A-Z_][A-Z0-9_]*)\)", str(entry.get("value", ""))):
                earlier = {e["name"] for e in env[:index]}
                assert name in earlier, (container["name"], entry["name"], name)
        for part in [*container.get("command", []), *container.get("args", [])]:
            assert "$$(POSTGRES_HOST)" not in part, container["name"]
            for name in set(re.findall(r"(?<!\$)\$\(([A-Z_][A-Z0-9_]*)\)", part)):
                assert name in {e["name"] for e in env}, (container["name"], name)
    keycloak = _by_name(values)["keycloak"]
    database = next(c for c in keycloak["initContainers"] if c["name"] == "keycloak-db")
    assert "psql -h $(POSTGRES_HOST)" in database["args"][0]


def test_the_conduit_knows_its_profile(values: dict[str, Any]) -> None:
    assert values["environment"]["OSPREY_PROFILE"] == "cloud-platform"
    # And reads the deployment's own configuration, which validates as it was written.
    mounted = OspreyConfig.model_validate(yaml.safe_load(values["files"]["osprey.yaml"]))
    assert mounted.profile.value == "cloud-platform" and mounted.cloud_platform is not None


def test_the_conduit_ingest_and_workers_run_as_the_bucket_s_service_account(
    values: dict[str, Any],
) -> None:
    account = load_platform("client").secrets.irsa.service_account
    for pod in _pods(values):
        expected = account if pod["name"] in ("api", "worker", "report-sync") else None
        assert pod.get("serviceAccountName") == expected, pod["name"]


# ---- images ------------------------------------------------------------------------------------


def test_every_image_is_the_registry_s_copy_pinned_by_digest(values: dict[str, Any]) -> None:
    for container in _containers(values):
        assert container["image"].startswith(REGISTRY + "/"), container["name"]
        assert re.search(r"[^@]@sha256:[0-9a-f]{64}$", container["image"]), container["image"]


def test_ours_are_refused_until_the_registry_holds_their_copy() -> None:
    def registry_has_only_theirs(ref: str) -> str | None:
        return None if ref.startswith(f"{REGISTRY}/ospreyflow/") else _resolver(ref)

    with pytest.raises(UnpinnedImagesError) as refused:
        render(_config(), resolver=registry_has_only_theirs)
    assert refused.value.images
    assert all(ref.startswith(f"{REGISTRY}/ospreyflow/") for ref in refused.value.images)


def test_the_conduit_is_planned_without_java() -> None:
    plan = yaml.safe_load(_artefacts(_config())["images.yaml"])
    api = next(i for i in plan["images"] if "/ospreyflow/api:" in i["target"])
    assert api["build_args"] == {"CONDUIT_JAVA": "omitted"}


# ---- egress and the front door -----------------------------------------------------------------


#: The fixtures' networks for S3 and STS (synthetic; the platform's own are its settings file's
#: or the deployment's `egress_nets`).
AWS = {
    "s3.eu-west-2.amazonaws.com": ["198.18.0.0/24"],
    "sts.eu-west-2.amazonaws.com": ["198.18.1.0/24"],
}


def _hosts(values: dict[str, Any]) -> dict[str, list[str]]:
    return {h["host"]: h["nets"] for h in values["egress"]["hosts"]}


def test_egress_allows_the_managed_stores_and_each_enabled_host_by_its_networks() -> None:
    dev = _values(_config("development"))["egress"]
    assert dev["managedNets"] == load_platform("client").egress.managed_nets
    assert _hosts({"egress": dev}) == AWS
    prod = _hosts(_values(_config("production")))
    assert prod == {**AWS, "api.openai.com": ["203.0.113.0/24"]}


def test_s3_and_sts_are_reached_by_networks_named_never_by_the_vpc_s() -> None:
    """The bucket is reached at S3's addresses (a gateway endpoint routes them by a prefix list, not
    the VPC's network) and IRSA's role by STS: each is an egress host on every render, its networks
    the platform's settings file's (`egress.service_nets`) or the deployment's, or refused."""
    with pytest.raises(CloudPlatformNotRenderable, match="s3.eu-west-2.amazonaws.com"):
        _artefacts(_config("development", cloud_platform={"egress_nets": {}}))
    kind = load_platform("kind")
    assert set(kind.egress.service_nets) == set(AWS)
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["cloud_platform"] |= {"platform": "kind", "egress_nets": {}}
    assert _hosts(_values(OspreyConfig.model_validate(raw))) == {
        h: list(n) for h, n in kind.egress.service_nets.items()
    }


def test_an_enabled_host_without_networks_is_refused_in_words() -> None:
    config = _config("production", cloud_platform={"egress_nets": AWS})
    with pytest.raises(CloudPlatformNotRenderable, match="api.openai.com"):
        _artefacts(config)


def test_the_mail_server_is_an_egress_host() -> None:
    """Keycloak sends invitations through the mail server, from the namespace: its host is allowed
    by its networks or the render is refused. (The organisation's own sign-in is Small's alone,
    refused at this profile by the schema.)"""
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["mail"] = {"host": "smtp.example.org", "from_address": "ospreyflow@example.org"}
    with pytest.raises(CloudPlatformNotRenderable, match="smtp.example.org"):
        render(OspreyConfig.model_validate(raw), resolver=_resolver)
    raw["cloud_platform"]["egress_nets"] |= {"smtp.example.org": ["198.51.100.25/32"]}
    assert _hosts(_values(OspreyConfig.model_validate(raw)))["smtp.example.org"] == [
        "198.51.100.25/32"
    ]


def test_a_connector_host_is_allowed_by_the_network_and_by_the_conduit_alike() -> None:
    """A connection's host is reached only if both the namespace's egress and the Conduit's own
    allow-list (`OSPREY_CONNECTOR_EGRESS`) admit it: one list, `cloud_platform.connector_hosts`,
    renders both, so they never disagree."""
    config = _config("development", cloud_platform={"connector_hosts": ["api.example.org"]})
    with pytest.raises(CloudPlatformNotRenderable, match="api.example.org"):
        _artefacts(config)
    config = _config("development", cloud_platform={
        "connector_hosts": ["api.example.org", "db.example.org"],
        "egress_nets": {**AWS, "api.example.org": ["198.51.100.80/32"],
                        "db.example.org": ["198.51.100.81/32"]}})  # fmt: skip
    values = _values(config)
    assert values["environment"]["OSPREY_CONNECTOR_EGRESS"] == "api.example.org,db.example.org"
    assert "OSPREY_CONNECTOR_EGRESS" not in values["secrets"]["keys"]
    assert {"api.example.org", "db.example.org"} <= set(_hosts(values))
    assert "OSPREY_CONNECTOR_EGRESS" not in _values(_config("development"))["environment"]


def test_a_proxied_map_provider_s_host_is_an_egress_host() -> None:
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["map"] = {"default": "hosted", "providers": [{
        "id": "hosted", "label": "Hosted tiles", "kind": "raster",
        "source": "https://tiles.example.org/{z}/{x}/{y}.png", "proxy": "required",
        "attribution": "Example",
        "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
    }]}  # fmt: skip
    with pytest.raises(CloudPlatformNotRenderable, match="tiles.example.org"):
        render(OspreyConfig.model_validate(raw), resolver=_resolver)
    raw["cloud_platform"]["egress_nets"] |= {"tiles.example.org": ["198.51.100.0/24"]}
    hosts = _hosts(_values(OspreyConfig.model_validate(raw)))
    assert hosts["tiles.example.org"] == ["198.51.100.0/24"]


def test_the_front_door_is_the_platform_s_ingress() -> None:
    ingress = _values(_config("development"))["ingress"]
    platform = load_platform("client")
    assert ingress["className"] == platform.ingress.class_name
    assert ingress["annotations"][platform.ingress.allow_list_annotation] == "192.0.2.0/24"
    assert ingress["annotations"]["nginx.ingress.kubernetes.io/enable-modsecurity"] == "true"
    assert {(r["host"], r["service"]) for r in ingress["rules"]} == {
        ("ospreyflow-dev.apps.example.org", "workspace"),
        ("id.ospreyflow-dev.apps.example.org", "keycloak"),
    }
    prod = {r["service"] for r in _values(_config("production"))["ingress"]["rules"]}
    assert prod == {"workspace", "keycloak", "superset"}
    assert not [w for w in _values(_config()).get("workloads", []) if w.get("public")]


# ---- the configuration ---------------------------------------------------------------------------


def test_the_sign_in_page_s_govuk_assets_come_from_the_glass_on_its_own_host() -> None:
    """Caddy sends `id.<host>/assets/govuk/*` to the workspace when the brand is GOV.UK (ADR-132
    Amendment 2: same-origin on the sign-in page); the platform's ingress must route it too, or the
    sign-in page loses its stylesheet and fonts."""
    rules = {r["host"]: r for r in _values(_config("development"))["ingress"]["rules"]}
    assert rules["id.ospreyflow-dev.apps.example.org"]["paths"] == [
        {"path": "/", "service": "keycloak", "port": 8080}
    ]
    govuk = _config("development", appearance={"brand": "govuk"})
    rules = {r["host"]: r for r in _values(govuk)["ingress"]["rules"]}
    assert rules["id.ospreyflow-dev.apps.example.org"]["paths"] == [
        {"path": "/assets/govuk", "service": "workspace", "port": 8080},
        {"path": "/", "service": "keycloak", "port": 8080},
    ]
    assert rules["ospreyflow-dev.apps.example.org"]["paths"] == [
        {"path": "/", "service": "workspace", "port": 8080}
    ]


def test_a_certificate_secret_is_named_or_the_platform_s_is_used() -> None:
    assert "tlsSecret" not in _values(_config("development"))["ingress"]
    named = _config("development", cloud_platform={"tls_secret": "ospreyflow-tls"})
    assert _values(named)["ingress"]["tlsSecret"] == "ospreyflow-tls"


def test_a_host_the_platform_s_wildcard_does_not_cover_needs_a_certificate_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A platform's default certificate is a wildcard one label deep: `id.` and `bi.` below the
    deployment's own name are two, so the browser refuses them unless a certificate is named."""
    import harness.cloud_platform as cp

    platform = load_platform("client")
    covering = platform.model_copy(
        update={"ingress": platform.ingress.model_copy(update={"wildcard": "*.apps.example.org"})}
    )
    monkeypatch.setattr(cp, "load_platform", lambda _name: covering)
    with pytest.raises(CloudPlatformNotRenderable, match="id.ospreyflow-dev.apps.example.org"):
        _artefacts(_config("development"))
    named = _config("development", cloud_platform={"tls_secret": "ospreyflow-tls"})
    assert _values(named)["ingress"]["tlsSecret"] == "ospreyflow-tls"


def test_the_settings_belong_to_the_profile_alone() -> None:
    with pytest.raises(ValidationError, match="only meaningful at profile: cloud-platform"):
        OspreyConfig.model_validate({"cloud_platform": {"namespace": "x"}})


def test_a_namespace_and_a_registry_are_required() -> None:
    with pytest.raises(
        ValidationError, match="cloud_platform.namespace and cloud_platform.registry"
    ):
        OspreyConfig.model_validate(
            {"profile": "cloud-platform", "network": {"public_origin": "https://a.example.org"}}
        )


def test_external_services_are_refused_on_the_profile() -> None:
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["external"] = {"postgres": {"host": "db.example.org"}}
    with pytest.raises(ValidationError, match="external: names none"):
        OspreyConfig.model_validate(raw)


def test_a_network_that_is_not_one_is_refused() -> None:
    raw = copy.deepcopy(yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8")))
    raw["cloud_platform"]["allow_from"] = ["not-a-network"]
    with pytest.raises(ValidationError, match="is not a network"):
        OspreyConfig.model_validate(raw)


def test_duckdb_is_refused_in_words() -> None:
    with pytest.raises(CloudPlatformNotRenderable, match="clickhouse"):
        _artefacts(_config(components={"analytics_engine": "duckdb"}))


def test_the_fixture_loads_as_a_deployment_would() -> None:
    assert load_config(FIXTURES / "development.yaml").profile.value == "cloud-platform"


# ---- the renderer's edges (reviewer point 16) --------------------------------------------------


def test_bucket_names_are_unique_beyond_the_namespace_s_name() -> None:
    """S3's bucket names are global across every AWS account: `<namespace>-media` is taken by the
    first namespace of that name anywhere, so the Terraform adds a suffix of its own making, and the
    prefix the services read is the same one the buckets are made under."""
    s3 = _artefacts(_config())["terraform/s3.tf"]
    assert 'resource "random_id" "buckets"' in s3
    assert re.search(r'bucket\s*=\s*"\$\{local\.prefix\}\$\{each\.key\}"', s3), s3
    assert re.search(r'prefix\s*=\s*"\$\{var\.namespace\}-\$\{random_id\.buckets\.hex\}-"', s3), s3
    assert re.search(r"=\s*local\.prefix\b", s3), "the services' prefix is not the buckets' own"


def test_an_image_with_neither_a_tag_nor_a_digest_is_refused() -> None:
    from harness.cloud_platform import _Copies

    copies = _Copies("registry.example/ns", "ghcr.io/ospreyflow", lambda ref: None)
    with pytest.raises(CloudPlatformNotRenderable, match="neither a tag nor a digest"):
        copies("docker.io/library/busybox")


def test_two_sources_copied_to_one_target_are_refused() -> None:
    """A second source for a target the plan already holds would be dropped silently, and the
    values would pin a digest `images push` never copied."""
    from harness.cloud_platform import _Copies

    copies = _Copies("registry.example/ns", "ghcr.io/ospreyflow", lambda ref: None)
    copies("quay.io/team/tool:1.0@sha256:" + "a" * 64)
    with pytest.raises(CloudPlatformNotRenderable, match="two sources"):
        copies("docker.io/team/tool:1.0@sha256:" + "b" * 64)
