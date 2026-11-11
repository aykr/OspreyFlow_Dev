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
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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


class IrsaSettings(_Strict):
    service_account: str = Field(min_length=1)


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


class EgressHosts(_Strict):
    always: list[str] = Field(default_factory=list)
    engine_hosts: dict[str, str] = Field(default_factory=dict)
    #: A model engine of a kind that names no address (ADR-135 Amendment 4: `bedrock`), by its
    #: kind, whatever its name, `{region}` the engine's own (P11).
    engine_kind_hosts: dict[str, str] = Field(default_factory=dict)


_QUANTITY = r"^[0-9]+(\.[0-9]+)?(m|Ki|Mi|Gi|Ti)?$"


class Resources(_Strict):
    cpu: str = Field(pattern=_QUANTITY)
    memory: str = Field(pattern=_QUANTITY)
    memory_limit: str = Field(pattern=_QUANTITY)


class ProfileSettings(_Strict):
    doors: list[Door]
    group_zero: list[str] = Field(default_factory=list)
    ours: dict[str, ImageOfOurs]
    egress: EgressHosts
    resources: dict[str, Resources]
    arcadedb_heap_fraction: float = Field(gt=0, lt=1)

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
