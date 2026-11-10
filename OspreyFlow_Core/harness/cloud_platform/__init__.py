"""`profile: cloud-platform` (`spec/06_DECISIONS.md` ADR-148): the chart's values for a namespace
on a shared Kubernetes platform someone else runs, and the Terraform for that namespace's AWS
resources, in the shape its environments repository takes, for a person to raise as a pull request.

**Translated from the cluster's values, not written again**, as the cluster's are from compose
(`harness/cluster.py`): every workload is the one a cluster runs, and this module changes only what
the platform changes (ADR-148's decisions):

- 1: no cluster and no VPC are made; the namespace exists. `deploy/generated/cloud-platform/` holds
  `values.yaml`, `versions.lock` and `terraform/`.
- 2: the platform's ingress is the front door; no Caddy, and no Service is a load balancer.
- 3: every pod runs as 10001:10001, non-root, no privilege escalation, every capability dropped.
- 4: RDS, ElastiCache, OpenSearch and S3 replace ours; each detail is read from the secret the
  namespace's Terraform writes (the platform settings name them), never rendered into a file.
- 5: ArcadeDB 3, ClickHouse 2, Keeper 3 in production, one of each in development, on the
  platform's ReadWriteOnce class, each with a disruption budget allowing one copy down.
- 7: the platform's Calico deny-egress policy, and an allow policy for the managed stores, the
  cluster's DNS and each host an enabled feature reaches (by its declared networks).
- 8: every image from the deployment's registry, by the digest it was copied with.
- 11 (as far as this step needs it): no local model and no Whisper; the gateway only when an engine
  is enabled.

**The shared folders until P8** (the orchestrator's acceptance, 10 November 2026; ADR-148 decision 6
and its open questions 1 and 2 move them to S3 and Postgres): one ReadWriteOnce claim holds them, and
every pod that mounts it is placed on the node that holds it (a required pod affinity), so two
Conduits still read one folder. It is not spread across nodes; P8 removes it (a CARRIES row).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import yaml

from harness.cloud_platform.settings import PlatformSettings, load_platform
from harness.images import DigestResolver, ServiceImage
from schemas.deployment import (
    AnalyticsEngine,
    CloudPlatformConfig,
    GraphStore,
    OspreyConfig,
    Profile,
    SearchBackend,
)

#: ADR-148 decision 3: the one numeric user every pod runs as.
UID = 10001

#: What a cluster runs that this profile does not: Caddy (decision 2), the local models (11).
NOT_RENDERED = frozenset({"proxy", "ollama", "ollama-models", "whisper", "whisper-models"})
#: The gateway and its database, rendered only when an engine is enabled (decision 11).
GATEWAY = frozenset({"litellm", "litellm-db"})

#: What reads the managed stores' details: only these are given them (a pod that reads the whole
#: env, as the workspace's nginx does, is not handed the database's password for that).
READERS = frozenset({"api", "worker", "report-sync", "superset", "ingest"})

#: Decision 5: one of each in development.
DEVELOPMENT_REPLICAS = {
    "workspace": 1, "api": 1, "report-sync": 1, "superset": 1, "worker": 1, "keycloak": 1,
    "arcadedb": 1, "clickhouse": 1, "clickhouse-keeper": 1,
}  # fmt: skip

#: The stores' writable folders that are not on a claim of their own: a folder of the pod's own
#: (measured on the test server, `process/lanes/platform/gates/p7_uid_proof.sh`: as 10001 each
#: image's own folder is not writable).
SCRATCH: dict[str, list[str]] = {
    "arcadedb": ["/home/arcadedb/log", "/home/arcadedb/backups", "/home/arcadedb/replication"],
    "clickhouse": ["/var/log/clickhouse-server"],
    # Keeper's start checks its data folder, its claim's parent, is its own (measured: refused).
    "clickhouse-keeper": ["/var/log/clickhouse-keeper", "/var/lib/clickhouse"],
}

#: Decision 5: long enough for ArcadeDB to close its databases.
GRACE_SECONDS = {"arcadedb": 120, "clickhouse": 60, "clickhouse-keeper": 30}

#: How each image of ours is built (ADR-148 decision 8): its Dockerfile, its context, its arguments.
#: The Conduit without Java on this profile (decision 12).
OURS: dict[str, tuple[str, str, dict[str, str]]] = {
    "workspace": ("apps/workspace/Dockerfile", ".", {}),
    "api": ("services/api/Dockerfile", ".", {"CONDUIT_JAVA": "omitted"}),
    "ingest": ("services/ingest/Dockerfile", ".", {}),
    "ner": ("services/ner/Dockerfile", ".", {}),
    "worker": ("services/worker/Dockerfile", ".", {}),
    "report-sync": ("services/report_sync/Dockerfile", ".", {}),
    "superset": ("deploy/superset/Dockerfile", "deploy/superset", {}),
}

#: The label every pod that mounts the shared folders carries, which their affinity follows.
SHARED_LABEL = "ospreyflow.io/shared"

#: What the Ingress serves, by `harness.site.sites`' names: (site attribute, workload, port).
DOORS = (("glass", "workspace", 8080), ("identity", "keycloak", 8080),
         ("dashboards", "superset", 8088))  # fmt: skip

_BANNER = (
    "# Generated by harness.render from osprey.yaml (profile: cloud-platform) — do not edit by\n"
    "# hand. helm install ospreyflow <chart> -n <namespace> -f values.yaml, into the namespace the\n"
    "# platform's team created (ADR-148). No secret is here: the managed stores' details are read\n"
    "# from the secrets the namespace's Terraform (terraform/) writes.\n"
)


class CloudPlatformNotRenderable(ValueError):
    """The configuration asks for something the platform cannot run; the message says what."""


def _cp(config: OspreyConfig) -> CloudPlatformConfig:
    assert config.cloud_platform is not None  # the profile's validator requires it
    return config.cloud_platform


def _refuse(config: OspreyConfig) -> None:
    if config.components.analytics_engine is not AnalyticsEngine.CLICKHOUSE:
        raise CloudPlatformNotRenderable(
            "a cloud platform's Conduits share ClickHouse (ADR-148 decision 5); set "
            "components.analytics_engine: clickhouse"
        )
    if config.components.graph_store is not GraphStore.ARCADEDB:
        raise CloudPlatformNotRenderable(
            "a cloud platform runs ArcadeDB (ADR-148 decision 5); components.graph_store is "
            f"{config.components.graph_store.value!r}"
        )
    if config.components.source_path is not None:
        raise CloudPlatformNotRenderable(
            "a cloud platform pulls its images from its registry; components.source_path asks "
            "to build them here"
        )
    if not config.network.public_origin.startswith("https://"):
        raise CloudPlatformNotRenderable("a cloud platform is reached over HTTPS")


#: Each variable a workload reads that a managed store's secret gives: (store, the secret's key).
def managed_variables(config: OspreyConfig) -> dict[str, tuple[str, str]]:
    variables = {
        "POSTGRES_HOST": ("postgres", "host"),
        "POSTGRES_PORT": ("postgres", "port"),
        "POSTGRES_USER": ("postgres", "user"),
        "OSPREY_POSTGRES_USER": ("postgres", "user"),
        "POSTGRES_PASSWORD": ("postgres", "password"),
        "OSPREY_POSTGRES_PASSWORD": ("postgres", "password"),
        "POSTGRES_DB": ("postgres", "database"),
        "OSPREY_POSTGRES_DB": ("postgres", "database"),
        "VALKEY_HOST": ("redis", "host"),
        "VALKEY_PORT": ("redis", "port"),
        "VALKEY_PASSWORD": ("redis", "password"),
        "MINIO_BUCKET_PREFIX": ("s3", "prefix"),
    }
    if config.components.search is SearchBackend.OPENSEARCH:
        variables["OPENSEARCH_URL"] = ("opensearch", "url")
    return variables


def _as_cluster(config: OspreyConfig, platform: PlatformSettings) -> OspreyConfig:
    """The same deployment as a cluster would be configured, its managed stores named by the
    variables their secrets give (`$(VAR)`, which Kubernetes expands in a container's env, command
    and arguments), so the cluster's translation runs unchanged."""
    raw = config.model_dump(mode="json", exclude_none=True)
    raw.pop("cloud_platform", None)
    raw["profile"] = Profile.CLUSTER.value
    namespace = _cp(config).namespace
    assert namespace is not None
    storage = raw.setdefault("components", {}).setdefault("storage", {})
    # On a cluster these are paths on the shared folders, never a product folder's.
    storage["ingest"], storage["tiles"] = "/var/lib/osprey/ingest", "/var/lib/osprey/tiles"
    raw["cluster"] = {
        "namespace": namespace,
        "storage_class": platform.storage.class_name,
        "shared_storage_class": platform.storage.class_name,
    }
    raw["external"] = {
        "postgres": {"host": "$(POSTGRES_HOST)", "sslmode": "require"},
        "valkey": {"host": "$(VALKEY_HOST)", "tls": True},
        "object_store": {
            "endpoint": f"s3.{platform.aws_region}.amazonaws.com",
            "region": platform.aws_region,
            "credentials": "instance",
            "bucket_prefix": f"{namespace}-",
        },
        **(
            {"search": {"url": "$(OPENSEARCH_URL)"}}
            if config.components.search is SearchBackend.OPENSEARCH
            else {}
        ),
    }
    return OspreyConfig.model_validate(raw)


def _in_registry(image: str, registry: str) -> str:
    """`image` (`[host/]path:tag@digest`) as the copy `ospreyflow images push` made of it."""
    first, _, rest = image.partition("/")
    path = rest if rest and ("." in first or ":" in first or first == "localhost") else image
    return f"{registry}/{path}"


class _Copies:
    """Each image as the registry holds its copy, and the plan `ospreyflow images push` follows to
    make the copies: ours built here and pushed, the third-party ones copied by their digest (so
    the digest the values pin is the source's). Ours are pinned by the digest the registry gives
    for its copy, once pushed; until then the render is unpinned, and refused unless asked."""

    def __init__(self, registry: str, ours_prefix: str, resolver: DigestResolver) -> None:
        self.registry, self.ours_prefix, self.resolver = registry, ours_prefix, resolver
        self.plan: dict[str, dict[str, Any]] = {}
        self.unresolved: list[str] = []

    def __call__(self, image: str) -> str:
        # A reference given by its digest is pinned again by the cluster's translation
        # (`harness.cluster._Pins` appends one; reported to the orchestrator, 10 November 2026):
        # its own digest, the first, is the image's.
        reference, *digests = image.split("@")
        digest = digests[0] if digests else ""
        source = f"{reference}@{digest}" if digest else reference
        target = _in_registry(reference, self.registry)
        if not reference.rsplit("/", 1)[-1].count(":"):
            target += ":sha256-" + digest.removeprefix("sha256:")[:12]  # a tag to push it under
        entry: dict[str, Any] = {"source": source, "target": target}
        if reference.startswith(self.ours_prefix + "/"):
            name = reference.removeprefix(self.ours_prefix + "/").split(":")[0]
            dockerfile, context, arguments = OURS[name]
            entry = {"target": target, "dockerfile": dockerfile, "context": context,
                     "build_args": dict(arguments)}  # fmt: skip
            digest = self.resolver(target) or ""
            if not digest:
                self.unresolved.append(target)
        self.plan.setdefault(target, entry)
        return f"{target.split(':sha256-')[0]}@{digest}" if digest else target


def _containers(workload: dict[str, Any]) -> list[dict[str, Any]]:
    return [workload, *workload.get("initContainers", [])]


def _secret_ref(platform: PlatformSettings, store: str, key: str) -> dict[str, str]:
    settings = getattr(platform.secrets, store)
    return {"name": settings.name, "key": settings.keys[key]}


def _read_from_the_platform(
    container: dict[str, Any],
    variables: dict[str, tuple[str, str]],
    platform: PlatformSettings,
    *,
    reader: bool,
) -> None:
    """Every managed variable the container reads comes from the platform's secret: an entry that
    named our Secret or the ConfigMap is pointed there, and a container that reads the whole env
    (`envFrom`) is given each one by name, first, so a later `$(VAR)` finds it."""
    env = list(container.get("env", []))
    named = {e["name"] for e in env}
    first: list[dict[str, Any]] = []
    for entry in env:
        source = entry.get("secret") or entry.get("config")
        if source in variables:
            entry.pop("secret", None)
            entry.pop("config", None)
            entry["secretKeyRef"] = _secret_ref(platform, *variables[source])
    text = yaml.safe_dump(container)
    for name, (store, key) in variables.items():
        if name in named:
            continue
        if (reader and container.get("envFrom")) or f"$({name})" in text or f"$$({name})" in text:
            first.append({"name": name, "secretKeyRef": _secret_ref(platform, store, key)})
    # Kubernetes expands `$(VAR)` only for a variable defined earlier in the list.
    defined = [e for e in env if "secretKeyRef" in e]
    rest = [e for e in env if "secretKeyRef" not in e]
    container["env"] = [*first, *defined, *rest]
    for field in ("command", "args"):
        if field in container:
            container[field] = [
                re.sub(r"\$\$\((%s)\)" % "|".join(variables), r"$(\1)", part)
                for part in container[field]
            ]


def _egress_hosts(config: OspreyConfig) -> list[str]:
    """Each host an enabled feature reaches (the settings ADR-135 Amendment 2 and ADR-147 gate):
    a model engine's address and a proxied map provider's source."""
    from urllib.parse import urlsplit

    defaults = {"openai": "api.openai.com", "anthropic": "api.anthropic.com",
                "gemini": "generativelanguage.googleapis.com"}  # fmt: skip
    hosts: list[str] = []
    for provider in config.models.enabled_providers:
        host = urlsplit(provider.api_base).hostname if provider.api_base else None
        host = host or defaults.get(provider.name)
        if host is None:
            raise CloudPlatformNotRenderable(
                f"the model engine {provider.name!r} names no api_base, so its traffic's host is "
                "not known and cannot be allowed"
            )
        hosts.append(host)
    for map_provider in config.map.providers if config.map is not None else []:
        if map_provider.proxy == "none":
            continue  # fetched by the browser, never from the namespace
        for address in (map_provider.source or "", map_provider.endpoint or ""):
            if address.startswith(("http://", "https://")):
                host = urlsplit(re.sub(r"\{[^}]*\}", "x", address)).hostname
                if host:
                    hosts.append(host)
    return sorted(set(hosts))


def egress_policy(config: OspreyConfig, platform: PlatformSettings) -> dict[str, Any]:
    """Decision 7's two policies' settings: the networks allowed out, each host's by name."""
    hosts = _egress_hosts(config)
    given = _cp(config).egress_nets
    missing = [host for host in hosts if not given.get(host)]
    if missing:
        raise CloudPlatformNotRenderable(
            "egress is denied by default on a cloud platform (ADR-148 decision 7); name the "
            "networks of " + ", ".join(missing) + " under cloud_platform.egress_nets, or switch "
            "the feature off"
        )
    return {
        "kind": platform.egress.kind,
        "dnsNamespace": platform.egress.dns_namespace,
        "managedNets": list(platform.egress.managed_nets),
        "hosts": [{"host": host, "nets": list(given[host])} for host in hosts],
    }


def _ingress(config: OspreyConfig, platform: PlatformSettings, names: set[str]) -> dict[str, Any]:
    from harness.site import sites

    where = sites(config)
    annotations = dict(platform.ingress.annotations)
    if _cp(config).allow_from:
        annotations[platform.ingress.allow_list_annotation] = ",".join(
            _cp(config).allow_from
        )
    rules = []
    for site, service, port in DOORS:
        if service in names:
            host = getattr(where, site).removeprefix("https://").split("/")[0].split(":")[0]
            rules.append({"host": host, "service": service, "port": port})
    return {
        "enabled": True,
        "className": platform.ingress.class_name,
        "annotations": annotations,
        "rules": rules,
        "controllerNamespace": platform.ingress.controller_namespace,
    }


def render_cloud_platform(
    config: OspreyConfig,
    images: Sequence[ServiceImage],  # noqa: ARG001 — the cluster configuration's are rendered
    *,
    resolver: DigestResolver,
    allow_unpinned: bool,
    resolved_source_label: str,
) -> dict[str, str]:
    """`values.yaml`, `versions.lock` and `terraform/*.tf`."""
    from harness.cloud_platform.terraform import render_terraform
    from harness.cluster import render_cluster
    from harness.render import service_images

    _refuse(config)
    platform = load_platform(_cp(config).platform)
    production = _cp(config).environment == "production"
    as_cluster = _as_cluster(config, platform)
    # The images the cluster's configuration runs: none of the stores the platform manages.
    images = [i for i in service_images(as_cluster) if i.service not in NOT_RENDERED]
    rendered = render_cluster(
        as_cluster,
        images,
        resolver=resolver,
        allow_unpinned=allow_unpinned,
        resolved_source_label=resolved_source_label,
        replicas=None if production else DEVELOPMENT_REPLICAS,
    )
    values = yaml.safe_load(rendered["values.yaml"].split("\n", 3)[-1])
    registry = _cp(config).registry
    assert registry is not None
    variables = managed_variables(config)
    engines = bool(config.models.enabled_providers)
    api_image = next(i.image for i in images if i.service == "api")
    copies = _Copies(registry, api_image.rsplit("/", 1)[0], resolver)

    workloads = [
        w for w in values["workloads"]
        if w["name"] not in NOT_RENDERED and (engines or w["name"] not in GATEWAY)
    ]  # fmt: skip
    jobs = [j for j in values["jobs"] if j["name"] not in NOT_RENDERED]
    for pod in [*workloads, *jobs]:
        pod.pop("runAs", None)  # decision 3: every pod is 10001's (the chart's podSecurity)
        pod["initContainers"] = [
            c for c in pod.get("initContainers", []) if engines or c["name"] not in GATEWAY
        ]
        if not pod["initContainers"]:
            pod.pop("initContainers")
        for container in _containers(pod):
            container["image"] = copies(container["image"])
            _read_from_the_platform(
                container, variables, platform, reader=pod["name"] in READERS
            )
        if pod["name"] in SCRATCH:
            pod["scratch"] = [
                *pod.get("scratch", []), *({"mountPath": p} for p in SCRATCH[pod["name"]])
            ]  # fmt: skip
        if pod["name"] in GRACE_SECONDS:
            pod["terminationGracePeriodSeconds"] = GRACE_SECONDS[pod["name"]]
        if pod.get("shared") or any(c.get("shared") for c in pod.get("initContainers", [])):
            pod["sharedAffinity"] = True
        if pod["name"] in ("api", "worker", "report-sync"):
            pod["serviceAccountName"] = platform.secrets.irsa.service_account
        if pod.get("kind") == "StatefulSet":
            pod["disruptionBudget"] = {"maxUnavailable": 1}
    names = {w["name"] for w in workloads}
    if copies.unresolved and not allow_unpinned:
        from harness.render import UnpinnedImagesError

        raise UnpinnedImagesError(copies.unresolved)

    environment = {k: v for k, v in values["environment"].items() if k not in variables}
    # Decision 12: no Java in this profile's Conduit; Admin › Maps' Build reads the profile and
    # says where the basemap is built instead.
    environment["OSPREY_PROFILE"] = Profile.CLOUD_PLATFORM.value
    secrets = values["secrets"]
    secrets["keys"] = [k for k in secrets["keys"] if k not in variables]
    secrets["defaults"] = {k: v for k, v in secrets["defaults"].items() if k not in variables}
    if not engines:
        from harness.render import GATEWAY_DB_PASSWORD, GATEWAY_MASTER, GATEWAY_SALT

        gateway = {GATEWAY_DB_PASSWORD, GATEWAY_MASTER, GATEWAY_SALT}
        secrets["keys"] = [k for k in secrets["keys"] if k not in gateway]

    out = {
        "secrets": secrets,
        "storage": {
            "className": platform.storage.class_name,
            "sharedClassName": platform.storage.class_name,
            "sharedAccessMode": "ReadWriteOnce",
            "sharedSize": values["storage"]["sharedSize"],
        },
        "imagePullSecrets": [],
        "podSecurity": {"user": UID, "group": UID},
        "networkPolicy": {"openEgress": False},
        "egress": egress_policy(config, platform),
        "ingress": _ingress(config, platform, names),
        "environment": environment,
        "files": {
            **{k: v for k, v in values["files"].items() if k != "Caddyfile"},
            # The deployment's own configuration, as it was written, not the cluster's shape.
            "osprey.yaml": yaml.safe_dump(
                config.model_dump(mode="json", exclude_none=True), sort_keys=False
            ),
        },
        "workloads": workloads,
        "jobs": jobs,
    }
    artefacts = {
        "values.yaml": _BANNER
        + yaml.safe_dump(out, sort_keys=False, default_flow_style=False, width=4096),
        "versions.lock": rendered["versions.lock"],
        "images.yaml": "# What `ospreyflow images push --registry` copies (ADR-148 decision 8).\n"
        + yaml.safe_dump(
            {"registry": registry, "images": [copies.plan[k] for k in sorted(copies.plan)]},
            sort_keys=False,
        ),
    }
    artefacts.update(
        {
            f"terraform/{name}": text
            for name, text in render_terraform(config, platform, out).items()
        }
    )
    return artefacts
