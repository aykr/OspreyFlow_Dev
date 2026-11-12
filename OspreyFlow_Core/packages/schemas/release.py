"""A dataset's release between environments, as YAML (`06_DECISIONS.md` ADR-140 Amendment 9
decision 4; the owner's ruling D4 of 7 November 2026).

*Export* in Studio › Releases writes one bundle: a manifest (`DatasetRelease`), following
Kubernetes' conventions (`apiVersion`, `kind`, `metadata`, `spec`) so it can sit in a ConfigMap or
be applied by a GitOps tool; one YAML file each for the domain model, each pipeline and each
reference list's definition; and a small list's rows as a CSV named by its checksum. The manifest
names every file with its SHA-256, so a script or CI can check a bundle against
`release.schema.json`, which is generated from `DatasetRelease` and published beside this module.

**Never in a bundle:** credentials, loaded data, case membership, owners, or the rows of a licensed
screening list. The file models below have no field that could hold one: a connection appears by
name only, a pipeline carries no owner, schedule owner, case or publisher, and a list's rows are
named only when the list is a dataset's own `reference` list (`services/ingest/release.py` writes
them; a `screening` list's rows never leave). **Importing lands everything as a draft**: *Make live*
stays a person's audited step.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .dataset_model import ModelExtension, ReferenceListKind
from .monitoring import ListSchedule

RELEASE_API_VERSION = "ospreyflow.io/v1"
RELEASE_KIND = "DatasetRelease"

#: A Kubernetes object name (RFC 1123 subdomain, lower case), so the manifest can be a ConfigMap's.
_K8S_NAME = r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$"
_SHA256 = r"^[0-9a-f]{64}$"
#: A bundle's file path: relative, forward slashes, at most four parts, none starting with a dot (so
#: never `..`), no leading slash.
_SEGMENT = r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,99}"
_BUNDLE_PATH = rf"^{_SEGMENT}(/{_SEGMENT}){{0,3}}$"

ReleaseFileRole = Literal["domain_model", "pipeline", "reference_list", "list_rows"]


class ReleaseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_K8S_NAME)
    #: The release's own version, as the person exporting names it (`1`, `2026.11.10`).
    version: str = Field(min_length=1, max_length=64)


class ReleaseFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(pattern=_BUNDLE_PATH)
    role: ReleaseFileRole
    sha256: str = Field(pattern=_SHA256)


class ReleaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The domain model's file.
    domain_model: str = Field(pattern=_BUNDLE_PATH)
    #: The starter packs the model pins, each at its version.
    packs: dict[str, int] = Field(default_factory=dict)
    pipelines: list[str] = Field(default_factory=list)
    reference_lists: list[str] = Field(default_factory=list)
    #: The connections the pipelines' sources read through, **by name only**: the receiving
    #: environment has its own of that name, with its own secret.
    connections: list[str] = Field(default_factory=list)
    #: Every file of the bundle but the manifest, with its SHA-256.
    files: list[ReleaseFile] = Field(default_factory=list)


class DatasetRelease(BaseModel):
    """The manifest (`release.yaml`). Its JSON schema is `packages/schemas/release.schema.json`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: Literal["ospreyflow.io/v1"] = Field(alias="apiVersion")
    kind: Literal["DatasetRelease"]
    metadata: ReleaseMetadata
    spec: ReleaseSpec


class ReleasedDomainModel(BaseModel):
    """The domain model's file: what a draft is made of, never who made it or when it went live."""

    model_config = ConfigDict(extra="forbid")

    #: The version it was exported from, for the record; an import makes a draft of its own number.
    exported_version: int = Field(ge=1)
    packs: dict[str, int] = Field(default_factory=dict)
    extensions: list[ModelExtension] = Field(default_factory=list)
    reference_lists: list[str] = Field(default_factory=list)


class ReleasedPipeline(BaseModel):
    """One pipeline's file: its definition as it was published. No owner, publisher, schedule
    owner, case, dataset id or run is in it; the load node's dataset is the receiving one."""

    model_config = ConfigDict(extra="forbid")

    pipeline_id: str = Field(min_length=1)
    exported_version: int = Field(ge=1)
    label: str
    connector_profile: str | None = None
    source_location: str | None = None
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None
    row_template: dict[str, Any] | None = None
    deduplicate: dict[str, Any] | None = None
    pack_versions: dict[str, int] | None = None
    #: `schemas.ingest.PipelineGraph`, as `services.api.studio_staging.pipeline_yaml` writes it.
    pipeline: dict[str, Any] | None = None


class ReleasedReferenceList(BaseModel):
    """One reference list's definition, and its rows' file when they travel."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1)
    kind: ReferenceListKind
    key_column: str = Field(min_length=1)
    version: int = Field(ge=1)
    schedule: ListSchedule | None = None
    #: The CSV of its rows, named by its SHA-256; `None` for a screening list (licensed rows never
    #: travel) or one too large to carry.
    rows: str | None = Field(default=None, pattern=_BUNDLE_PATH)


ReleaseImportAction = Literal["new_draft", "replaces_draft"]


class ReleaseImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ReleaseFileRole
    name: str
    action: ReleaseImportAction


class ReleaseImportPlan(BaseModel):
    """What an import writes, or with `--dry-run` would write: always drafts. `refused` names in
    words why a bundle cannot be imported; nothing is written when it is not empty."""

    model_config = ConfigDict(extra="forbid")

    dry_run: bool
    release: ReleaseMetadata | None = None
    items: list[ReleaseImportItem] = Field(default_factory=list)
    refused: list[str] = Field(default_factory=list)
    #: Connections the bundle names that the receiving environment has none of, by name.
    missing_connections: list[str] = Field(default_factory=list)
    #: What an import leaves to a person, in words: a screening list to subscribe to here, a
    #: large list's rows to import here.
    notes: list[str] = Field(default_factory=list)
    #: The import replaces the importer's own in-progress draft of the domain model: refused until
    #: they confirm it (`replace_own_draft`), then written. Another person's draft is never
    #: offered to confirm: it is refused in words naming them (CARRIES row 90).
    replaces_own_draft: bool = False


class ReleaseBundleInput(BaseModel):
    """A bundle sent to the import route: each file's text by its path (`release.yaml` the
    manifest). Bounded so an upload cannot be unbounded."""

    model_config = ConfigDict(extra="forbid")

    files: dict[str, str] = Field(max_length=500)


class ReleaseExport(BaseModel):
    """*Export*'s answer: the bundle's files as text by path, and how many published pipelines
    were left out, being marked above the exporter's view (rule 2: said, never silent)."""

    model_config = ConfigDict(extra="forbid")

    files: dict[str, str]
    left_out: int = Field(default=0, ge=0)


ALL_MODELS: list[type[BaseModel]] = [
    ReleaseMetadata,
    ReleaseFile,
    ReleaseSpec,
    DatasetRelease,
    ReleasedDomainModel,
    ReleasedPipeline,
    ReleasedReferenceList,
    ReleaseImportItem,
    ReleaseImportPlan,
    ReleaseBundleInput,
    ReleaseExport,
]
