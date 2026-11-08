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
from urllib.parse import urlsplit

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

#: From a rendered deployment's folder, `<product>/deploy/generated/<name>/`, back to the product
#: folder that holds `osprey.yaml` (ADR-054 Amendment 6).
GENERATED_TO_PRODUCT = "../../.."


def host_folder_source(value: str) -> str:
    """`components.storage.ingest` or `tiles` as a Compose bind source (ADR-054 Amendment 6). An
    absolute path is used as it is. A relative one is read from the product folder, and Compose
    reads a relative source from the folder `compose.yaml` is in, so it is written relative to that
    folder: no rendered file then carries the host's own absolute path."""
    return value if value.startswith("/") else f"{GENERATED_TO_PRODUCT}/{value}"


class StorageRoots(BaseModel):
    """`05_DEPLOYMENT.md` §2.1's Components screen: "the storage roots for data, staging and
    backups", plus `ingest` (owner ruling R6, 27 September 2026). Paths on the deployment host,
    not in this repository."""

    model_config = ConfigDict(extra="forbid")

    data: str = Field(
        default="/var/lib/osprey/data",
        description=(
            "Default: /var/lib/osprey/data. Where the deployment keeps its data inside the "
            "containers."
        ),
    )
    staging: str = Field(
        default="/var/lib/osprey/staging",
        description=(
            "Default: /var/lib/osprey/staging. Where loads stage their rows before they reach the "
            "graph."
        ),
    )
    backups: str = Field(
        default="/var/lib/osprey/backups",
        description="Default: /var/lib/osprey/backups. Where backups are written.",
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
        default="/var/lib/osprey/ingest",
        description=(
            "Default: /var/lib/osprey/ingest. The host folder of source files the Ingest Studio "
            "lists (read-only to it; uploads go to its uploaded/ folder). A relative path is read "
            "from the folder osprey.yaml is in."
        ),
    )
    #: **The folder the built basemap lives in (ADR-054 Amendment 4).** A map provider's
    #: `source` is a path inside the Conduit's container (`/data/tiles/...`,
    #: `TILES_CONTAINER_PATH`); this is the
    #: host folder mounted there, read-only, for every profile. Before it existed the generated
    #: deployment mounted nothing at that path, so tiles built on the host were never visible to the
    #: process that serves them.
    tiles: str = Field(
        default="/var/lib/osprey/tiles",
        description=(
            "Default: /var/lib/osprey/tiles. The host folder a built basemap lives in. A relative "
            "path is read from the folder osprey.yaml is in."
        ),
    )


class ComponentsConfig(BaseModel):
    """`05_DEPLOYMENT.md` §2.1's Components screen. Defaults are the `local-lite` row of §1's own
    profile table, because that is the profile this repository is demonstrable on today."""

    model_config = ConfigDict(extra="forbid")

    graph_store: GraphStore = Field(
        default=GraphStore.ARCADEDB, description="Default: arcadedb. The graph store."
    )
    analytics_engine: AnalyticsEngine = Field(
        default=AnalyticsEngine.DUCKDB,
        description=(
            "Default: duckdb. Where events are counted: DuckDB inside the Conduit, or ClickHouse "
            "shared by several."
        ),
    )
    post_ingest_resolution: bool = Field(
        default=True,
        description=(
            "Default: true. Whether a load queues entity resolution afterwards "
            "(`OSPREY_POST_INGEST_RESOLUTION`). False for a demonstration whose people must not "
            "gain automatic `SAME_AS` links; an analyst's own Resolve now still works."
        ),
    )
    search: SearchBackend = Field(
        default=SearchBackend.OPENSEARCH,
        description="Default: opensearch. Search; postgres-fulltext is the lighter variant.",
    )
    storage: StorageRoots = Field(default_factory=StorageRoots)
    source_path: str | None = Field(
        default=None,
        description=(
            "Default: none — the owned services (workspace, api, ingest) are PULLED, by the "
            "digest recorded in versions.lock, from the registry reference harness/render.py's "
            "own service_images names. This is the operator path: the harness image itself "
            "carries no services/ or apps/workspace source, and a review found that "
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
#: ADR-135 Amendment 1 decision 3: the extraction model on an NVIDIA GPU when none is named.
GPU_EXTRACTION_MODEL: ExtractionModel = "qwen2.5:14b-instruct"
VisionModel = Literal["moondream:1.8b-v2-q4_K_M"]
EmbeddingModel = Literal["all-minilm:22m-l6-v2-fp16"]
TranscriptionModel = Literal["Systran/faster-whisper-tiny.en"]

#: The context an extraction model is served with (ADR-095 decision 2), in tokens: room for a long
#: email whole; a longer text is read in windows rather than cut inside the model.
EXTRACTION_CONTEXT_TOKENS = 32768


ModelRole = Literal["extraction", "vision", "transcription", "embedding"]


#: The label analysts see for the providers ADR-135 names; any other is its name, capitalised.
PROVIDER_LABELS: dict[str, str] = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Gemini"}

#: The engine name that means the deployment's own models (ADR-135 decision 1).
LOCAL_ENGINE = "local"


#: ADR-136: how long a contract reference may be — a name or number, not a document.
MAX_CONTRACT_REFERENCE = 200
#: A provider key's own prefixes (OpenAI and Anthropic `sk-`, Google `AIza`).
_KEY_PREFIXES = ("sk-", "AIza")


def _looks_like_a_key(text: str) -> bool:
    """A key's shape: a known key prefix, or one unbroken run of 24 or more letters, digits, `-`
    and `_` mixing letters and digits. A reference in words (`DPA-2026-0001, signed 3 March`) has
    spaces or is short."""
    if any(word.startswith(_KEY_PREFIXES) for word in text.split()):
        return True
    return bool(
        re.fullmatch(r"[A-Za-z0-9_\-]{24,}", text)
        and re.search(r"[A-Za-z]", text)
        and re.search(r"[0-9]", text)
    )


class ModelProviderConfig(BaseModel):
    """A client's own model provider (ADR-114 decision 11, Amendment 6 point 4; ADR-135), reached
    through the deployment's LiteLLM gateway, for material whose handling code is in
    `models.sendable_handling_codes` only; anything else runs on the local model. Its key is never
    here: it is `OSPREY_MODEL_KEY_<NAME>` at install (`OSPREY_MODEL_PROVIDER_KEY` for the single
    `models.provider`), kept in the deployment's `deployment.env` and read by the gateway alone."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="LiteLLM's name for the provider: openai, anthropic, gemini, azure, bedrock…"
    )
    label: str | None = Field(
        default=None,
        description="ADR-135: the name analysts see for this engine. Default: OpenAI, Anthropic "
        "or Gemini for those three, else the provider's name capitalised.",
    )
    roles: dict[ModelRole, str] = Field(
        description="The roles it takes, each with the provider's model for it"
    )
    api_base: str | None = Field(
        default=None,
        description="The provider's address, where it is not LiteLLM's default (an Azure "
        "deployment, a proxy)",
    )
    privacy_contract: bool = Field(
        default=False,
        description="ADR-136: true when the deployment's organisation holds a data-processing "
        "agreement with the provider covering this key. A dataset whose egress is `contracted` is "
        "sent only to a provider marked so. Default: false.",
    )
    contract_reference: str | None = Field(
        default=None,
        description="ADR-136: the agreement's reference, in words (for example DPA 2026/07); "
        "never a secret. Shown beside the mark.",
    )

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

    @field_validator("contract_reference")
    @classmethod
    def _reference_is_words(cls, value: str | None) -> str | None:
        """ADR-136 decision 1: words, never a secret. One line, short, and not shaped like a key —
        the mark and its reference are shown in the Admin area and the analysts' engine choice."""
        if value is None:
            return None
        if "\n" in value or "\r" in value:
            raise ValueError("the contract reference is one line of words")
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > MAX_CONTRACT_REFERENCE:
            raise ValueError(
                f"the contract reference is at most {MAX_CONTRACT_REFERENCE} characters"
            )
        if not re.fullmatch(r"[A-Za-z0-9 .,;:/()&'_+\-]+", cleaned):
            # It travels to the Conduit in `deployment.env`, where `$` and ` #` would be read as
            # an interpolation and a comment, and in JSON, where a quote or backslash is escaped.
            raise ValueError(
                "the contract reference may hold letters, digits, spaces and . , ; : / ( ) & ' _ "
                "+ - only"
            )
        if _looks_like_a_key(cleaned):
            raise ValueError(
                "the contract reference looks like a key; it is shown to analysts, so give the "
                "agreement's name or number in words, and the key with ospreyflow models key"
            )
        return cleaned

    @model_validator(mode="after")
    def _labelled(self) -> ModelProviderConfig:
        if self.label is None or not self.label.strip():
            self.label = PROVIDER_LABELS.get(self.name, self.name.replace("_", " ").title())
        return self


def provider_key_variable(provider: str, *, single: bool = False) -> str:
    """`OSPREY_MODEL_KEY_<NAME>`; `OSPREY_MODEL_PROVIDER_KEY` for the single `models.provider`."""
    return "OSPREY_MODEL_PROVIDER_KEY" if single else f"OSPREY_MODEL_KEY_{provider.upper()}"


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
    provider: ModelProviderConfig | None = Field(
        default=None,
        description="ADR-114 Amendment 6: one provider, read as a one-entry `providers` whose "
        "roles default to it; its key is OSPREY_MODEL_PROVIDER_KEY. Not with `providers`.",
    )
    #: ADR-135 decision 1: each enabled provider (engine), its models per role, its label.
    providers: list[ModelProviderConfig] = Field(
        default_factory=list,
        description="ADR-135: the providers an administrator enables; each key is "
        "OSPREY_MODEL_KEY_<NAME>, entered at install or with `ospreyflow models key`.",
    )
    #: ADR-135 decision 1: each role's default engine — `local` or an enabled provider's name.
    defaults: dict[ModelRole, str] = Field(
        default_factory=dict,
        description="ADR-135: each role's default engine, `local` or an enabled provider's name. "
        "A role not named runs on `local` (for the single `provider`, on it).",
    )
    extraction: ExtractionModel = Field(
        default="qwen2.5:7b-instruct",
        description="ADR-095: the local model that extracts entities from text. Default: "
        "qwen2.5:7b-instruct, the model the product ships with; with resources.gpu: nvidia and "
        "this not named, qwen2.5:14b-instruct (ADR-135 Amendment 1).",
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

    @property
    def enabled_providers(self) -> list[ModelProviderConfig]:
        """ADR-135: every enabled provider — `providers`, or the single `provider` as a one-entry
        list."""
        return [self.provider] if self.provider is not None else list(self.providers)

    def key_variable(self, provider: str) -> str:
        """Where a provider's key is kept in `deployment.env` (ADR-135 decision 2):
        `OSPREY_MODEL_KEY_<NAME>`, or `OSPREY_MODEL_PROVIDER_KEY` for the single `provider`, so an
        install made before ADR-135 keeps working. `ospreyflow models` (`cli/ospreyflow/models.py`)
        names it by the same rule; `test_model_engines.py` holds the two to each other."""
        return provider_key_variable(provider, single=self.provider is not None)

    @property
    def role_defaults(self) -> dict[ModelRole, str]:
        """Each role's default engine as named. The single `provider` keeps Amendment 6's meaning:
        the roles it takes default to it. A role not here runs on `local`."""
        if self.provider is not None and not self.defaults:
            return {role: self.provider.name for role in self.provider.roles}
        return dict(self.defaults)

    @model_validator(mode="after")
    def _hosted_fallback_and_local_only_are_consistent(self) -> ModelsConfig:
        if self.provider is not None and self.providers:
            raise ValueError(
                "both models.provider and models.providers are named; list every provider under "
                "providers (provider is the older one-provider form)"
            )
        enabled = self.enabled_providers
        seen: set[str] = set()
        for provider in enabled:
            if provider.name in seen:
                raise ValueError(f"the provider {provider.name} is named twice in models.providers")
            seen.add(provider.name)
        if enabled and self.local_only:
            raise ValueError(
                "models.local_only is true but a provider is named; set local_only: false to "
                "declare that case content may leave the deployment"
            )
        if enabled and self.hosted_fallback is not None:
            raise ValueError(
                "models.provider replaces the old hosted_fallback; name only the provider"
            )
        if self.local_only and self.hosted_fallback is not None:
            raise ValueError(
                "models.local_only is true but a hosted_fallback is named; set local_only: false "
                "to declare the egress exception explicitly rather than by implication"
            )
        if self.sendable_handling_codes and self.hosted_fallback is None and not enabled:
            raise ValueError(
                "models.sendable_handling_codes is set but no hosted_fallback is named; handling "
                "codes cannot be sendable to nothing"
            )
        by_name = {p.name: p for p in enabled}
        for role, engine in self.defaults.items():
            if engine == LOCAL_ENGINE:
                continue
            if engine not in by_name:
                raise ValueError(
                    f"models.defaults names {engine} for {role}, which is not an enabled engine "
                    f"(local, or one of: {', '.join(by_name) or 'no provider is enabled'})"
                )
            if role not in by_name[engine].roles:
                raise ValueError(
                    f"models.defaults names {engine} for {role}, but {engine} takes no {role} "
                    "model; add one under its roles, or choose another engine"
                )
        return self


class OrganisationProvider(BaseModel):
    """ADR-114 Amendment 33 decision 4: the organisation's own identity provider (OpenID Connect —
    Entra ID, ADFS, an internal Keycloak), brokered by the deployment's Keycloak. Names and
    addresses only: the client secret is `OSPREY_ORG_SIGN_IN_SECRET` in the installer's
    environment, kept in `deployment.env` and set through Keycloak's admin API, never here
    (`05_DEPLOYMENT.md` §2.5). A person arriving through it gets no role and no clearance until an
    administrator grants them (the owner's answer 6: no group-to-role mapping)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        min_length=1,
        description="The provider's name as people know it, shown on the welcome page's button "
        "(Continue with <label>) and on the identity provider's own sign-in pages (for example "
        "'Example Department account').",
    )
    issuer: str = Field(
        description="The provider's issuer, an https:// address; its discovery document is read "
        "from <issuer>/.well-known/openid-configuration (for Entra ID, "
        "https://login.microsoftonline.com/<tenant>/v2.0).",
    )
    client_id: str = Field(
        min_length=1,
        description="The application (client) id the organisation registered for OspreyFlow.",
    )
    trust_email: bool = Field(
        default=False,
        description="ADR-114 Amendment 33, 'Step 33': true joins a person arriving through the "
        "organisation to the OspreyFlow account holding the same email address, automatically, "
        "with its roles and clearance. Off by default: a person whose email an account holds is "
        "refused in words, and an administrator joins them in Admin, People and roles. Turn it on "
        "only with the organisation's security officer's written sign-off that every address its "
        "provider gives is verified and cannot be set by the person who holds it: anyone who can "
        "make the provider give an address takes over the account that holds it (the 2023 "
        "'nOAuth' account takeovers).",
    )

    @field_validator("issuer")
    @classmethod
    def _issuer_is_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError(
                f"governance.organisation_provider.issuer {value!r} must be an https:// address: "
                "the provider's keys and tokens are read from it"
            )
        if value.endswith("/"):
            raise ValueError(
                f"governance.organisation_provider.issuer {value!r} must not end with '/': it is "
                "compared exactly with the issuer in the provider's tokens"
            )
        return value


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
        default="keycloak",
        description="Default: keycloak. The identity provider people sign in through.",
    )
    handling_scheme: str = Field(
        default="uk-law-enforcement",
        description="Default: uk-law-enforcement. The handling scheme every item is marked under.",
    )
    ontology: str = Field(
        default="default", description="Default: default. The ontology the deployment starts from."
    )
    organisation_sign_in: str | None = Field(
        default=None,
        description=(
            "The alias of an organisation's own identity provider brokered by Keycloak. When set, "
            "the welcome page offers *Continue with organisation sign-in* (*Continue with "
            "<label>* when `organisation_provider` names one), which goes straight to it (ADR-115 "
            "decision 3, Amendment 5). Default: none — one *Sign in* to the OspreyFlow form."
        ),
    )
    organisation_provider: OrganisationProvider | None = Field(
        default=None,
        description=(
            "Small on a server of your own only (ADR-114 Amendment 33 decision 4): the "
            "organisation's identity provider that `organisation_sign_in` names, which `ospreyflow "
            "install` and `ospreyflow repair-sign-in` register in Keycloak. Default: none — "
            "people sign in with accounts an administrator makes."
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

    name: str = Field(description="The machine's name")
    address: str = Field(description="Where the machine is reached")
    roles: list[str] = Field(default_factory=list, description="What runs on it")


class ClusterConfig(BaseModel):
    """Only meaningful at `profile: cluster`; declarable (and empty) at the other two so a profile
    change does not need the file restructured."""

    model_config = ConfigDict(extra="forbid")

    hosts: list[ClusterHost] = Field(default_factory=list)
    namespace: str = Field(
        default="ospreyflow",
        pattern=r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$",
        description=(
            "The Kubernetes namespace the deployment is installed in (05_DEPLOYMENT.md §3b)"
        ),
    )
    storage_class: str | None = Field(
        default=None,
        description="The storage class each store's own volumes use; the cluster's default when "
        "unset",
    )
    shared_storage_class: str | None = Field(
        default=None,
        description="Required for a cluster: the storage class of the one volume every Conduit "
        "shares (ReadWriteMany) — EFS on AWS, Azure Files on Azure",
    )

    @property
    def declared(self) -> bool:
        """Anything set that only a cluster reads."""
        return bool(
            self.hosts
            or self.namespace != "ospreyflow"
            or self.storage_class
            or self.shared_storage_class
        )

    @model_validator(mode="after")
    def _host_names_are_unique(self) -> ClusterConfig:
        names = [h.name for h in self.hosts]
        if len(set(names)) != len(names):
            raise ValueError("cluster host names must be unique")
        return self


class TlsFiles(BaseModel):
    """ADR-114 Amendment 33 decision 3: the organisation's own certificate for a Small on a server
    of its own. Paths on the server, absolute; the front proxy mounts the two files read-only and
    the key is never copied (not into the deployment folder, not into a backup). Checked before
    anything starts by `harness/tls_check.py`."""

    model_config = ConfigDict(extra="forbid")

    certificate: str = Field(
        description="The server certificate, then its intermediates, in PEM: an absolute path."
    )
    key: str = Field(
        description="The certificate's private key in PEM, unencrypted: an absolute path. Owned by "
        "the installing account, mode 600; the front proxy runs as that account to read it."
    )
    ca: str | None = Field(
        default=None,
        description="Optional: the organisation's root certificate (PEM), an absolute path. With "
        "it, the certificate's chain is checked to reach it, and the host's own tools trust it.",
    )

    @field_validator("certificate", "key", "ca")
    @classmethod
    def _absolute(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not value.startswith("/"):
            raise ValueError(
                f"network.tls.{info.field_name} {value!r} must be an absolute path on the server "
                "(from /)"
            )
        return value


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

    tls: TlsFiles | None = Field(
        default=None,
        description=(
            "Small on a server of your own only (ADR-114 Amendment 33): the organisation's own "
            "certificate and key, served by the front proxy with no certificate management and "
            "no call out. Default: none — Small's front proxy obtains a certificate itself, which "
            "needs a public name and the internet."
        ),
    )
    redirect_http: bool = Field(
        default=False,
        description=(
            "Small on a server of your own, with network.tls only: also publish port 80, and only "
            "to send people to the https:// address. Default: false — port 443 alone."
        ),
    )
    listen_address: str | None = Field(
        default=None,
        description=(
            "Small on a server of your own, with network.tls only: the one address of the server "
            "the front proxy publishes on. Default: none — every interface."
        ),
    )

    @model_validator(mode="after")
    def _public_origin_is_a_bare_origin(self) -> NetworkConfig:
        if not (
            self.public_origin.startswith("http://") or self.public_origin.startswith("https://")
        ):
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
    sync_interval_seconds: int = Field(
        default=900,
        ge=60,
        description="Default: 900. How often each case is pulled into the mart, in seconds.",
    )
    sync_memory: str = Field(
        default="256m", description="Default: 256m. Report sync's memory limit."
    )
    superset: bool = Field(default=False, description="Default: false — run Superset")
    superset_memory: str = Field(default="2g", description="Default: 2g. Superset's memory limit.")


class MonitoringConfig(BaseModel):
    """Monitoring and alerts (`06_DECISIONS.md` ADR-133 ruling 3): whom a new hotlist's alerts reach
    in the shared alert queue, and whether its owner may change that. A hotlist made before the
    setting existed keeps `only_me` whatever is set here."""

    model_config = ConfigDict(extra="forbid")

    hotlist_audience: Literal["only_me", "team"] = Field(
        default="only_me",
        description=(
            "Default: only_me. Whom a new hotlist's alerts reach: its owner alone (only_me), or "
            "also the owner's team, the people of the owner's organisational unit (team). Applies "
            "to hotlists made after it is set, never to an existing one."
        ),
    )
    hotlist_audience_editable: bool = Field(
        default=True,
        description=(
            "Default: true. Whether a hotlist's owner may choose its audience, when making it or "
            "later. When false, every new hotlist takes hotlist_audience and a change is refused."
        ),
    )


class WelcomeConfig(BaseModel):
    """The welcome page before sign-in (ADR-115 decision 8): its About section, and the footer's
    links — the deploying organisation's own documents, each shown only when its address is
    given."""

    model_config = ConfigDict(extra="forbid")

    about: bool = Field(
        default=True, description="Default: on. Off for an internal-only deployment."
    )
    account_help: str | None = Field(
        default=None, description="Default: no link. Where people get help with their account."
    )
    accessibility: str | None = Field(
        default=None, description="Default: no link. The organisation's accessibility statement."
    )
    privacy: str | None = Field(
        default=None, description="Default: no link. The organisation's privacy notice."
    )
    service_status: str | None = Field(
        default=None, description="Default: no link. A page saying whether the service is up."
    )

    @field_validator("account_help", "accessibility", "privacy", "service_status")
    @classmethod
    def _a_web_address(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError(f"welcome.{info.field_name} must be an http(s) address, not {value!r}")
        return value


#: What Compose takes as a project name: lowercase letters, digits and hyphens, starting with a
#: letter or digit.
_COMPOSE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class DeploymentConfig(BaseModel):
    """Which deployment this is, on a machine that may run more than one (ADR-132 Amendment 1)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        description=(
            "Default: osprey-<profile>, rendered to deploy/generated/<profile>/. Names this "
            "deployment's Compose project, its volumes and its rendered folder, so a second "
            "deployment on the same machine shares none of them."
        ),
    )
    #: ADR-138 decision 2: a deployment installed beside another (`ospreyflow install --name`)
    #: publishes its graph store on a loopback port of its own, so two share no port.
    graph_port: int | None = Field(
        default=None,
        ge=1024,
        le=65535,
        description=(
            "Default: 2480. The port on this machine (127.0.0.1 only) the graph store's own tools "
            "reach it at. A deployment installed beside another with ospreyflow install --name is "
            "given one of its own, so the two share no port."
        ),
    )

    @field_validator("name")
    @classmethod
    def _a_compose_name(cls, value: str | None) -> str | None:
        if value is not None and not _COMPOSE_NAME.match(value):
            raise ValueError(
                f"deployment.name {value!r} must be lowercase letters, digits and hyphens, "
                "starting with a letter or digit"
            )
        return value


class AppearanceConfig(BaseModel):
    """How every page of the deployment looks (ADR-132): the deployment's brand, which is not the
    viewer's light or dark choice. `govuk` is the GOV.UK look the Service Manual requires on a
    `*.service.gov.uk` service: its header and footer, GDS Transport, its colours and the light
    page. The network's own colours and shapes are the same under either brand. Read by the Glass
    from `/deployment.json`; the Admin console's Appearance tab is to write the same section."""

    model_config = ConfigDict(extra="forbid")

    brand: Literal["ospreyflow", "govuk"] = Field(
        default="ospreyflow",
        description="Default: ospreyflow. The GOV.UK look, for a service on a gov.uk domain only.",
    )
    service_name: str | None = Field(
        default=None,
        min_length=1,
        description="Default: none. The service's name, in the page title.",
    )
    organisation: str | None = Field(
        default=None,
        min_length=1,
        description="Default: none. The organisation in the GOV.UK footer and the page title.",
    )
    phase: Literal["alpha", "beta", "live", "none"] = Field(
        default="none",
        description="Default: none. The phase banner shows at alpha or beta.",
    )


class MailConfig(BaseModel):
    """The mail server the identity provider sends invitations and sign-in resets through
    (`06_DECISIONS.md` ADR-114 Amendment 5). Without one, people are signed in by a one-time code.
    **No password here**: `osprey.yaml` never holds a secret (§2.5); the install reads it from
    `OSPREY_SMTP_PASSWORD` and keeps it in the deployment's own `deployment.env`."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, description="The mail server's name")
    port: int = Field(
        default=587, ge=1, le=65535, description="Default: 587. The mail server's port."
    )
    from_address: str = Field(min_length=3, description="The address invitations come from")
    starttls: bool = Field(
        default=True, description="Default: true. Whether mail is sent over TLS (STARTTLS)."
    )
    username: str | None = Field(
        default=None,
        description="Default: none — a relay that takes mail without signing in. With one, the "
        "password comes from OSPREY_SMTP_PASSWORD at install.",
    )


class ExternalPostgres(BaseModel):
    """A cloud's managed PostgreSQL (`05_DEPLOYMENT.md` §3a). The password is never here: it arrives
    at apply as `OSPREY_POSTGRES_PASSWORD`, from the cloud's secret store."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, description="The managed server's address")
    port: int = Field(default=5432, description="Its port")
    database: str = Field(default="ospreyflow", description="The deployment's database on it")
    user: str = Field(
        default="osprey", description="The login, which needs CREATEROLE and CREATEDB there"
    )
    sslmode: Literal["require", "verify-ca", "verify-full"] = Field(
        default="require", description="Default: require. A managed server is reached over TLS."
    )


class ExternalObjectStore(BaseModel):
    """A cloud's S3 (`05_DEPLOYMENT.md` §3a) for staging, site images, tiles, backups and media."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, description="Host and port, no scheme: always HTTPS")
    region: str = Field(min_length=1, description="The region the buckets live in")
    credentials: Literal["instance", "keys"] = Field(
        default="instance",
        description="Default: instance — the server's own cloud identity, no key anywhere; `keys` "
        "reads OSPREY_S3_ACCESS_KEY and OSPREY_S3_SECRET_KEY at apply.",
    )
    bucket_prefix: str = Field(
        default="ospreyflow-", description="Each bucket is <prefix><name>, as OpenTofu made them"
    )


class ExternalMedia(BaseModel):
    """Media on Azure Blob (`05_DEPLOYMENT.md` §3a); the account key arrives at apply as
    `AZURE_STORAGE_KEY`."""

    model_config = ConfigDict(extra="forbid")

    blob_account: str = Field(min_length=1, description="The Blob storage account")
    blob_container: str = Field(default="media", description="The container media is kept in")


class ExternalValkey(BaseModel):
    """A cloud's managed Valkey or Redis (`05_DEPLOYMENT.md` §3b: ElastiCache, Azure Cache for
    Redis); a cluster's replicas share it. Its password, if any, arrives as `VALKEY_PASSWORD`."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, description="The managed cache's address")
    port: int = Field(default=6379, description="Its port")
    tls: bool = Field(default=True, description="Whether it is reached over TLS")


class ExternalSearch(BaseModel):
    """A cloud's managed OpenSearch (`05_DEPLOYMENT.md` §3b: Amazon OpenSearch Service)."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, description="The domain's HTTPS address")


class ExternalConfig(BaseModel):
    """What a cloud runs for the deployment instead of a container (ADR-114 decision 8)."""

    model_config = ConfigDict(extra="forbid")

    postgres: ExternalPostgres | None = None
    object_store: ExternalObjectStore | None = None
    media: ExternalMedia | None = None
    valkey: ExternalValkey | None = None
    search: ExternalSearch | None = None

    @property
    def any(self) -> bool:
        return any((self.postgres, self.object_store, self.media, self.valkey, self.search))


class ResourcesConfig(BaseModel):
    """ADR-114 Amendment 33 decision 6: the stores sized to the server's memory. `memory_gib` is
    measured once, at install (`server.memory_gib: auto`), and written here, so the render reads a
    number and never the machine; resizing is an edit and `ospreyflow apply`. The three overrides
    win over the rule (`harness/profiles.py`). Unset, every store keeps today's values."""

    model_config = ConfigDict(extra="forbid")

    memory_gib: int | None = Field(
        default=None,
        ge=16,
        description="The memory the stores are sized to, in GiB (as Docker reports it). Default: "
        "none — the stores keep their fixed sizes.",
    )
    graph_heap_gib: int | None = Field(
        default=None, ge=1, le=31,
        description="Overrides the graph store's heap (-Xmx), in GiB; at most 31.",
    )  # fmt: skip
    search_heap_gib: float | None = Field(
        default=None, ge=0.5, le=31,
        description="Overrides OpenSearch's heap (-Xms and -Xmx), in GiB.",
    )  # fmt: skip
    postgres_shared_buffers_gib: float | None = Field(
        default=None, ge=0.125,
        description="Overrides PostgreSQL's shared_buffers, in GiB.",
    )  # fmt: skip
    #: ADR-135 Amendment 1: the local engine on the server's NVIDIA GPU. It sizes nothing, so it is
    #: not one of `any`'s settings, and Lite on a Linux computer may set it too.
    gpu: Literal["none", "nvidia"] = Field(
        default="none",
        description="Default: none — the local engine runs on the CPU. nvidia: the ollama service "
        "reserves every NVIDIA GPU, and the extraction model is qwen2.5:14b-instruct unless "
        "models.extraction names one. The NVIDIA driver and Container Toolkit are the "
        "administrator's to install.",
    )

    @property
    def any(self) -> bool:
        """Whether the stores are sized to the server (Small's alone); `gpu` is not part of it."""
        return any(
            value is not None
            for value in (self.memory_gib, self.graph_heap_gib, self.search_heap_gib,
                          self.postgres_shared_buffers_gib)
        )  # fmt: skip

    @model_validator(mode="after")
    def _the_stores_fit_the_server(self) -> ResourcesConfig:
        """An override may not hand the three stores more than three quarters of the server: the
        rest is Ollama's, Keycloak's, the Conduit's and the operating system's. Measured, the real
        PostgreSQL does not refuse shared buffers beyond its memory (it reserves them and is
        killed later), so the check is here. The rule's own values take at most half."""
        if self.memory_gib is None:
            return self
        graph = (
            self.graph_heap_gib
            if self.graph_heap_gib is not None
            else min(max(int(0.4 * self.memory_gib), 8), 31)
        )
        search = (
            self.search_heap_gib
            if self.search_heap_gib is not None
            else min(max(self.memory_gib / 16, 0.5), 8)
        )
        shared = (
            self.postgres_shared_buffers_gib
            if (self.postgres_shared_buffers_gib is not None)
            else min(max(self.memory_gib / 32, 0.25), 4)
        )
        total = graph + search + shared
        if total > 0.75 * self.memory_gib:
            raise ValueError(
                f"resources gives the graph store, OpenSearch and PostgreSQL {total:g} GiB "
                f"together, more than three quarters of resources.memory_gib ({self.memory_gib} "
                "GiB); lower the overrides, or give the server more memory"
            )
        return self


class OspreyConfig(BaseModel):
    """The whole of `osprey.yaml`.

    Validating the committed root file — which has only `map:` — must succeed, so every field here
    has a default. `map` is `None` rather than a stub when absent: a deployment with no basemap is
    a real state (nothing has been chosen on the Geospatial screen yet), and inventing an empty
    `MapConfig` would fail `MapConfig`'s own `min_length=1` for no reason."""

    model_config = ConfigDict(extra="forbid")

    profile: Profile = Field(
        default=Profile.LOCAL_LITE,
        description=(
            "Default: local-lite. Which kind of deployment: one machine (local-lite), a cloud "
            "server on managed services or a server of your own with every store in a container "
            "(small), or a cluster."
        ),
    )
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    cluster: ClusterConfig = Field(default_factory=ClusterConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    map: MapConfig | None = Field(default=None, description="Default: none declared")
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    mail: MailConfig | None = Field(default=None, description="Default: none — one-time codes")
    welcome: WelcomeConfig = Field(default_factory=WelcomeConfig)
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    appearance: AppearanceConfig = Field(default_factory=AppearanceConfig)
    external: ExternalConfig = Field(default_factory=ExternalConfig)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)

    @model_validator(mode="after")
    def _external_services_belong_to_a_cloud(self) -> OspreyConfig:
        if self.external.any and self.profile is Profile.LOCAL_LITE:
            raise ValueError(
                "external services are for the small and cluster profiles, which run on a "
                "cloud's managed services; local-lite runs its own"
            )
        return self

    @model_validator(mode="after")
    def _cluster_hosts_belong_to_the_cluster_profile(self) -> OspreyConfig:
        if self.cluster.declared and self.profile is not Profile.CLUSTER:
            raise ValueError(
                f"cluster settings are declared but profile is {self.profile.value!r}; they are "
                "only meaningful at profile: cluster"
            )
        if self.profile is Profile.CLUSTER:
            # ADR-054 Amendment 6: on a cluster these folders are on other machines, so there is
            # no product folder for a relative path to be read from.
            for name in ("ingest", "tiles"):
                value = getattr(self.components.storage, name)
                if not value.startswith("/"):
                    raise ValueError(
                        f"components.storage.{name} {value!r} must be an absolute path at "
                        "profile: cluster; a relative path is read from the product folder, which "
                        "only a single-machine deployment has"
                    )
        if self.profile is Profile.CLUSTER and not self.cluster.shared_storage_class:
            raise ValueError(
                "a cluster names cluster.shared_storage_class: the one volume every Conduit "
                "shares needs a class several pods can mount at once (EFS on AWS, Azure Files on "
                "Azure), which neither cloud has by default"
            )
        return self

    @model_validator(mode="after")
    def _a_cluster_runs_on_its_managed_services(self) -> OspreyConfig:
        """05 §3b: on Kubernetes the cloud runs PostgreSQL, Valkey and the object store, and a
        managed Valkey or search is for a cluster only (Small runs its own on the server)."""
        external = self.external
        if self.profile is Profile.CLUSTER:
            missing = [
                name
                for name, present in (
                    ("postgres", external.postgres),
                    ("valkey", external.valkey),
                    ("object_store (or media, on Azure)", external.object_store or external.media),
                )
                if present is None
            ]
            if missing:
                raise ValueError(
                    "a cluster runs on its cloud's managed services; external names no "
                    + ", ".join(missing)
                )
        elif external.valkey is not None or external.search is not None:
            raise ValueError(
                "a managed Valkey or search is for profile: cluster; Small runs its own on the "
                "server"
            )
        return self

    @model_validator(mode="after")
    def _the_address_suits_the_profile(self) -> OspreyConfig:
        """S11 and O2 (GDS re-audit; the owner's ruling of 2 November 2026; `05_DEPLOYMENT.md`
        §7). Small and Enterprise are reached by other people over a network, so their address is
        HTTPS. Lite answers on this computer only, in plain HTTP (S10), so a gov.uk address, which
        the public reaches, is never Lite. Refused in words, so `ospreyflow apply` and the guided
        page say why and what to write instead."""
        origin = self.network.public_origin
        if self.profile is not Profile.LOCAL_LITE and not origin.startswith("https://"):
            name = "a Small" if self.profile is Profile.SMALL else "an Enterprise"
            raise ValueError(
                f"network.public_origin {origin!r} is plain HTTP: {name} deployment's "
                "network.public_origin must be an https:// address (for example "
                "https://osprey.example.org), because other people reach it over a network and the "
                "front proxy obtains its certificate. Plain HTTP is for Lite, on this computer only"
            )
        host = (urlsplit(origin).hostname or "").rstrip(".").lower()
        if self.profile is Profile.LOCAL_LITE and (host == "gov.uk" or host.endswith(".gov.uk")):
            raise ValueError(
                f"network.public_origin {origin!r} is a gov.uk address, and Lite answers on this "
                "computer only, in plain HTTP. A gov.uk service is reached by the public over "
                "HTTPS: install it as Small or Enterprise (profile: small or cluster) with an "
                "https:// address, or give Lite a localhost address such as "
                "http://ospreyflow.localhost"
            )
        return self

    @model_validator(mode="after")
    def _a_certificate_of_its_own_is_for_a_small_on_its_own_server(self) -> OspreyConfig:
        """ADR-114 Amendment 33 decisions 1–3: the organisation's own certificate, the redirect
        from port 80 and the one listening address belong to a Small on a server of your own —
        every store in a container — and are refused anywhere else, in words."""
        network = self.network
        given = [
            name
            for name, present in (
                ("network.tls", network.tls is not None),
                ("network.redirect_http", network.redirect_http),
                ("network.listen_address", network.listen_address is not None),
            )
            if present
        ]
        if not given:
            return self
        if self.profile is not Profile.SMALL:
            raise ValueError(
                f"{', '.join(given)} is for Small on a server of your own (profile: small), not "
                f"profile: {self.profile.value}"
            )
        if self.external.any:
            raise ValueError(
                f"{', '.join(given)} is for Small on a server of your own, with every store in a "
                "container; this one names managed services under external:"
            )
        if network.tls is None:
            raise ValueError(
                f"{', '.join(given)} goes with network.tls (the organisation's own certificate); "
                "without it the front proxy obtains its own certificate, which needs port 80 on "
                "every interface"
            )
        if network.listen_address is not None:
            import ipaddress

            try:
                ipaddress.ip_address(network.listen_address)
            except ValueError:
                raise ValueError(
                    f"network.listen_address {network.listen_address!r} is not an IP address of "
                    "the server (for example 192.0.2.10)"
                ) from None
        return self

    @model_validator(mode="after")
    def _the_organisations_provider_and_memory_belong_to_a_small(self) -> OspreyConfig:
        """ADR-114 Amendment 33 decisions 4 and 6: the organisation's identity provider and the
        stores sized to the server are Small's; each is refused on Lite and Enterprise in words."""
        _check_organisation_provider(self)
        if self.resources.any and not self_contained_small(self):
            where = (
                "a Small on managed services, whose cloud sizes them"
                if self.profile is Profile.SMALL
                else f"profile: {self.profile.value}"
            )
            raise ValueError(
                "resources (the stores sized to the server's memory) is for Small on a server of "
                f"your own, every store in a container, not {where}"
            )
        return self

    @model_validator(mode="after")
    def _a_gpu_is_not_a_clouds(self) -> OspreyConfig:
        """ADR-135 Amendment 1 decision 1: the local engine on an NVIDIA GPU is for Lite on a Linux
        computer or Small on a server of your own. A cloud's servers are sized without a GPU
        (ADR-114), so it is refused there in words. macOS and Windows, whose Docker Desktop gives a
        container no NVIDIA GPU, are refused by the doctor, which reads the machine."""
        if self.resources.gpu == "nvidia" and (
            self.profile is Profile.CLUSTER or self.external.any
        ):
            where = (
                "Enterprise" if self.profile is Profile.CLUSTER else "a Small on managed services"
            )
            raise ValueError(
                "resources.gpu: nvidia is for Lite on a Linux computer or Small on a server of "
                f"your own, not {where}: a cloud's servers are sized without a GPU"
            )
        return self

    @property
    def extraction_model(self) -> str:
        """ADR-135 Amendment 1 decision 3: the extraction model the deployment runs. Named in
        `models.extraction`, that one always; else `qwen2.5:14b-instruct` on an NVIDIA GPU and the
        shipped `qwen2.5:7b-instruct` without one. "Named" is the key being in the file
        (`model_fields_set`), not its value, so a GPU deployment that names the 7b keeps it. The
        render, the pull and `start --build` read this, never `models.extraction` itself."""
        if "extraction" in self.models.model_fields_set or self.resources.gpu != "nvidia":
            return self.models.extraction
        return GPU_EXTRACTION_MODEL


#: A Keycloak identity-provider alias is part of the redirect URI the organisation registers
#: (`/realms/osprey/broker/<alias>/endpoint`), so it is kept plain.
_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _check_organisation_provider(config: OspreyConfig) -> None:
    """ADR-114 Amendment 33 decision 4: the organisation's identity provider belongs to a Small (it
    is refused on Lite and Enterprise, in words), and goes with the alias the welcome page's
    *Continue with organisation sign-in* names."""
    governance = config.governance
    if governance.organisation_provider is None:
        return
    if config.profile is not Profile.SMALL:
        raise ValueError(
            "governance.organisation_provider is for Small (profile: small), on a server of your "
            f"own, not profile: {config.profile.value}"
        )
    alias = governance.organisation_sign_in
    if not alias:
        raise ValueError(
            "governance.organisation_provider goes with governance.organisation_sign_in, the "
            "alias the welcome page's organisation sign-in names (for example: org)"
        )
    if not _ALIAS.match(alias):
        raise ValueError(
            f"governance.organisation_sign_in {alias!r} is part of the address the organisation "
            "registers, so it is letters, digits, '-' and '_' only (for example: org)"
        )


def self_contained_small(config: OspreyConfig) -> bool:
    """ADR-114 Amendment 33 decision 1: Small with every store in a container (no `external:`)."""
    return config.profile is Profile.SMALL and not config.external.any


#: Exported to `generate_ts.py`. `MapConfig` and its own members are already exported by
#: `schemas/mapconfig.py`'s own `ALL_MODELS` and are deliberately not repeated here — the generator
#: writes one file per model name, so listing a model twice writes it twice.
ALL_MODELS: tuple[type[BaseModel], ...] = (
    StorageRoots,
    ExternalPostgres,
    ExternalObjectStore,
    ExternalMedia,
    ExternalValkey,
    ExternalSearch,
    ExternalConfig,
    ComponentsConfig,
    ModelsConfig,
    OrganisationProvider,
    GovernanceConfig,
    ClusterHost,
    ClusterConfig,
    TlsFiles,
    NetworkConfig,
    ResourcesConfig,
    OspreyConfig,
)


def compose_project(config: OspreyConfig) -> str:
    """The deployment's Compose project, which prefixes its volumes (ADR-132 Amendment 1):
    `deployment.name`, else `osprey-<profile>` as every deployment was named before it."""
    return config.deployment.name or f"osprey-{config.profile.value}"


def generated_folder(config: OspreyConfig) -> str:
    """The folder under `deploy/generated/` the deployment is rendered to, `deployment.env` with
    it: `deployment.name`, else the profile, as before (ADR-132 Amendment 1)."""
    return config.deployment.name or config.profile.value
