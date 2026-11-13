"""Each workload's own egress, ingress and secrets on the `cloud-platform` profile (ADR-148
Amendment 5 points 21-23, the orchestrator's rulings from case-b's P12 review): the render's rows,
from `profile.yaml`'s `egress` and `secrets`. Helm's own policies, evaluated in Calico's order, are
`tests/cp_policy_check/test_cp_egress_order.py`'s.

What a mistake would do, and the case that catches it (rule 12):
- every pod given every host or the managed stores (the one `all()` Allow this replaces) —
  `test_a_workload_reaches_only_what_its_rows_give_it`;
- a caller left off a path, its calls refused once deployed —
  `test_every_service_a_workload_s_own_environment_names_is_on_its_path`;
- a pod admitting every pod of ours — `test_ingress_is_the_paths_turned_round`;
- the Glass or the recogniser holding the stores' passwords —
  `test_the_glass_and_the_recogniser_hold_no_secret_and_superset_its_own_alone`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from harness.cloud_platform.settings import load_profile
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig


def _values(name: str) -> dict[str, Any]:
    raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
    rendered = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts
    return yaml.safe_load(rendered["values.yaml"])


@pytest.fixture(scope="module", params=["development", "production", "poc"])
def values(request: pytest.FixtureRequest) -> dict[str, Any]:
    return _values(request.param)


def _rows(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in values["egress"]["workloads"]}


def test_every_rendered_workload_has_its_row(values: dict[str, Any]) -> None:
    others = set(load_profile().egress.others)
    assert others == {"backup", "backup-claims", "restore", "restore-claims"}
    assert set(_rows(values)) == {w["name"] for w in values["workloads"]} | others


def test_a_workload_reaches_only_what_its_rows_give_it(values: dict[str, Any]) -> None:
    rows, egress = _rows(values), load_profile().egress
    hosts = {h["host"] for h in values["egress"]["hosts"]}
    s3 = {h for h in hosts if h.startswith("s3.")}
    sts = {h for h in hosts if h.startswith("sts.")}
    for name, row in rows.items():
        assert row.get("managed", False) == (name in egress.managed), name
        given = set(row.get("hosts", []))
        if name in egress.reach["always"]:
            assert s3 | sts <= given, name
        else:
            # The buckets to the bucket role's pods alone; STS alone to a workload signing in by
            # a role of its own (the gateway, for Bedrock).
            assert not given & s3, name
            assert bool(given & sts) == (name in egress.reach.get("identity", [])), name
        for target in row.get("toPods", []):
            assert target["name"] in egress.paths.get(name, []), (name, target)
    # The Glass and the recogniser reach no store, no host and nothing outside: DNS and the
    # Conduit (the Glass) alone.
    assert rows["ner"].keys() <= {"name", "ports", "fromPods"}
    assert rows["workspace"].get("toPods") == [{"name": "api", "ports": [8000]}]
    assert not rows["workspace"].get("hosts") and not rows["workspace"].get("managed")


def test_a_model_engine_s_host_is_the_gateway_s_alone() -> None:
    rows = _rows(_values("production"))
    assert "api.openai.com" in rows["litellm"]["hosts"]
    assert not [h for h in rows["litellm"]["hosts"] if h.startswith("s3.")]
    assert [n for n, r in rows.items() if "api.openai.com" in r.get("hosts", [])] == ["litellm"]


def test_an_engine_s_host_is_open_while_declared_and_closed_by_a_render_without_it() -> None:
    """ADR-135 Amendment 10 point 2, correcting Amendment 8 decision 3: the render reads the engines
    `osprey.yaml` declares and nothing *Admin › Models* holds, so an engine disabled there keeps its
    host open at every render while `osprey.yaml` still declares it; it is taking the engine out of
    `osprey.yaml` and rendering again that closes it."""
    raw = yaml.safe_load((FIXTURES / "production.yaml").read_text(encoding="utf-8"))

    def hosts(declared: dict[str, Any]) -> dict[str, list[str]]:
        rendered = render(OspreyConfig.model_validate(declared), resolver=_resolver).artefacts
        return {
            n: r.get("hosts", []) for n, r in _rows(yaml.safe_load(rendered["values.yaml"])).items()
        }

    # Declared: open, and again at the next render of the same file (nothing else is read).
    for _ in range(2):
        assert "api.openai.com" in hosts(raw)["litellm"]

    without = {**raw, "models": {k: v for k, v in raw["models"].items() if k != "provider"}}
    assert not [n for n, h in hosts(without).items() if "api.openai.com" in h]


def test_ingress_is_the_paths_turned_round(values: dict[str, Any]) -> None:
    """A workload admits, in the namespace, exactly the rendered workloads whose paths name it."""
    rows, paths = _rows(values), load_profile().egress.paths
    for name, row in rows.items():
        callers = sorted(n for n in rows if name in paths.get(n, []))
        assert row.get("fromPods", []) == callers, name
    assert rows["worker"].get("fromPods") is None  # nothing calls the workers: they admit none
    assert rows["ner"]["fromPods"] == ["api", "worker"]


def test_every_service_a_workload_s_own_environment_names_is_on_its_path(
    values: dict[str, Any],
) -> None:
    """A workload's own environment (not the shared ConfigMap) names the services it calls; each is
    on its path, so no call it makes is refused once deployed."""
    rows, paths = _rows(values), load_profile().egress.paths
    names = set(rows)
    for workload in values["workloads"]:
        for container in [workload, *workload.get("initContainers", [])]:
            for variable in container.get("env", []):
                value = str(variable.get("value", ""))
                for target in names - {workload["name"]}:
                    if re.search(rf"(^|//|@){re.escape(target)}([:./]|$)", value):
                        assert target in paths.get(workload["name"], []), (workload["name"], value)


def test_the_glass_and_the_recogniser_hold_no_secret_and_superset_its_own_alone(
    values: dict[str, Any],
) -> None:
    workloads = {w["name"]: w for w in values["workloads"]}
    secrets = load_profile().secrets
    for name, workload in workloads.items():
        if not workload.get("envFrom"):
            continue
        named = {e["secret"] for e in workload.get("env", []) if "secret" in e}
        if name in secrets.whole:
            assert not workload.get("noSecret"), name
        else:
            assert workload.get("noSecret"), name
            assert named <= set(secrets.named.get(name, [])), (name, named)
    for name in ("workspace", "ner"):
        assert not [e for e in workloads[name].get("env", []) if "secret" in e], name


# ---- P9's pods, rendered beside the workloads (the orchestrator's rulings from P9 round 2) ----


def test_p9_s_pods_have_rows_by_their_own_names_and_a_restore_reaches_the_api(
    values: dict[str, Any],
) -> None:
    """P9's backup and restore pods render beside the workloads (`values.backups`), so the render
    gives `egress_policy` their names (`egress.others`): each has its row and admits nothing. The
    backup reaches ArcadeDB and ClickHouse, the restore ClickHouse alone (ArcadeDB's restore calls
    nothing), each admitted; the two restores alone the cluster's API (`kube-api`, the writers
    check); the claims' runs none of ours (a claim is a mount). All four reach S3 and STS, and
    nothing reaches KMS: S3 calls it on their behalf (SSE-KMS)."""
    rows = _rows(values)
    hosts = {h["host"] for h in values["egress"]["hosts"]}
    assert not [h for h in hosts if h.startswith("kms.")]
    s3_sts = {h for h in hosts if h.startswith(("s3.", "sts."))}
    stores = {"backup": {"arcadedb", "clickhouse"}, "restore": {"clickhouse"},
              "backup-claims": set(), "restore-claims": set()}  # fmt: skip
    for name, reached in stores.items():
        assert set(rows[name]["hosts"]) == s3_sts, name
        assert {t["name"] for t in rows[name].get("toPods", [])} == reached, name
        assert "fromPods" not in rows[name] and "ports" not in rows[name], name
        assert not rows[name].get("managed"), name
        assert rows[name].get("toKubeApi", False) == name.startswith("restore"), name
    for store, callers in {"arcadedb": {"backup"}, "clickhouse": {"backup", "restore"}}.items():
        assert set(rows[store]["fromPods"]) & set(stores) == callers, store
    assert sorted(n for n, r in rows.items() if r.get("toKubeApi")) == ["restore", "restore-claims"]


# ---- the service account's token (Amendment 5 point 24, case-b's P12 part 2) --------------------


@pytest.mark.parametrize("name", ["development", "production", "poc", "production-bedrock"])
def test_only_a_pod_with_an_account_of_its_own_mounts_its_token(name: str) -> None:
    """Every pod and Job says whether its token is mounted (Kubernetes mounts it by default): only
    the IRSA pods and, with Bedrock, the gateway, each by an account of its own; none of the others,
    which call no Kubernetes API."""
    values = _values(name)
    pods = [*values["workloads"], *values["jobs"]]
    for pod in pods:
        if pod["name"] == "clickhouse":
            # Its backup role's account (ADR-148 Amendment 7), its web identity by the account
            # alone (IRSA's webhook); it calls no Kubernetes API, so no token (P9_render.diff).
            assert pod["serviceAccountName"] and pod["automountToken"] is False
            continue
        assert pod["automountToken"] is bool(pod.get("serviceAccountName")), pod["name"]
    mounted = {p["name"] for p in pods if p["automountToken"]}
    gateway = {"litellm"} if name == "production-bedrock" else set()
    irsa = {"api", "worker", "report-sync"} & {p["name"] for p in pods}  # the poc's has no sync
    assert {"api", "worker"} <= irsa and mounted == irsa | gateway


# ---- each host on its own ports (Amendment 5 point 21, the final review's item 5) ----------------


def _with(**cloud: Any) -> OspreyConfig:
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    nets = raw["cloud_platform"]["egress_nets"]
    for host, net in cloud.pop("nets", {}).items():
        nets[host] = [net]
    raw.update(cloud.pop("top", {}))
    raw["cloud_platform"].update(cloud)
    return OspreyConfig.model_validate(raw)


def _hosts(config: OspreyConfig) -> dict[str, list[int]]:
    values = yaml.safe_load(render(config, resolver=_resolver).artefacts["values.yaml"])
    return {h["host"]: h["ports"] for h in values["egress"]["hosts"]}


def test_each_host_is_reached_on_its_own_ports() -> None:
    """S3 and STS on 443; the mail server on `mail.port`; a connector host on its `host:port`, a
    bare one on 443, and one given twice with two ports on both. The Conduit's allow-list keeps
    the hosts alone."""
    mail = {"host": "smtp.example.org", "port": 2525, "from_address": "osprey@example.org"}
    config = _with(
        connector_hosts=["db.example.org:5432", "api.example.org", "db.example.org:1433"],
        nets={"smtp.example.org": "198.18.4.0/24", "db.example.org": "198.18.5.0/24",
              "api.example.org": "198.18.6.0/24"},
        top={"mail": mail},
    )  # fmt: skip
    hosts = _hosts(config)
    assert hosts["s3.eu-west-2.amazonaws.com"] == [443]
    assert hosts["sts.eu-west-2.amazonaws.com"] == [443]
    assert hosts["smtp.example.org"] == [2525]
    assert hosts["db.example.org"] == [1433, 5432]
    assert hosts["api.example.org"] == [443]
    values = yaml.safe_load(render(config, resolver=_resolver).artefacts["values.yaml"])
    assert values["environment"]["OSPREY_CONNECTOR_EGRESS"] == "api.example.org,db.example.org"


def test_the_managed_stores_are_reached_on_their_own_ports() -> None:
    """RDS's and ElastiCache's, and the OpenSearch domain's 443 where the Terraform makes one (not
    in the poc shape, which takes no OpenSearch)."""
    assert _values("development")["egress"]["managedPorts"] == [443, 5432, 6379]
    assert _values("poc")["egress"]["managedPorts"] == [5432, 6379]


@pytest.mark.parametrize(
    "entry", ["db.example.org:0", "db.example.org:65536", "db.example.org:54x2",
              "db.example.org:", ":5432", "db.example.org:+5432"],
)  # fmt: skip
def test_a_connector_host_s_port_that_is_not_a_port_is_refused(entry: str) -> None:
    with pytest.raises(ValueError, match="host:port with a port from 1 to 65535"):
        _with(connector_hosts=[entry], nets={"db.example.org": "198.18.5.0/24"})


def test_an_engine_s_own_port_and_a_map_source_s_scheme_are_their_hosts_ports() -> None:
    """The final review's second pass, item 3: an address's own port (an engine at
    `https://…:8443`), and its scheme's when it names none (a proxied `http://` map source, 80)."""
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["models"] = {"local_only": False, "providers": [
        {"name": "azure", "roles": {"extraction": "gpt-4o-mini"},
         "api_base": "https://llm.example.org:8443/openai"}]}  # fmt: skip
    tiles = {**raw["map"]["providers"][0], "id": "tiles-http", "kind": "raster",
             "source": "http://tiles.example.org/{z}/{x}/{y}.png", "proxy": "required",
             "style": None}  # fmt: skip
    raw["map"]["providers"].append({k: v for k, v in tiles.items() if v is not None})
    nets = raw["cloud_platform"]["egress_nets"]
    nets["llm.example.org"] = ["198.18.7.0/24"]
    nets["tiles.example.org"] = ["198.18.8.0/24"]
    hosts = _hosts(OspreyConfig.model_validate(raw))
    assert hosts["llm.example.org"] == [8443]
    assert hosts["tiles.example.org"] == [80]


@pytest.mark.parametrize("entry", ["[2001:db8::1]:5432", "2001:db8::1", "[2001:db8::1]"])
def test_a_connector_host_given_as_an_ipv6_literal_is_refused_in_its_own_words(entry: str) -> None:
    with pytest.raises(ValueError, match="an IPv6 address is not taken; name the host by its name"):
        _with(connector_hosts=[entry])


def test_install_md_warns_of_each_bare_connector_host() -> None:
    """A connector host named without a port is reached on 443 alone: the render says so, in
    words, for each, at the head of `values.yaml` (and in the poc shape's INSTALL.md); a host with
    its port is not named there."""
    config = _with(
        connector_hosts=["api.example.org", "db.example.org:5432"],
        nets={"api.example.org": "198.18.6.0/24", "db.example.org": "198.18.5.0/24"},
    )
    values = render(config, resolver=_resolver).artefacts["values.yaml"]
    head = values[: values.index("secrets:")]
    assert "# Connector hosts reached on 443 only: api.example.org, named in" in head
    assert "db.example.org" not in head
    assert (
        "Connector hosts reached on 443 only"
        not in render(_with(), resolver=_resolver).artefacts["values.yaml"]
    )
    # The poc shape's INSTALL.md says it too.
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    raw["cloud_platform"]["connector_hosts"] = ["api.example.org"]
    raw["cloud_platform"]["egress_nets"]["api.example.org"] = ["198.18.6.0/24"]
    install = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["INSTALL.md"]
    assert "**Connector hosts reached on 443 only.** `api.example.org` is named in" in install


@pytest.mark.parametrize("name", ["development", "production", "poc", "production-bedrock"])
def test_the_ceiling_is_in_no_key_of_our_secret(name: str) -> None:
    """The final review's second pass, item 7: OSPREY_HIGHEST_MARKING is the ConfigMap's alone,
    in no key of our Secret (its keys, its defaults or its copies), so the Secret, read whole by
    the Conduit and the workers, cannot say otherwise."""
    values = _values(name)
    assert values["environment"]["OSPREY_HIGHEST_MARKING"] == "OFFICIAL-SENSITIVE"
    secrets = values["secrets"]
    assert "OSPREY_HIGHEST_MARKING" not in secrets["keys"]
    assert "OSPREY_HIGHEST_MARKING" not in secrets.get("defaults", {})
    assert "OSPREY_HIGHEST_MARKING" not in secrets.get("copies", {})
