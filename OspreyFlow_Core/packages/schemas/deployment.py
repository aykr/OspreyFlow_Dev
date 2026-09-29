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

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.mapconfig import MapConfig

#: `05_DEPLOYMENT.md` §3's own default published workspace port
#: (`harness/render.py`'s `PORT_OVERRIDES["workspace"]`), restated here rather than imported —
#: this schema has no dependency on the harness, and the harness depends on it, not the reverse.
DEFAULT_PUBLIC_ORIGIN = "http://localhost:8080"


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

    @model_validator(mode="after")
    def _hosted_fallback_and_local_only_are_consistent(self) -> ModelsConfig:
        if self.local_only and self.hosted_fallback is not None:
            raise ValueError(
                "models.local_only is true but a hosted_fallback is named; set local_only: false "
                "to declare the egress exception explicitly rather than by implication"
            )
        if self.sendable_handling_codes and self.hosted_fallback is None:
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
            "Default: http://localhost:8080 — the workspace's own default published port "
            "(`OSPREY_WORKSPACE_PORT`). The origin a browser uses to reach this deployment. "
            "`06_DECISIONS.md` ADR-050 objection 2's resolution: the identity-provider realm is "
            "rendered from this value at apply time and the Glass's public client is registered "
            "with an exact redirect URI and post-logout URI derived from it — no wildcards. "
            "Override this when `OSPREY_WORKSPACE_PORT` is overridden or the deployment is reached "
            "at a different host; the renderer does not infer either from the environment."
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
