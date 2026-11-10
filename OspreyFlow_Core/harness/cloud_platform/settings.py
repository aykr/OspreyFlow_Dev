"""A shared platform's own settings (ADR-148 decision 1): what its rules and its modules fix for
every namespace on it, read from `platforms/<name>.yaml` beside this module. A deployment's own
choices are `osprey.yaml`'s `cloud_platform:`; another shared platform is another file here, not
another profile."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

PLATFORMS = Path(__file__).resolve().parent / "platforms"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngressSettings(_Strict):
    class_name: str = Field(alias="class", min_length=1)
    annotations: dict[str, str] = Field(default_factory=dict)
    #: The annotation the platform's controller reads a deployment's allowed networks from.
    allow_list_annotation: str = Field(min_length=1)
    #: Where the controller's pods run, which the namespace's ingress policy admits.
    controller_namespace: str = Field(min_length=1)


class StorageSettings(_Strict):
    #: The ReadWriteOnce class every claim uses; the platform has no ReadWriteMany one.
    class_name: str = Field(alias="class", min_length=1)


class EgressSettings(_Strict):
    kind: Literal["calico"]
    #: The networks the platform's managed stores answer in.
    managed_nets: list[str] = Field(min_length=1)
    dns_namespace: str = Field(min_length=1)
    #: An AWS service's host and the networks the platform reaches it at (its VPC endpoint, or a
    #: gateway endpoint's prefix list as networks), where the platform's guide names them; a host
    #: not here takes the deployment's `cloud_platform.egress_nets`.
    service_nets: dict[str, list[str]] = Field(default_factory=dict)


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


def load_platform(name: str, folder: Path = PLATFORMS) -> PlatformSettings:
    path = folder / f"{name}.yaml"
    if not path.is_file():
        known = sorted(p.stem for p in folder.glob("*.yaml"))
        raise UnknownPlatform(
            f"cloud_platform.platform is {name!r}, and there is no settings file for it; "
            f"the platforms known are {', '.join(known) or 'none'}"
        )
    return PlatformSettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
