"""`osprey.yaml` as a whole — the deployment, as a schema.

`05_DEPLOYMENT.md` §2.1: "`osprey.yaml` is the deployment. Version it, review it in a pull request,
and never hand-edit a generated artefact — regenerate instead." Until now only its `map:` section
had a schema (`schemas/mapconfig.py`); every other section existed as prose in `05_DEPLOYMENT.md`'s
own six-screen table and nowhere a machine could check. This module is the rest of it —
`06_DECISIONS.md` ADR-049's Stage 2 §1, accepted 24 September 2026.

**Every top-level key is optional, and that is a constraint from the review rather than a
convenience.** The committed root `osprey.yaml` contains a `map:` key and nothing else, and
`services/api/mapconfig_loader.load_map_config` reads it as a bare `raw["map"]`. A schema that
required `profile:`, `components:` or `governance:` would invalidate that file and break
`tests/test_demo_osprey_config_is_tier_1_only.py` on the day it landed. So every section defaults,
each default is documented at its own field, and
`tests/harness/test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates` holds the
line against a future edit that quietly makes one required.

**`map:` keeps the shape `schemas/mapconfig.py` already gives it** — reused here, never redefined.
Two schemas for one section is how the section's two readers start disagreeing.

**Extra keys are forbidden.** A misspelled `governence:` that silently did nothing would be
indistinguishable, in a generated deployment, from one that was never written — and the failure
would surface as a missing service rather than as a typo.

TypeScript types are generated from these (`generate_ts.py`); a drift between the two fails the
build (`tools/schemas_check.py`), per `CLAUDE.md`'s own Conventions.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from schemas.mapconfig import MapConfig

#: The Lite address (`06_DECISIONS.md` ADR-114 Amendment 4): the front proxy on port 80 of this
#: machine, the Glass at this name, the identity provider at `id.` and the dashboards at `bi.`.
DEFAULT_PUBLIC_ORIGIN = "http://ospreyflow.localhost"


class Profile(StrEnum):
    """`05_DEPLOYMENT.md` §1's three, not two — ADR-011. The gap between one laptop and ten
    machines is too wide to cross in one step, and `small` is the case that otherwise gets
    improvised."""

    LOCAL_LITE = "local-lite"
    SMALL = "small"
    CLUSTER = "cluster"


class GraphStore(StrEnum):
    """`05_DEPLOYMENT.md` §1's own profile table. `janusgraph` is declarable here before its
    adapter exists — Phase 8a builds that (ADR-022's third addendum) — because a schema that
    cannot express the `cluster` profile cannot validate a `cluster` deployment's own config."""

    ARCADEDB = "arcadedb"
    JANUSGRAPH = "janusgraph"


class AnalyticsEngine(StrEnum):
    """Same note as `GraphStore`: `clickhouse` is declarable before `analytics_clickhouse`
    exists."""

    DUCKDB = "duckdb"
    CLICKHOUSE = "clickhouse"


class SearchBackend(StrEnum):
    """`05_DEPLOYMENT.md` §3's reduced variant, as a declarable component rather than a hidden
    branch: "If Preflight finds less than 16 GB it offers a reduced variant that drops OpenSearch
    and falls back to PostgreSQL full-text, stating the trade-off on screen: search quality
    degrades and semantic search is unavailable."

    **Offering it is Preflight's job, not this schema's** (ADR-049 amendment 5, ownership confirmed
    by the owner 24 September 2026). Stage 2 §1 only has to be able to *render* the reduced variant
    when asked, which is what this field makes possible: setting `search: postgres-fulltext` drops
    the OpenSearch service from the rendered compose file. Nothing here decides when that is
    offered, and nothing applies it silently."""

    OPENSEARCH = "opensearch"
    POSTGRES_FULLTEXT = "postgres-fulltext"


#: Where the Conduit's container sees `components.storage.tiles`.
TILES_CONTAINER_PATH = "/data/tiles"


class StorageRoots(BaseModel):
    """`05_DEPLOYMENT.md` §2.1's Components screen: "the storage roots for data, staging and
    backups", plus `ingest` (owner ruling R6, 27 September 2026). Paths on the deployment host,
    not in this repository."""

    model_config = ConfigDict(extra="forbid")

    data: str = Field(default="/var/lib/osprey/data", description="Default: /var/lib/osprey/data")
    staging: str = Field(
        default="/var/lib/osprey/staging", description="Default: /var/lib/osprey/staging"
    )
    backups: str = Field(
        default="/var/lib/osprey/backups", description="Default: /var/lib/osprey/backups"
    )
    #: **Owner ruling R6, 27 September 2026 — the fourth root, and the one an analyst touches.**
    #: Round 13b's over-the-wire exit test found that a rendered deployment gives an analyst no
    #: route by which to supply a source file at all: `POST /v1/ingest/recipes` takes a
    #: `source_location` the *Conduit's own container* must be able to read, and nothing was
    #: mounted there. Eight acceptance rows (B1-B3, B6-B8, B13-B18) were unreachable through the
    #: analyst's own door in consequence — not because the test declined to try them, but because
    #: there was nothing to try.
    #:
    #: R6's answer is deliberately **not** a bare drop folder: this root is bind-mounted
    #: **read-only** into the Conduit for every profile, and the Ingest Studio's own Connect stage
    #: lists what is in it, so the analyst picks a file and continues to Profile -> Map on the
    #: existing canvas. The Conduit never writes here — an operator, or whatever moves evidence
    #: onto the host, owns the contents. A browser upload route is explicitly post-milestone.
    ingest: str = Field(
        default="/var/lib/osprey/ingest", description="Default: /var/lib/osprey/ingest"
    )
    #: **The folder the built basemap lives in (ADR-054 Amendment 4).** A map provider's
    #: `source` is a path inside the Conduit's container (`/data/tiles/...`,
    #: `TILES_CONTAINER_PATH`); this is the
    #: host folder mounted there, read-only, for every profile. Before it existed the generated
    #: deployment mounted nothing at that path, so tiles built on the host were never visible to the
    #: process that serves them.
    tiles: str = Field(
        default="/var/lib/osprey/tiles", description="Default: /var/lib/osprey/tiles"
    )


class ComponentsConfig(BaseModel):
    """`05_DEPLOYMENT.md` §2.1's Components screen. Defaults are the `local-lite` row of §1's own
    profile table, because that is the profile this repository is demonstrable on today."""

    model_config = ConfigDict(extra="forbid")

    graph_store: GraphStore = Field(default=GraphStore.ARCADEDB, description="Default: arcadedb")
    analytics_engine: AnalyticsEngine = Field(
        default=AnalyticsEngine.DUCKDB, description="Default: duckdb"
    )
    search: SearchBackend = Field(
        default=SearchBackend.OPENSEARCH,
        description="Default: opensearch. postgres-fulltext is §3's reduced variant.",
    )
    storage: StorageRoots = Field(default_factory=StorageRoots)
    source_path: str | None = Field(
        default=None,
        description=(
            "Default: none — the owned services (workspace, api, ingest) are PULLED, by the "
            "digest recorded in versions.lock, from the registry reference harness/render.py's "
            "own service_images names. This is the operator path: the harness image itself "
            "carries no services/ or apps/workspace source, and round 05's own finding was that "
            "the documented one-command bootstrap could not Launch without it — a clean laptop "
            "has no checkout. Set to a checkout root containing services/api/Dockerfile, "
            "services/ingest/Dockerfile and apps/workspace/Dockerfile (this repository's own "
            "root, for a developer/CI run) to BUILD owned images from source instead. Declared "
            "and the Dockerfiles absent is refused by name (harness.render.MissingDockerfileError) "
            "— never silently treated as the pull path."
        ),
    )


#: `06_DECISIONS.md` ADR-095: the models a deployment may choose for analysts' work, each pinned to
#: its Ollama manifest id (the first 12 hex characters `ollama list` shows), so the pull can
#: verify it (ADR-020). A model is added by adding it here, with its pin, and to ADR-095's table.
EXTRACTION_MODELS: dict[str, str] = {
    "qwen2.5:7b-instruct": "845dbda0ea48",
    "qwen2.5:14b-instruct": "7cdf5a0187d5",
}
VISION_MODELS: dict[str, str] = {"moondream:1.8b-v2-q4_K_M": "c865c80afc38"}
EMBEDDING_MODELS: dict[str, str] = {"all-minilm:22m-l6-v2-fp16": "1b226e2802db"}
#: Served by the whisper container, pinned by its image, not by Ollama.
TRANSCRIPTION_MODELS: tuple[str, ...] = ("Systran/faster-whisper-tiny.en",)

ExtractionModel = Literal["qwen2.5:7b-instruct", "qwen2.5:14b-instruct"]
VisionModel = Literal["moondream:1.8b-v2-q4_K_M"]
EmbeddingModel = Literal["all-minilm:22m-l6-v2-fp16"]
TranscriptionModel = Literal["Systran/faster-whisper-tiny.en"]

#: The context an extraction model is served with (ADR-095 decision 2), in tokens: room for a long
#: email whole; a longer text is read in windows rather than cut inside the model.
EXTRACTION_CONTEXT_TOKENS = 32768


ModelRole = Literal["extraction", "vision", "transcription", "embedding"]


class ModelProviderConfig(BaseModel):
    """A client's own model provider (ADR-114 decision 11, Amendment 6 point 4), reached through the
    deployment's LiteLLM gateway. For each role it names, it **replaces** the local model — for
    material whose handling code is in `models.sendable_handling_codes` only; anything else runs on
    the local model. Its key is never here: it is `OSPREY_MODEL_PROVIDER_KEY` at install."""

    model_config = ConfigDict(extra="forbid")

    #: LiteLLM's name for the provider: `openai`, `anthropic`, `gemini`, `azure`, `bedrock`…
    name: str
    #: The roles it takes, each with the provider's model for it.
    roles: dict[ModelRole, str]
    #: The provider's address, where it is not LiteLLM's default (an Azure deployment, a proxy).
    api_base: str | None = None

    @field_validator("name")
    @classmethod
    def _name_is_plain(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError(
                f"the provider name {value!r} is not one LiteLLM knows the shape of (lower-case, "
                "such as openai or anthropic)"
            )
        return value

    @field_validator("roles")
    @classmethod
    def _some_roles(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("a provider takes at least one role (extraction, vision, …)")
        for role, model in value.items():
            if not model.strip() or any(ch.isspace() for ch in model):
                raise ValueError(f"the {role} model {model!r} is not a model name")
        return value

    @field_validator("api_base")
    @classmethod
    def _https_only(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError(
                "the provider's address must be https://, so case content is encrypted"
            )
        return value


class ModelsConfig(BaseModel):
    """`05_DEPLOYMENT.md` §2.1's Models screen: "Local only, or local with a named hosted fallback
    — and if hosted, which handling codes may be sent to it. **Defaults to none**."

    The default here is that sentence, enforced rather than described: no hosted fallback, and an
    empty set of sendable handling codes. `04_VAULT_BACKEND.md` §4's egress exception is off unless
    something turns it on."""

    model_config = ConfigDict(extra="forbid")

    local_only: bool = Field(default=True, description="Default: true — no hosted fallback")
    hosted_fallback: str | None = Field(
        default=None, description="Default: none. A provider name, never a credential."
    )
    sendable_handling_codes: list[str] = Field(
        default_factory=list,
        description="Default: empty. Which handling codes may leave for a hosted model.",
    )
    #: ADR-114 decision 11, Amendment 6: a client's own provider, replacing the local model for the
    #: roles it names (sendable material only). Supersedes `hosted_fallback`, which nothing acts on.
    provider: ModelProviderConfig | None = None
    extraction: ExtractionModel = Field(
        default="qwen2.5:7b-instruct",
        description="ADR-095: the local model that extracts entities from text. Default: "
        "qwen2.5:7b-instruct, the model the product ships with.",
    )
    vision: VisionModel = Field(
        default="moondream:1.8b-v2-q4_K_M",
        description="ADR-095: the local model that describes an image and reads its text.",
    )
    transcription: TranscriptionModel = Field(
        default="Systran/faster-whisper-tiny.en",
        description="ADR-095: the local model that transcribes a video's speech.",
    )
    embedding: EmbeddingModel = Field(
        default="all-minilm:22m-l6-v2-fp16",
        description="ADR-095: the local model that turns text into vectors.",
    )

    @model_validator(mode="after")
    def _hosted_fallback_and_local_only_are_consistent(self) -> ModelsConfig:
        if self.provider is not None and self.local_only:
            raise ValueError(
                "models.local_only is true but a provider is named; set local_only: false to "
                "declare that case content may leave the deployment"
            )
        if self.provider is not None and self.hosted_fallback is not None:
            raise ValueError(
                "models.provider replaces the old hosted_fallback; name only the provider"
            )
        if self.local_only and self.hosted_fallback is not None:
            raise ValueError(
                "models.local_only is true but a hosted_fallback is named; set local_only: false "
                "to declare the egress exception explicitly rather than by implication"
            )
        if self.sendable_handling_codes and self.hosted_fallback is None and self.provider is None:
            raise ValueError(
                "models.sendable_handling_codes is set but no hosted_fallback is named; handling "
                "codes cannot be sendable to nothing"
            )
        return self


class GovernanceConfig(BaseModel):
    """`05_DEPLOYMENT.md` §2.1's Governance screen: "Identity provider, handling scheme, ontology.
    Ships with a UK law-enforcement scheme, a US criminal-intelligence scheme, and the default
    ontology."

    `real_data_exceptions` is the **reference** ADR-049's Stage 2 §6 puts on the Governance panel —
    a path to the local, never-committed exceptions list, not its contents. The list itself is
    gitignored (`config/real_data_exceptions.yaml`, standing rule 3 / `CLAUDE.md` rule 9 /
    ADR-035 §C3) and must stay that way: this field records where to look, exactly as §2.5 requires
    of every credential, and for the same reason."""

    model_config = ConfigDict(extra="forbid")

    identity_provider: str = Field(
        default="keycloak", description="Default: keycloak (03_CONDUIT_MIDDLEWARE.md §6)"
    )
    handling_scheme: str = Field(
        default="uk-law-enforcement", description="Default: uk-law-enforcement"
    )
    ontology: str = Field(default="default", description="Default: default")
    organisation_sign_in: str | None = Field(
        default=None,
        description=(
            "The alias of an organisation's own identity provider brokered by Keycloak. When set, "
            "the welcome page offers *Continue with organisation sign-in*, which goes straight to "
            "it (ADR-115 decision 3). Default: none — one *Sign in* to the OspreyFlow form."
        ),
    )
    marking: str | None = Field(
        default=None,
        description=(
            "The protective marking shown where no case data is on screen: the welcome page, Home, "
            "the Ingest Studio and the Admin area; inside a case, the strip shows this or the "
            "highest marking on screen, whichever is higher (ADR-115 decision 2). One of the "
            "handling scheme's classifications. Default: the scheme's lowest."
        ),
    )
    real_data_exceptions: str = Field(
        default="config/real_data_exceptions.yaml",
        description=(
            "Default: config/real_data_exceptions.yaml. A path to the gitignored list, never its "
            "contents."
        ),
    )


class ClusterHost(BaseModel):
    """One declared machine. `05_DEPLOYMENT.md` §2.1's Preflight screen runs "for `cluster`
    connectivity to every declared host" against this list — Stage 2 §2's check, this schema's
    declaration."""

    model_config = ConfigDict(extra="forbid")

    name: str
    address: str
    roles: list[str] = Field(default_factory=list)


class ClusterConfig(BaseModel):
    """Only meaningful at `profile: cluster`; declarable (and empty) at the other two so a profile
    change does not need the file restructured."""

    model_config = ConfigDict(extra="forbid")

    hosts: list[ClusterHost] = Field(default_factory=list)

    @model_validator(mode="after")
    def _host_names_are_unique(self) -> ClusterConfig:
        names = [h.name for h in self.hosts]
        if len(set(names)) != len(names):
            raise ValueError("cluster host names must be unique")
        return self


class NetworkConfig(BaseModel):
    """What this deployment publishes to its host.

    `05_DEPLOYMENT.md` §7: "Every service on an internal network. Only the workspace and the
    Conduit are exposed, behind a reverse proxy terminating TLS." Since the owner's decision of
    25 September 2026 (§2.6 item 1) **the workspace's own image is that reverse proxy** — its nginx
    proxies `/v1` and the delta WebSocket to the Conduit on the internal network — so the normal
    deployment publishes one port, not two, and the Conduit is reachable without being exposed.
    """

    model_config = ConfigDict(extra="forbid")

    expose_conduit: bool = Field(
        default=False,
        description=(
            "Default: false. Publish the Conduit's own port on the host in addition to the "
            "workspace's. Not needed to use the deployment — the workspace proxies /v1 — and "
            "turning it on widens the exposed surface by a whole tier. For an operator debugging "
            "the Conduit directly, or a second client that is not the Glass."
        ),
    )
    public_origin: str = Field(
        default=DEFAULT_PUBLIC_ORIGIN,
        description=(
            "Default: http://ospreyflow.localhost. The origin a browser uses to reach the Glass; "
            "the identity provider is `id.` and the dashboards `bi.` in front of the same host, "
            "with the same scheme and port, and the front proxy publishes that port "
            "(ADR-114 Amendment 4). "
            "`06_DECISIONS.md` ADR-050 objection 2's resolution: the identity-provider realm is "
            "rendered from this value at apply time and the Glass's public client is registered "
            "with an exact redirect URI and post-logout URI derived from it — no wildcards. "
            "Change this to move the deployment to another name or port; nothing else needs to "
            "agree with it."
        ),
    )

    @model_validator(mode="after")
    def _public_origin_is_a_bare_origin(self) -> NetworkConfig:
        if not (self.public_origin.startswith("http://") or self.public_origin.startswith("https://")):
            raise ValueError(
                f"network.public_origin {self.public_origin!r} must start with http:// or https:// "
                "— it is an origin the realm renders an exact redirect URI from, not a path"
            )
        if self.public_origin.endswith("/"):
            raise ValueError(
                f"network.public_origin {self.public_origin!r} must not end with '/' — the "
                "redirect URI is derived by appending a single trailing slash, exactly once"
            )
        return self


class ReportingConfig(BaseModel):
    """Dashboards for the business (`06_DECISIONS.md` ADR-111 Amendment 2): the report sync service
    and Superset, each a component of its own with its own memory, both off by default."""

    model_config = ConfigDict(extra="forbid")

    sync: bool = Field(default=False, description="Default: false — run report-sync")
    sync_interval_seconds: int = Field(default=900, ge=60, description="Default: 900")
    sync_memory: str = Field(default="256m", description="Default: 256m")
    superset: bool = Field(default=False, description="Default: false — run Superset")
    superset_memory: str = Field(default="2g", description="Default: 2g")


class WelcomeConfig(BaseModel):
    """The welcome page before sign-in (ADR-115 decision 8): its About section, and the footer's
    links — the deploying organisation's own documents, each shown only when its address is
    given."""

    model_config = ConfigDict(extra="forbid")

    about: bool = Field(
        default=True, description="Default: on. Off for an internal-only deployment."
    )
    account_help: str | None = Field(default=None, description="Default: no link")
    accessibility: str | None = Field(default=None, description="Default: no link")
    privacy: str | None = Field(default=None, description="Default: no link")
    service_status: str | None = Field(default=None, description="Default: no link")

    @field_validator("account_help", "accessibility", "privacy", "service_status")
    @classmethod
    def _a_web_address(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError(f"welcome.{info.field_name} must be an http(s) address, not {value!r}")
        return value


class MailConfig(BaseModel):
    """The mail server the identity provider sends invitations and sign-in resets through
    (`06_DECISIONS.md` ADR-114 Amendment 5). Without one, people are signed in by a one-time code.
    **No password here**: `osprey.yaml` never holds a secret (§2.5); the install reads it from
    `OSPREY_SMTP_PASSWORD` and keeps it in the deployment's own `deployment.env`."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, description="The mail server's name")
    port: int = Field(default=587, ge=1, le=65535, description="Default: 587")
    from_address: str = Field(min_length=3, description="The address invitations come from")
    starttls: bool = Field(default=True, description="Default: true")
    username: str | None = Field(
        default=None,
        description="Default: none — a relay that takes mail without signing in. With one, the "
        "password comes from OSPREY_SMTP_PASSWORD at install.",
    )


class OspreyConfig(BaseModel):
    """The whole of `osprey.yaml`.

    Validating the committed root file — which has only `map:` — must succeed, so every field here
    has a default. `map` is `None` rather than a stub when absent: a deployment with no basemap is
    a real state (nothing has been chosen on the Geospatial screen yet), and inventing an empty
    `MapConfig` would fail `MapConfig`'s own `min_length=1` for no reason."""

    model_config = ConfigDict(extra="forbid")

    profile: Profile = Field(default=Profile.LOCAL_LITE, description="Default: local-lite")
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    cluster: ClusterConfig = Field(default_factory=ClusterConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    map: MapConfig | None = Field(default=None, description="Default: none declared")
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)
    mail: MailConfig | None = Field(default=None, description="Default: none — one-time codes")
    welcome: WelcomeConfig = Field(default_factory=WelcomeConfig)

    @model_validator(mode="after")
    def _cluster_hosts_belong_to_the_cluster_profile(self) -> OspreyConfig:
        if self.cluster.hosts and self.profile is not Profile.CLUSTER:
            raise ValueError(
                f"cluster.hosts is declared but profile is {self.profile.value!r}; hosts are only "
                "meaningful at profile: cluster"
            )
        if self.profile is Profile.CLUSTER and not self.cluster.hosts:
            raise ValueError("profile: cluster declares no cluster.hosts")
        return self


#: Exported to `generate_ts.py`. `MapConfig` and its own members are already exported by
#: `schemas/mapconfig.py`'s own `ALL_MODELS` and are deliberately not repeated here — the generator
#: writes one file per model name, so listing a model twice writes it twice.
ALL_MODELS: tuple[type[BaseModel], ...] = (
    StorageRoots,
    ComponentsConfig,
    ModelsConfig,
    GovernanceConfig,
    ClusterHost,
    ClusterConfig,
    NetworkConfig,
    OspreyConfig,
)
