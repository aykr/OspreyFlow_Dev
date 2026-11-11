"""A shared platform's own settings (ADR-148 decision 1): what its rules and its modules fix for
every namespace on it, read from `platforms/<name>.yaml` beside this module (or from a folder named
in `OSPREY_PLATFORM_FOLDERS`, which a test's or a local proof's own platform file lives in). A
deployment's own choices are `osprey.yaml`'s `cloud_platform:`; another shared platform is another
file, not another profile.

**The profile's extension points** are data too (`profile.yaml`, ADR-148 Amendment 1 item 11):
the Ingress's doors, the images of ours and how each is built, the workloads given group 0, the
hosts every render reaches and each container's resources. A later step adds a row there."""

from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from schemas.deployment import too_wide_for_egress

HERE = Path(__file__).resolve().parent
PLATFORMS = HERE / "platforms"
PROFILE = HERE / "profile.yaml"
#: Further folders of platform settings files, separated as `PATH` is (a test's fixtures; P7a's
#: kind proof). Core's own folder is read first, so a name there is never shadowed.
FOLDERS_VARIABLE = "OSPREY_PLATFORM_FOLDERS"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _egress_networks(nets: list[str]) -> list[str]:
    for net in nets:
        try:
            ipaddress.ip_network(net)
        except ValueError:
            raise ValueError(f"{net!r} is not a network (for example 192.0.2.0/24)") from None
        if why := too_wide_for_egress(net):
            raise ValueError(why)
    return nets


class IngressSettings(_Strict):
    class_name: str = Field(alias="class", min_length=1)
    annotations: dict[str, str] = Field(default_factory=dict)
    #: The annotation the platform's controller reads a deployment's allowed networks from.
    allow_list_annotation: str = Field(min_length=1)
    #: Where the controller's pods run, which the namespace's ingress policy admits.
    controller_namespace: str = Field(min_length=1)
    #: The name the platform's own certificate covers (`*.apps.example.org`: one label deep), where
    #: its guide gives it; a host it does not cover then needs `cloud_platform.tls_secret`.
    wildcard: str | None = Field(default=None, pattern=r"^\*\.[a-z0-9.-]+$")


class StorageSettings(_Strict):
    #: The ReadWriteOnce class every claim uses; the platform has no ReadWriteMany one.
    class_name: str = Field(alias="class", min_length=1)


class EgressSettings(_Strict):
    kind: Literal["calico"]
    #: The networks the platform's managed stores answer in. Every pod may reach all of it, so it
    #: is held to the same width as a host's networks (`schemas.deployment.EGRESS_WIDEST_PREFIX`).
    managed_nets: list[str] = Field(min_length=1)
    dns_namespace: str = Field(min_length=1)
    #: An AWS service's host and the networks the platform reaches it at (its VPC endpoint, or a
    #: gateway endpoint's prefix list as networks), where the platform's guide names them; a host
    #: not here takes the deployment's `cloud_platform.egress_nets`.
    service_nets: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("managed_nets")
    @classmethod
    def _managed_nets_are_narrow(cls, nets: list[str]) -> list[str]:
        return _egress_networks(nets)

    @field_validator("service_nets")
    @classmethod
    def _service_nets_are_narrow(cls, nets: dict[str, list[str]]) -> dict[str, list[str]]:
        for host_nets in nets.values():
            _egress_networks(host_nets)
        return nets


class SecretSettings(_Strict):
    name: str = Field(min_length=1)
    keys: dict[str, str]


#: A Kubernetes object's name (RFC 1123 subdomain): lower case, digits, `-` and `.`, beginning and
#: ending with a letter or digit, at most 253.
_KUBERNETES_NAME = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")


class IrsaSettings(_Strict):
    service_account: str = Field(min_length=1)
    #: The model gateway's own account, its role Bedrock's invoke in London alone, made only while a
    #: Bedrock engine is enabled (P11 part 2; the orchestrator's ruling, option A).
    gateway_service_account: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _two_accounts_apart(self) -> IrsaSettings:
        """Each a Kubernetes name, and never one account for both: the gateway's role would trust
        the buckets' account, or two service accounts would share one name (the orchestrator's
        review of P11 part 2, round 1, item 5)."""
        for field, name in (("service_account", self.service_account),
                            ("gateway_service_account", self.gateway_service_account)):  # fmt: skip
            if name is not None and not _KUBERNETES_NAME.fullmatch(name):
                raise ValueError(
                    f"secrets.irsa.{field} must be a Kubernetes name (lower case, digits, - and .)"
                )
        if self.gateway_service_account == self.service_account:
            raise ValueError(
                "secrets.irsa.gateway_service_account must differ from service_account: the "
                "gateway's role grants Bedrock alone, the namespace's the buckets"
            )
        return self


class PlatformSecrets(_Strict):
    postgres: SecretSettings
    redis: SecretSettings
    opensearch: SecretSettings
    s3: SecretSettings
    irsa: IrsaSettings


class PlatformSettings(_Strict):
    name: str
    aws_region: str
    ingress: IngressSettings
    storage: StorageSettings
    egress: EgressSettings
    secrets: PlatformSecrets


class UnknownPlatform(ValueError):
    """`cloud_platform.platform` names no settings file; the message lists those there are."""


def platform_folders() -> list[Path]:
    extra = [Path(p) for p in os.environ.get(FOLDERS_VARIABLE, "").split(os.pathsep) if p]
    return [PLATFORMS, *extra]


def load_platform(name: str, folders: list[Path] | None = None) -> PlatformSettings:
    folders = platform_folders() if folders is None else folders
    for folder in folders:
        path = folder / f"{name}.yaml"
        if path.is_file():
            return PlatformSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    known = sorted({p.stem for folder in folders for p in folder.glob("*.yaml")})
    raise UnknownPlatform(
        f"cloud_platform.platform is {name!r}, and there is no settings file for it; "
        f"the platforms known are {', '.join(known) or 'none'}"
    )


# ---- the profile's extension points (`profile.yaml`) ---------------------------------------------


class Door(_Strict):
    site: Literal["glass", "identity", "dashboards"]
    workload: str = Field(min_length=1)
    port: int = Field(ge=1024, le=65535)


class ImageOfOurs(_Strict):
    dockerfile: str = Field(min_length=1)
    context: str = Field(min_length=1)
    build_args: dict[str, str] = Field(default_factory=dict)


#: The kinds of host the namespace reaches (`harness.cloud_platform._egress_hosts_by_kind`), each
#: reached only by the workloads `egress.reach` names for it.
HOST_KINDS = ("always", "identity", "keys", "engines", "maps", "mail", "connectors")
#: A path's target that is not a workload: the cluster's API server, by the `kubernetes` Service.
KUBE_API = "kube-api"


class EgressHosts(_Strict):
    always: list[str] = Field(default_factory=list)
    engine_hosts: dict[str, str] = Field(default_factory=dict)
    #: A model engine of a kind that names no address (ADR-135 Amendment 4: `bedrock`), by its
    #: kind, whatever its name, `{region}` the engine's own (P11).
    engine_kind_hosts: dict[str, str] = Field(default_factory=dict)
    #: ADR-148 Amendment 5 point 21: egress is each workload's own. Who reaches each kind of host,
    #: who reaches the managed stores' networks, and which of the namespace's own workloads each
    #: one calls; anything not named here is denied.
    reach: dict[str, list[str]] = Field(default_factory=dict)
    #: STS alone (a subset of `always`), for a workload that signs in by a role of its own and
    #: never reaches the buckets: the gateway's, for Bedrock (P11 part 2).
    identity: list[str] = Field(default_factory=list)
    #: KMS, for the backups' own key (P9, ADR-148 Amendment 7).
    keys: list[str] = Field(default_factory=list)
    managed: list[str] = Field(default_factory=list)
    paths: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("reach")
    @classmethod
    def _known_kinds(cls, reach: dict[str, list[str]]) -> dict[str, list[str]]:
        unknown = sorted(set(reach) - set(HOST_KINDS))
        if unknown:
            raise ValueError(
                f"egress.reach names {', '.join(unknown)}, not a kind of host this profile "
                f"reaches ({', '.join(HOST_KINDS)})"
            )
        return reach


_QUANTITY = r"^[0-9]+(\.[0-9]+)?(m|Ki|Mi|Gi|Ti)?$"


class Resources(_Strict):
    cpu: str = Field(pattern=_QUANTITY)
    memory: str = Field(pattern=_QUANTITY)
    memory_limit: str = Field(pattern=_QUANTITY)


class OwnClaim(_Strict):
    """A shared folder given a claim of its own (ADR-148 Amendment 5): its name (the claim is
    `ospreyflow-<name>`), the folder it takes from the shared claim, and its size."""

    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    folder: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    size: str = Field(pattern=r"^[0-9]+(Mi|Gi|Ti)$")


class PocShape(_Strict):
    """`cloud_platform.shape: poc` (ADR-148 Amendment 5): the folders that leave the shared claim
    for claims of their own."""

    claims: list[OwnClaim]
    #: Each container's CPU limit, by the name `resources` uses, `default` for any not named.
    cpu_limits: dict[str, str]

    @field_validator("cpu_limits")
    @classmethod
    def _a_default_limit(cls, limits: dict[str, str]) -> dict[str, str]:
        if "default" not in limits:
            raise ValueError("poc.cpu_limits names no `default`, which a container not named takes")
        for quantity in limits.values():
            if not re.fullmatch(_QUANTITY, quantity):
                raise ValueError(f"poc.cpu_limits: {quantity!r} is not a quantity")
        return limits


class SecretReaders(_Strict):
    """ADR-148 Amendment 5 point 22: which workloads read our Secret whole (`envFrom`), and the keys
    each other workload that reads the deployment's settings is given by name. A workload named in
    neither gets the ConfigMap alone, never the stores' passwords or the gateway's master key."""

    whole: list[str]
    named: dict[str, list[str]] = Field(default_factory=dict)


class ProfileSettings(_Strict):
    doors: list[Door]
    group_zero: list[str] = Field(default_factory=list)
    ours: dict[str, ImageOfOurs]
    egress: EgressHosts
    resources: dict[str, Resources]
    arcadedb_heap_fraction: float = Field(gt=0, lt=1)
    poc: PocShape
    secrets: SecretReaders

    @field_validator("resources")
    @classmethod
    def _a_default(cls, resources: dict[str, Resources]) -> dict[str, Resources]:
        if "default" not in resources:
            raise ValueError("resources names no `default`, which a container not named takes")
        return resources


class ProfileUnreadable(ValueError):
    """`profile.yaml` cannot be read as the profile's settings; the message says where."""


def load_profile(path: Path = PROFILE) -> ProfileSettings:
    try:
        return ProfileSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ProfileUnreadable(
            f"the cloud-platform profile's settings ({path.name}) cannot be read: {error}"
        ) from None
