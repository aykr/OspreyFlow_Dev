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
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from schemas.domain import BUILT_IN_GRADING_SCHEMES, GradingSchemeAnswer
from schemas.mapconfig import MapConfig
from schemas.sources import (
    ATHENA_NAME,
    AWS_REGION,
    S3_BUCKET,
    S3_FOLDER,
    S3_LOCATION,
    SECRET_NAME,
    no_climbing,
    private_host_entry,
)

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
    #: ADR-148 decision 1: values for the chart into a namespace on a shared platform someone else
    #: runs, and that namespace's Terraform; no cluster, no VPC, none of the stores the platform
    #: manages.
    CLOUD_PLATFORM = "cloud-platform"


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
    code path: "If Preflight finds less than 16 GB it offers a reduced variant that drops OpenSearch
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


#: A JSON Web Token, the shape most gateways issue their tokens in: three base64url parts joined by
#: dots, the first two starting `eyJ` (`{"` encoded). Its dots hid it from the unbroken-run check
#: (the orchestrator's review of P11, round 2, item b).
#: Its header may carry `=` padding, and a JWE (encrypted, five parts) has a second part that is not
#: `eyJ`; a dot may arrive percent-encoded (`%2E`).
_DOT = r"=*(?:\.|%2[eE])"
_B64 = r"[A-Za-z0-9_\-]"
_JWT = re.compile(rf"eyJ{_B64}{{8,}}{_DOT}{_B64}{{8,}}=*(?:{_DOT}{_B64}*=*)+")


def _looks_like_a_key(text: str) -> bool:
    """A key's shape: a known key prefix, a JWT anywhere in it, or one unbroken run of 24 or more
    letters, digits, `-` and `_` mixing letters and digits. A reference in words
    (`DPA-2026-0001, signed 3 March`) has spaces or is short."""
    if any(word.startswith(_KEY_PREFIXES) for word in text.split()) or _JWT.search(text):
        return True
    return bool(
        re.fullmatch(r"[A-Za-z0-9_\-]{24,}", text)
        and re.search(r"[A-Za-z]", text)
        and re.search(r"[0-9]", text)
    )


#: ADR-135 Amendment 4: what an engine is. `provider`, a hosted provider LiteLLM knows by name (as
#: before); `gateway`, the client's own OpenAI-compatible AI gateway at its address; `bedrock`,
#: Amazon Bedrock in the client's London region.
EngineKind = Literal["provider", "gateway", "bedrock"]
#: How an engine signs in: `key`, a key (a gateway's token) entered write-only in *Admin › Models*
#: and kept by the model gateway alone; `iam_role`, an IAM role held by the gateway's pod through
#: its service account, so **no key is stored anywhere**. (The cloud-platform render gives the
#: gateway's pod its own account and role in P11 part 2; until then it has none.)
EngineAuth = Literal["key", "iam_role"]
#: ADR-135 Amendment 4 (b): Bedrock in the client's London region, and nowhere else.
BEDROCK_REGION = "eu-west-2"
#: ADR-135 Amendment 7 decision 1: Amendment 4's engine kinds and their rules are the
#: `cloud-platform` profile's (ADR-148) alone. On every other profile an engine is a provider by its
#: name and key, exactly as before Amendment 4 (an engine named `bedrock` included). Named by value:
#: the profile's own `Profile` member is P7's.
MODEL_ROUTE_PROFILE = "cloud-platform"
MODEL_ROUTE_PROFILES: frozenset[str] = frozenset({MODEL_ROUTE_PROFILE})
#: The validation context's key naming the profile whose engine rules a translated configuration
#: was already held to (`harness.cloud_platform._as_cluster`).
ENGINES_AS = "engines_as"
#: ADR-135 Amendment 7 decision 2: a Bedrock model is named by its own id (`anthropic.…`). An
#: inference profile's id puts a geography before it (`eu.`, `us.`, `apac.`, `global.`, …) and may
#: send the call outside London; AWS's own guide says not to rely on the prefix alone to tell where
#: it goes, so any id with a part before the provider's is refused, and so is an ARN.
_BEDROCK_MODEL_ID = re.compile(r"[a-z0-9-]+\.[^.\s:]+(:[^.\s]+)?")


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
    kind: EngineKind = Field(
        default="provider",
        description="ADR-135 Amendments 4 and 7: provider (a hosted provider LiteLLM knows by "
        "name), or at profile: cloud-platform only, gateway (the client's own OpenAI-compatible "
        "AI gateway, at api_base) or bedrock (Amazon Bedrock in London). Default: provider.",
    )
    auth: EngineAuth | None = Field(
        default=None,
        description="ADR-135 Amendments 4 and 7: key (entered in Admin › Models, kept by the "
        "model gateway alone), or at profile: cloud-platform only, iam_role (the gateway's own "
        "IAM role: no key is stored). Default: iam_role for bedrock, else key.",
    )
    region: str | None = Field(
        default=None,
        description="Bedrock's region (profile: cloud-platform): eu-west-2 (London) only, and "
        "the default for bedrock.",
    )

    @field_validator("name")
    @classmethod
    def _name_is_plain(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError(
                f"the provider name {value!r} is not one LiteLLM knows the shape of (lower-case, "
                "such as openai or anthropic)"
            )
        if value == LOCAL_ENGINE:
            raise ValueError(
                "local is this deployment's own engine; a provider outside it takes another name"
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

    @model_validator(mode="after")
    def _signs_in_as_its_kind_does(self) -> ModelProviderConfig:
        """ADR-135 Amendment 4's defaults, on any profile: Bedrock signs in by the gateway's own IAM
        role in London, any other kind by its key. **What each profile allows is not decided
        here** but by `engine_refusal`, which every reader of an engine calls with the
        deployment's profile (ADR-135 Amendment 7 decision 1)."""
        if self.auth is None:
            self.auth = "iam_role" if self.kind == "bedrock" else "key"
        if self.kind == "bedrock" and self.region is None:
            self.region = BEDROCK_REGION
        return self

    @property
    def plain(self) -> bool:
        """A provider by its key with no region: the only engine there was before Amendment 4, and
        the only one any profile but `cloud-platform` takes."""
        return self.kind == "provider" and self.auth == "key" and self.region is None

    @property
    def keyless(self) -> bool:
        """True where the engine signs in by the gateway's own IAM role: no key is stored for it."""
        return self.auth == "iam_role"

    def route(self, model: str) -> str:
        """LiteLLM's `model` for one of this engine's models: the client's gateway through the
        OpenAI-compatible route, Bedrock through its own, any other provider by its name."""
        prefix = {"gateway": "openai", "bedrock": "bedrock"}.get(self.kind, self.name)
        return f"{prefix}/{model}"


def engine_kinds_offered(profile: str) -> list[EngineKind]:
    """The kinds of engine *Admin › Models* offers on `profile` (ADR-135 Amendment 7 decision 1)."""
    if profile in MODEL_ROUTE_PROFILES:
        return ["provider", "gateway", "bedrock"]
    return ["provider"]


def _address_refusal(address: str) -> str | None:
    """ADR-135 Amendment 7 decision 3: an address is an address alone. A key pasted into it, before
    the host (`https://<key>@host`) or after it (`?api-key=<key>`, `#…`), would be kept in the
    models file, the gateway's entries and the audit, and shown in *Admin › Models*."""
    parts = urlsplit(address)
    if "@" in parts.netloc:
        return (
            "the address carries a name or key before its host (https://…@…); give the address "
            "alone, and the key or token with Enter key"
        )
    if parts.query or parts.fragment or "?" in address or "#" in address:
        return (
            "the address carries a query or fragment (?… or #…), where a key is often pasted; "
            "give the address alone, and the key or token with Enter key"
        )
    if any(_a_key_in_the_path(segment) for segment in parts.path.split("/")):
        return (
            "the address's path carries what looks like a key or token (https://…/<key>); give "
            "the address alone, and the key or token with Enter key"
        )
    return None


def _label_looks_like_a_key(text: str) -> bool:
    """A label or contract reference shaped like a key, or holding one among its words: each word
    checked as a whole one is (my own lane review of round 2, item 6; the reference too since P11
    part 2, on cloud-platform alone, by `engine_refusal`)."""
    return _looks_like_a_key(text) or any(
        _looks_like_a_key(word.strip(".,;:()'\"")) for word in text.split()
    )


def _a_key_in_the_path(segment: str) -> bool:
    """A path segment shaped like a key: a key prefix, a JWT, or 24 or more characters mixing upper
    case, lower case and digits. A deployment's name in a path (`my-deployment-2024-08-06`,
    `gpt-4o-mini-2024-07-18`) is lower case, so is taken (the orchestrator's round 2, item d)."""
    if segment.startswith(_KEY_PREFIXES) or _JWT.search(segment):
        return True
    # One unhyphenated run of 24 or more letters and digits in one case, mixing letters and digits
    # (a hex subscription key in either case, a base32 secret): a deployment's name is hyphenated
    # words (my own lane review of round 2, item 5; upper case since P11 part 2).
    if (
        re.fullmatch(r"[a-z0-9]{24,}|[A-Z0-9]{24,}", segment)
        and re.search(r"[A-Za-z]", segment)
        and re.search(r"[0-9]", segment)
    ):
        return True
    return bool(
        len(segment) >= 24
        and re.search(r"[A-Z]", segment)
        and re.search(r"[a-z]", segment)
        and re.search(r"[0-9]", segment)
    )


def engine_refusal(provider: ModelProviderConfig, profile: str) -> str | None:
    """What `profile` refuses in `provider`, in fixed words that name a field and never quote a
    value, or None (ADR-135 Amendment 7). Called by every reader of an engine with the deployment's
    profile: `OspreyConfig` (`osprey.yaml`), the Conduit's start (`Installed.from_env`), the models
    file (`ModelSettingsFile.load`) and each change in *Admin › Models* (`ModelAdmin._validated`).

    **Off `cloud-platform`**, an engine is a provider by its key, as before Amendment 4: an engine
    named `bedrock` is LiteLLM's Bedrock provider by its key there, as it always was (ADR-135
    decision 1). **On `cloud-platform`**, Amendment 4's rules: Bedrock by the gateway's own IAM role
    in London, by a model's own id; the client's gateway at its address alone, by a token; no
    engine named `bedrock` but Bedrock; no label shaped like a key."""
    if profile not in MODEL_ROUTE_PROFILES:
        if provider.plain:
            return None
        return (
            "your organisation's AI gateway, Amazon Bedrock in London and signing in by the "
            f"gateway's own IAM role are for profile: {MODEL_ROUTE_PROFILE} (ADR-135 Amendment 4); "
            "on this deployment an engine is a provider, reached by its name and its key"
        )
    if provider.contract_reference and _label_looks_like_a_key(provider.contract_reference):
        # Word by word on this profile alone (the orchestrator's ruling on P11 part 2, round 1):
        # every other profile reads a reference exactly as before Amendment 4.
        return (
            "the contract reference holds what looks like a key among its words; it is shown to "
            "analysts, so give the agreement's name or number in words, and the key or token with "
            "Enter key"
        )
    if provider.label and _label_looks_like_a_key(provider.label):
        return (
            "the label looks like a key; it is shown to analysts, so give the engine's name in "
            "words, and the key or token with Enter key"
        )
    if provider.api_base is not None and (refused := _address_refusal(provider.api_base)):
        return refused
    if provider.kind == "bedrock":
        if provider.auth != "iam_role":
            return (
                "Bedrock is reached by the gateway's own IAM role, so no key is kept for it; "
                "choose the IAM role"
            )
        if provider.api_base is not None:
            return (
                "Bedrock is reached at its own London address; an engine of this kind takes no "
                "address"
            )
        if provider.region != BEDROCK_REGION:
            return f"Bedrock is used in London only ({BEDROCK_REGION}); no other region is allowed"
        for role, model in provider.roles.items():
            if not _BEDROCK_MODEL_ID.fullmatch(model):
                return (
                    f"Bedrock is used in London only: the {role} model is not a model's own id "
                    "(such as anthropic.…). A cross-region inference profile's id (eu.…, us.…, "
                    "apac.…, global.…) or an ARN may send the call outside London"
                )
        return None
    if provider.name == "bedrock":
        # LiteLLM routes a provider by its name, so a `bedrock` provider would reach Bedrock by a
        # stored key and in no fixed region: on this profile Bedrock is reached only as its kind.
        return (
            "bedrock is reached only as Amazon Bedrock in London, by the gateway's own IAM role; "
            "choose that kind of engine"
        )
    if provider.region is not None:
        return "only a Bedrock engine takes a region"
    if provider.kind == "gateway" and provider.api_base is None:
        return "your organisation's AI gateway needs its address (https://…)"
    if provider.kind == "gateway" and provider.auth == "iam_role":
        # Held (platform-b server log, Q1): LiteLLM's OpenAI-compatible route sends no request
        # without a token, and how the client's gateway takes the namespace's identity is not yet
        # known. Refused rather than offered to analysts and failing every call.
        return (
            "your organisation's AI gateway signs in by a token for now: signing in by an IAM "
            "role waits for your gateway's owners to say how it accepts one"
        )
    if provider.kind == "provider" and provider.auth == "iam_role":
        return (
            "only Bedrock signs in by the gateway's own IAM role (your organisation's AI gateway, "
            "by a token for now); a provider signs in by its key"
        )
    return None


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
    #: ADR-135 Amendments 5 and 6 (P12 part 2): which engine runs `ModelPort.extract`. Deep read is
    #: the LiteLLM adapter; Laurium is its own service, rendered only when chosen, on
    #: `cloud-platform` alone (`OspreyConfig._extraction_engine_suits_the_profile`). Left unset,
    #: the profile's preset (Amendment 5 decision 2; Amendment 9): `laurium` on `cloud-platform`,
    #: `deep_read` on every other. Stored as written (unset stays unset, so a dump round-trips); the
    #: effective engine is read from `OspreyConfig.extraction_engine`.
    extraction_engine: Literal["deep_read", "laurium"] | None = Field(
        default=None,
        description="ADR-135 Amendments 5 and 6: deep_read or, at profile: cloud-platform only, "
        "laurium (its own service, every call through the gateway). Left unset: laurium on "
        "cloud-platform (its preset), deep_read on every other profile.",
    )

    @property
    def enabled_providers(self) -> list[ModelProviderConfig]:
        """ADR-135: every enabled provider — `providers`, or the single `provider` as a one-entry
        list."""
        return [self.provider] if self.provider is not None else list(self.providers)

    @property
    def keyed_providers(self) -> list[ModelProviderConfig]:
        """The enabled providers that sign in by a key: an engine signed in by the gateway's own IAM
        role (ADR-135 Amendment 4) has no key variable, is asked for no key and keeps none."""
        return [p for p in self.enabled_providers if not p.keyless]

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


_KUBE_NAME = r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$"

#: ADR-148 decision 7: the widest network an egress allowance may name, by IP version. **IPv4
#: /16** is the largest block AWS gives a VPC, so no one AWS service's network, and no platform's
#: shared VPC (the client's is a /16), is wider; **IPv6 /48** is one site's allocation (RFC 6177).
#: Anything wider, the default routes above all, opens the namespace's egress to far more than
#: one host, which one setting must never do.
EGRESS_WIDEST_PREFIX = {4: 16, 6: 48}


def too_wide_for_egress(net: str) -> str | None:
    """Why `net` may not be an egress allowance (a default route, or wider than
    `EGRESS_WIDEST_PREFIX`), or None. `net` must already be a network."""
    import ipaddress

    network = ipaddress.ip_network(net, strict=False)
    widest = EGRESS_WIDEST_PREFIX[network.version]
    if network.prefixlen == 0:
        return f"{net} is a default route: it would allow egress to every address"
    if network.prefixlen < widest:
        return (
            f"{net} is wider than /{widest}, the widest network egress may be allowed to "
            f"(IPv{network.version}); name the host's own, narrower networks"
        )
    return None


def s3_location(location: str) -> tuple[str, str]:
    """An `s3://` location's bucket and folder (the folder empty for the bucket's top)."""
    bucket, _, folder = location.removeprefix("s3://").partition("/")
    return bucket, folder


def standard_partition(region: str) -> str:
    """A declared source's region in AWS's standard partition: the role's statements are written for
    `arn:aws:`, so a China (`cn-`) or GovCloud (`-gov-`) region is refused in words, never rendered
    into ARNs that name another partition's resources wrongly."""
    if region.startswith("cn-") or "-gov-" in region:
        raise ValueError(
            f"{region} is outside AWS's standard partition: a declared source's region is a "
            "standard one (eu-west-2), since the role's statements name arn:aws: resources"
        )
    return region


class DeclaredS3Source(BaseModel):
    """A bucket an S3 connection may read, under a folder (ADR-140 Amendment 21): a connection on it
    names this region and a folder at or under this one."""

    model_config = ConfigDict(extra="forbid")

    bucket: str = Field(pattern=S3_BUCKET, description="The bucket's own name (no dot)")
    region: str = Field(pattern=AWS_REGION, description="The bucket's region (eu-west-2)")
    prefix: str = Field(
        default="",
        max_length=1024,
        pattern=S3_FOLDER,
        description="Default: the bucket's top. The folder a connection may read at or under, "
        "each name ending in / (exports/client-a/)",
    )

    @field_validator("prefix")
    @classmethod
    def _inside(cls, value: str) -> str:
        return no_climbing(value)

    @field_validator("region")
    @classmethod
    def _standard(cls, value: str) -> str:
        return standard_partition(value)

    def host(self) -> str:
        return f"{self.bucket}.s3.{self.region}.amazonaws.com"


class DeclaredAthenaSource(BaseModel):
    """An Athena workgroup an Athena connection may use (ADR-140 Amendment 21), with the databases
    it may read, where Athena writes its results, and where the tables' objects are (Athena reads
    them as the namespace's role, so the role is given read there; the Conduit never reaches
    them)."""

    model_config = ConfigDict(extra="forbid")

    workgroup: str = Field(pattern=ATHENA_NAME, description="The workgroup's name")
    region: str = Field(pattern=AWS_REGION, description="The workgroup's region (eu-west-2)")
    databases: list[Annotated[str, Field(pattern=r"^[a-z0-9_]{1,128}$")]] = Field(
        min_length=1, description="The Glue databases a connection may read"
    )
    results_location: str = Field(
        max_length=1024,
        pattern=S3_LOCATION,
        description="Where Athena writes each query's results (s3://bucket/folder/): the only "
        "place a declared source gives the role a write. A folder, never a bucket's top",
    )
    table_locations: list[Annotated[str, Field(max_length=1024, pattern=S3_LOCATION)]] = Field(
        description="Where the databases' tables keep their objects (s3://bucket/folder/), at "
        "least one, read by Athena as the namespace's role: read-only, and never reached by the "
        "Conduit",
    )

    @field_validator("results_location")
    @classmethod
    def _a_folder(cls, value: str) -> str:
        if not s3_location(value)[1]:
            raise ValueError(
                "results_location names a folder (s3://bucket/athena-results/), never a bucket's "
                "top: the role may write there alone"
            )
        no_climbing(s3_location(value)[1])
        return value

    @field_validator("table_locations")
    @classmethod
    def _tables_inside(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError(
                "table_locations names at least one s3://bucket/folder/: Athena reads a table's "
                "objects as the namespace's role, so with none the role could read no table"
            )
        for value in values:
            no_climbing(s3_location(value)[1])
        return values

    @field_validator("region")
    @classmethod
    def _standard(cls, value: str) -> str:
        return standard_partition(value)

    def host(self) -> str:
        return f"athena.{self.region}.amazonaws.com"


class ConnectorSources(BaseModel):
    """The cloud sources a cloud-platform deployment may read (ADR-140 Amendment 21)."""

    model_config = ConfigDict(extra="forbid")

    s3: list[DeclaredS3Source] = Field(default_factory=list, description="The S3 buckets")
    athena: list[DeclaredAthenaSource] = Field(
        default_factory=list, description="The Athena workgroups"
    )

    def declared(self) -> bool:
        return bool(self.s3 or self.athena)

    def hosts(self) -> list[str]:
        """Each declared source's one host, as a connection on it reaches it."""
        return sorted({s.host() for s in self.s3} | {a.host() for a in self.athena})


_ENTRA_ID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class EntraSignInConfig(BaseModel):
    """ADR-148 decision 9 and Amendment 8: how this deployment's people sign in with Entra ID, and
    where `principal_auth` finds each of clearance, unit and handling codes in their token (a claim,
    or a table from Entra group to value; `principal_auth.ClaimMapping` checks the shape at render).
    Roles are not here: they are kept in Admin › People, the first administrators named below."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(pattern=_ENTRA_ID, description="The client's Entra tenant id")
    client_id: str = Field(
        pattern=_ENTRA_ID, description="The Glass's own app registration (application id)"
    )
    api_client_id: str = Field(
        pattern=_ENTRA_ID,
        description="This API's app registration (application id): the token's audience",
    )
    api_id_uri: str | None = Field(
        default=None,
        pattern=r"^api://\S+$",
        description="Default: api://<api_client_id>. The API's application id URI, which the "
        "Glass's scope names",
    )
    token_version: Literal["2.0", "1.0"] = Field(
        default="2.0",
        description="Default: 2.0. The access token version the API's registration is issued "
        "(accessTokenAcceptedVersion): the issuer and audience the Conduit checks follow it",
    )
    scope: str = Field(
        default="access_as_user",
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Default: access_as_user. The delegated scope the Glass asks the API for",
    )
    clearance: dict[str, Any] = Field(
        description="Where clearance comes from: {claim: <name>} or {groups: {<group id>: <value>}}"
    )
    org_unit: dict[str, Any] = Field(
        description="Where the organisational unit comes from: {claim: ...} or {groups: {...}}"
    )
    handling_codes: dict[str, Any] = Field(
        description="Where the handling codes come from: {claim: ...} or {groups: {<id>: [codes]}}"
    )
    groups_claim: str = Field(
        default="groups",
        min_length=1,
        description="Default: groups. The token claim listing the person's Entra group ids, "
        "which a {groups: ...} table above is read from",
    )
    first_administrators: list[str] = Field(
        description="The people given the Admin role at install, by Entra object id (at least one)"
    )
    claims_mapping_policy: bool = Field(
        default=False,
        description="Default: false. Whether a claims-mapping policy signs the API's tokens with "
        "its own key (the keys are then read with ?appid=<api_client_id>)",
    )

    @field_validator("first_administrators")
    @classmethod
    def _someone(cls, oids: list[str]) -> list[str]:
        if not oids:
            raise ValueError(
                "names no first administrator: name at least one person by Entra object id "
                "(an empty list is never everyone)"
            )
        if bad := [o for o in oids if not re.match(_ENTRA_ID, o)]:
            raise ValueError(f"not an Entra object id (lower case): {bad[0]!r}")
        return list(dict.fromkeys(oids))

    @property
    def issuer(self) -> str:
        if self.token_version == "1.0":
            return f"https://sts.windows.net/{self.tenant_id}/"
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def id_uri(self) -> str:
        return self.api_id_uri or f"api://{self.api_client_id}"

    @property
    def audience(self) -> str:
        # Unmeasured: as Microsoft documents v1.0 and v2.0 tokens' `aud`; one real token from the
        # client's tenant settles it (ADR-148 Amendment 8; CARRIES).
        return self.id_uri if self.token_version == "1.0" else self.api_client_id

    @property
    def jwks_url(self) -> str:
        path = "discovery/keys" if self.token_version == "1.0" else "discovery/v2.0/keys"
        url = f"https://login.microsoftonline.com/{self.tenant_id}/{path}"
        return f"{url}?appid={self.api_client_id}" if self.claims_mapping_policy else url

    def claim_mapping(self) -> dict[str, Any]:
        """The `OSPREY_CLAIM_MAPPING` the Conduit reads (`principal_auth.ClaimMapping`)."""
        return {
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "api_client_id": self.api_client_id,
            "scope": self.scope,
            "clearance": self.clearance,
            "org_unit": self.org_unit,
            "handling_codes": self.handling_codes,
            "groups_claim": self.groups_claim,
        }


class CloudPlatformConfig(BaseModel):
    """ADR-148: only meaningful at `profile: cloud-platform`. What is this deployment's own (its
    namespace, its environment, its registry, who may reach it, where its enabled hosts are); what
    is the platform's (ingress class and annotations, storage class, egress policy kind, its
    secrets' names) is in the platform's settings file, `harness/cloud_platform/platforms/
    <platform>.yaml`, so another shared platform is a new file, not a new profile."""

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(
        default="client",
        pattern=r"^[a-z][a-z0-9-]*$",
        description="Default: client. The platform's settings file, by name",
    )
    namespace: str | None = Field(
        default=None,
        pattern=_KUBE_NAME,
        description="The namespace the platform's team created for the deployment (required)",
    )
    environment: Literal["development", "production"] = Field(
        default="development",
        description="Default: development — one copy of each store; production runs the "
        "cluster's copies (ArcadeDB 3, ClickHouse 2, Keeper 3)",
    )
    shape: Literal["standard", "poc"] = Field(
        default="standard",
        description="Default: standard — the stores as the environment sets them. poc: the "
        "proof-of-concept shape (ADR-148 Amendment 5), a development namespace's only: one "
        "ArcadeDB and one ClickHouse running its own Keeper, no disruption budgets, and the "
        "Ingest root on a claim of its own",
    )
    registry: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)*$",
        description="Where every image is pulled from (required): the namespace's ECR, as "
        "`ospreyflow images push --registry` copied them there",
    )
    allow_from: list[str] = Field(
        default_factory=list,
        description="The networks (CIDR) the platform's ingress admits; empty: every address",
    )
    egress_nets: dict[str, list[str]] = Field(
        default_factory=dict,
        description="For each host the namespace reaches (a model provider, a proxied map "
        "provider, the mail server, a connector host, S3 and STS "
        "unless the platform's settings name theirs), the networks (CIDR) its traffic is allowed "
        "to; a host with none is refused at render. No network wider than /16 (IPv4) or /48 "
        "(IPv6), and never a default route",
    )
    tls_secret: str | None = Field(
        default=None,
        pattern=_KUBE_NAME,
        description="Default: none — the platform's own certificate. The Kubernetes Secret "
        "holding the certificate for the deployment's name (the Glass's: the profile renders no "
        "sign-in or reporting name), where the platform's wildcard does not cover it",
    )
    claims: EntraSignInConfig | None = Field(
        default=None,
        description="How people sign in, with Entra ID (required at render): the tenant, the "
        "Glass's and the API's app registrations, where each claim comes from and the first "
        "administrators",
    )
    connector_hosts: list[str] = Field(
        default_factory=list,
        description="The hosts a SQL or API connection may reach, each as host or host:port (a "
        "name, not an IPv6 literal), with its networks in egress_nets under the host alone. The "
        "namespace's egress allows each host on its ports; the Conduit's own allow-list "
        "(OSPREY_CONNECTOR_EGRESS) holds the hosts alone, so a connection to a listed host on a "
        "port not listed here passes the Conduit and times out at the egress. A bare host is "
        "reached on 443 (an API connection over HTTPS); a SQL connection needs its database's port "
        "here (db.example.org:5432). A host given twice with two ports is reached on both",
    )

    connector_sources: ConnectorSources = Field(
        default_factory=lambda: ConnectorSources(),
        description="The S3 buckets and Athena workgroups an S3 or Athena connection may read "
        "(ADR-140 Amendment 21). Each becomes the Conduit's own egress row on 443 and an entry on "
        "its allow-list, and the namespace's IAM role gains read-only statements scoped to it. "
        "Admin › Connections refuses an S3 or Athena connection not declared here; declare it, "
        "re-render and run helm upgrade (and apply the Terraform)",
    )

    @field_validator("connector_hosts")
    @classmethod
    def _connector_ports(cls, hosts: list[str]) -> list[str]:
        for entry in hosts:
            connector_address(entry)  # refused in words when its port is not a port
        return hosts

    @model_validator(mode="after")
    def _networks_are_networks(self) -> CloudPlatformConfig:
        import ipaddress

        for net in [*self.allow_from, *(n for nets in self.egress_nets.values() for n in nets)]:
            try:
                ipaddress.ip_network(net)
            except ValueError:
                raise ValueError(f"{net!r} is not a network (for example 192.0.2.0/24)") from None
        if self.shape == "poc" and self.environment != "development":
            raise ValueError(
                "cloud_platform.shape: poc is a development namespace's (one copy of each store); "
                "a production namespace takes the standard shape"
            )
        # ADR-148 decision 7: one setting must never open the namespace's egress.
        for host, nets in self.egress_nets.items():
            for net in nets:
                if why := too_wide_for_egress(net):
                    raise ValueError(f"cloud_platform.egress_nets[{host!r}]: {why}")
        return self


def connector_address(entry: str) -> tuple[str, int]:
    """A `cloud_platform.connector_hosts` entry's host and port: `host:port`, or a bare host on 443
    (ADR-148 Amendment 5 point 21). The port is digits alone, 1 to 65535."""
    if entry.startswith("[") or entry.count(":") > 1:
        raise ValueError(
            f"cloud_platform.connector_hosts {entry!r}: an IPv6 address is not taken; name the "
            "host by its name (db.example.org or db.example.org:5432)"
        )
    host, sep, port = entry.rpartition(":")
    if not sep:
        return entry, 443
    if not host or not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
        raise ValueError(
            f"cloud_platform.connector_hosts {entry!r}: a host, or host:port with a port from 1 "
            "to 65535 in digits alone (db.example.org:5432)"
        )
    return host, int(port)


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
    access_key: bool = Field(
        default=False,
        # Left out of every dump while false, so a deployment that does not ask renders byte for
        # byte what it did (the cluster's and the cloud platform's values carry `osprey.yaml`).
        exclude_if=lambda asks: asks is False,
        description=(
            "Small over https:// only: the front proxy asks every browser for a shared key (the "
            "browser's own user name and key box) on all three names before anything loads, and "
            "every answer says noindex. The key's bcrypt hash is set on the server by "
            "`python -m harness.access_key set <the deployment's folder>`, never here. Default: "
            "false (ADR-114 Amendment 41)."
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


class ConnectorsConfig(BaseModel):
    """The Studio's SQL and API connectors (`06_DECISIONS.md` ADR-140 Amendments 13 and 15). A
    connector never reaches inside the deployment or its network unless the operator admits a
    client's private database or API here; the installer's setting, never Admin's."""

    model_config = ConfigDict(extra="forbid")

    private_hosts: list[str] = Field(
        default_factory=list,
        description=(
            "Default: none. The private hosts a SQL or API connection may reach: each a host name "
            "in full (nomis-replica.client.internal) or a network inside 10.0.0.0/8, "
            "172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10 or fc00::/7 (10.20.0.0/16) that a "
            "connection's host name resolves into. Everything else inside a network stays "
            "refused. Never admitted, whatever is listed: this machine, a cloud's metadata "
            "services (169.254.0.0/16, fd00:ec2::/32, 100.100.0.0/16), Docker's and the "
            "cluster's own names, and any address in the Conduit's own networks or the "
            "deployment's own services'. A host must still be on the egress allow-list."
        ),
    )

    secrets: list[str] = Field(
        default_factory=list,
        description=(
            "Default: none. The name of each SQL or API connection's secret "
            "(NOMIS_REPLICA for OSPREY_CONNECTION_SECRET_NOMIS_REPLICA in deployment.env). Only "
            "the Conduit is given a declared secret, every other service having it blanked, and a "
            "connection whose secret is not declared reads nothing."
        ),
    )

    @field_validator("secrets")
    @classmethod
    def _each_a_secret_name(cls, value: list[str]) -> list[str]:
        for name in value:
            if not re.fullmatch(SECRET_NAME, name):
                raise ValueError(
                    f"{name!r} is not a secret's name: capitals, digits and _ only, starting "
                    "with a capital (NOMIS_REPLICA)"
                )
        return value

    @field_validator("private_hosts")
    @classmethod
    def _each_private(cls, value: list[str]) -> list[str]:
        for entry in value:
            private_host_entry(entry)
        return [e.strip() for e in value]


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

    #: ADR-148 decision 10: the highest marking this deployment may hold. Checked against the
    #: handling scheme the Conduit loads at render (`harness.site.highest_marking`, which holds
    #: each profile's own default, `PROFILE_CEILINGS`).
    highest_marking: str | None = Field(
        default=None,
        description=(
            "Default: OFFICIAL-SENSITIVE on the cloud-platform profile, else the handling "
            "scheme's highest. The highest marking this deployment may hold: "
            "a load or an import marked above it is refused before anything is written, in words "
            "that say this limit and never the item's content. A demo pack that declares no "
            "highest marking is judged as the scheme's highest, so under a lower setting it is "
            "refused. One of the handling scheme's classifications. Left unset, it is the "
            "scheme's highest, or OFFICIAL-SENSITIVE on the cloud-platform profile."
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
    banner_text: str | None = Field(
        default=None,
        description=(
            'Default: none. The banner\'s own words, in place of "This is a new service.", in '
            "the Glass and on the sign-in page: after the phase's tag at alpha or beta, alone at "
            "live or none. One line of at most 200 characters (ADR-132 Amendment 7)."
        ),
    )

    @field_validator("banner_text")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        one_line = "\n" not in value and "\r" not in value if value is not None else True
        if value is not None and (not value.strip() or len(value) > 200 or not one_line):
            raise ValueError("appearance.banner_text must be one line of at most 200 characters")
        return value

    def told(self) -> dict[str, object]:
        """The section as the Glass and the sign-in page are told it: `banner_text` only when set,
        so a deployment that names none renders byte for byte what it did (Amendment 7)."""
        dumped = self.model_dump()
        if self.banner_text is None:
            del dumped["banner_text"]
        return dumped


class GradingConfig(BaseModel):
    """The deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11 and Amendment 6): the
    scheme every drawn node and link is graded in, chosen at install (`install.yaml`'s
    `grading.scheme`) and shown read-only in Admin. Changed only by `ospreyflow grading change`
    (C13), which changes the items and this setting together: editing this alone would leave the
    items' grades in the old scheme."""

    model_config = ConfigDict(extra="forbid")

    scheme: str = Field(
        default="5x5x5",
        min_length=1,
        description=(
            "Default: 5x5x5. The scheme drawn items are graded in: 5x5x5; 3x5x2, whose handling "
            "code (P or C) is part of the grade and never merged with the marking; or the path of "
            "a scheme file (.yaml, beside this file unless absolute) naming its own scheme and "
            "each part's grades."
        ),
    )

    #: A scheme file's scheme, read by `harness.render.load_config` (beside `osprey.yaml`).
    _file_scheme: GradingSchemeAnswer | None = PrivateAttr(default=None)

    @property
    def names_a_file(self) -> bool:
        return self.scheme not in BUILT_IN_GRADING_SCHEMES

    def read_file(self, beside: Path) -> None:
        """Reads the scheme file `scheme` names, relative to `beside` unless absolute, and checks
        it (`GradingSchemeAnswer`). Refused, naming the file, if it cannot be read or is not one."""
        if not self.names_a_file:
            return
        path = Path(self.scheme)
        path = path if path.is_absolute() else beside / path
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as unread:
            raise ValueError(
                f"grading.scheme: the scheme file {path} cannot be read: {unread}"
            ) from None
        try:
            self._file_scheme = GradingSchemeAnswer.model_validate(raw)
        except ValidationError as bad:
            raise ValueError(f"grading.scheme: {path} is not a grading scheme: {bad}") from None

    def resolved(self) -> GradingSchemeAnswer:
        """The scheme and its grades: a built-in one's, or the scheme file's once read."""
        if not self.names_a_file:
            return GradingSchemeAnswer.of(self.scheme)
        if self._file_scheme is None:
            raise ValueError(f"grading.scheme: the scheme file {self.scheme} has not been read")
        return self._file_scheme

    @field_validator("scheme")
    @classmethod
    def _a_scheme_or_its_file(cls, value: str) -> str:
        if value in BUILT_IN_GRADING_SCHEMES or value.endswith((".yaml", ".yml")):
            return value
        raise ValueError(
            f"{value!r} is neither a grading scheme ({', '.join(BUILT_IN_GRADING_SCHEMES)}) nor a "
            "scheme file (.yaml)"
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
    cloud_platform: CloudPlatformConfig | None = Field(
        default=None, description="Default: none — only at profile: cloud-platform (ADR-148)"
    )
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    map: MapConfig | None = Field(default=None, description="Default: none declared")
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    connectors: ConnectorsConfig = Field(default_factory=ConnectorsConfig)
    mail: MailConfig | None = Field(default=None, description="Default: none — one-time codes")
    welcome: WelcomeConfig = Field(default_factory=WelcomeConfig)
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    appearance: AppearanceConfig = Field(default_factory=AppearanceConfig)
    grading: GradingConfig = Field(default_factory=GradingConfig)
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
    def _a_cloud_platform_names_its_namespace_and_registry(self) -> OspreyConfig:
        """ADR-148: the platform's settings belong to that profile alone; the platform's own
        managed stores replace every one of ours, so `external:` names none (their details are
        read from the platform's secrets, never written here)."""
        given = self.cloud_platform
        if self.profile is not Profile.CLOUD_PLATFORM:
            if given is not None:
                raise ValueError(
                    "cloud_platform settings are declared but profile is "
                    f"{self.profile.value!r}; they are only meaningful at profile: cloud-platform"
                )
            return self
        missing = [
            name
            for name in ("namespace", "registry")
            if given is None or getattr(given, name) is None
        ]
        if missing:
            raise ValueError(
                "a cloud-platform deployment names "
                + " and ".join(f"cloud_platform.{name}" for name in missing)
                + ": the platform's team creates the namespace and its registry"
            )
        if self.external.any:
            raise ValueError(
                "on a cloud platform its managed stores replace ours and their details come from "
                "the platform's secrets; external: names none"
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
    def _engines_suit_the_profile(self, info: ValidationInfo) -> OspreyConfig:
        """ADR-135 Amendment 7 decision 1: each engine as this profile allows (`engine_refusal`).
        A cloud-platform deployment's cluster translation (`harness.cloud_platform._as_cluster`) is
        validated as `profile: cluster`; its engines were already held to cloud-platform's rules,
        and it says so by `ENGINES_AS` in the validation's context, so the render does not refuse
        the engines it is rendering (the orchestrator's round 2, item a)."""
        # Honoured only as `_as_cluster` uses it: cloud-platform's rules, for a cluster translation
        # (my own lane review of round 2, note 11). Any other use is the profile's own rules.
        engines_as = (info.context or {}).get(ENGINES_AS)
        translated = engines_as == MODEL_ROUTE_PROFILE and self.profile is Profile.CLUSTER
        profile = MODEL_ROUTE_PROFILE if translated else self.profile.value
        for provider in self.models.enabled_providers:
            if refused := engine_refusal(provider, profile):
                raise ValueError(f"models.providers: {provider.name}: {refused}")
        return self

    #: Set while validating a cloud-platform deployment's cluster translation (`ENGINES_AS`), so the
    #: translation reads cloud-platform's preset.
    _engines_as_cloud_platform: bool = PrivateAttr(default=False)

    @property
    def extraction_engine(self) -> Literal["deep_read", "laurium"]:
        """The engine `ModelPort.extract` runs on: as named, or the profile's preset (ADR-135
        Amendment 5 decision 2, the owner's; Amendment 9): `laurium` on `cloud-platform` (and its
        cluster translation), `deep_read` on every other profile."""
        named = self.models.extraction_engine
        if named is not None:
            return named
        cloud = self.profile is Profile.CLOUD_PLATFORM or self._engines_as_cloud_platform
        return "laurium" if cloud else "deep_read"

    @model_validator(mode="after")
    def _extraction_engine_suits_the_profile(self, info: ValidationInfo) -> OspreyConfig:
        """ADR-135 Amendments 5 and 6 (P12 part 2; the orchestrator's ruling of 11 November):
        Laurium on `cloud-platform` alone, as the engine kinds are (`_engines_suit_the_profile`),
        its cluster translation carried by `ENGINES_AS` alike."""
        engines_as = (info.context or {}).get(ENGINES_AS)
        translated = engines_as == MODEL_ROUTE_PROFILE and self.profile is Profile.CLUSTER
        profile = MODEL_ROUTE_PROFILE if translated else self.profile.value
        # Read, never written (the lane-reviewer's item 3): the preset is resolved by the
        # `extraction_engine` property, so a dump of this configuration names only what was named.
        self._engines_as_cloud_platform = translated
        if self.models.extraction_engine == "laurium" and profile not in MODEL_ROUTE_PROFILES:
            raise ValueError(
                f"models.extraction_engine: laurium is for profile: {MODEL_ROUTE_PROFILE} "
                f"(ADR-135 Amendment 6); this deployment is profile: {profile}. Name deep_read, "
                "or leave it out."
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
            name = {
                Profile.SMALL: "a Small",
                Profile.CLOUD_PLATFORM: "a cloud platform",
            }.get(self.profile, "an Enterprise")
            front = (
                "the platform's ingress serves its certificate"
                if self.profile is Profile.CLOUD_PLATFORM
                else "the front proxy obtains its certificate"
            )
            raise ValueError(
                f"network.public_origin {origin!r} is plain HTTP: {name} deployment's "
                "network.public_origin must be an https:// address (for example "
                "https://osprey.example.org), because other people reach it over a network and "
                f"{front}. Plain HTTP is for Lite, on this computer only"
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
    def _the_shared_key_is_for_a_small_over_tls(self) -> OspreyConfig:
        """ADR-114 Amendment 41: the shared key is asked by the Small's own front proxy. Only over
        TLS, since a browser sends it again with every request: a Small's address is always an
        https:// one (`_the_address_suits_the_profile`), and nothing else may ask."""
        if self.network.access_key and self.profile is not Profile.SMALL:
            raise ValueError(
                "network.access_key is for Small, whose front proxy asks for it (profile: small), "
                f"not profile: {self.profile.value}"
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
            self.profile in (Profile.CLUSTER, Profile.CLOUD_PLATFORM) or self.external.any
        ):
            where = (
                "Enterprise"
                if self.profile is Profile.CLUSTER
                else "a cloud platform (ADR-148 decision 11)"
                if self.profile is Profile.CLOUD_PLATFORM
                else "a Small on managed services"
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
    GradingConfig,
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
