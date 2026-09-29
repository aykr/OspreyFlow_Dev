// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: local-lite
 */
export type Profile = "local-lite" | "small" | "cluster";
/**
 * Default: arcadedb
 */
export type GraphStore = "arcadedb" | "janusgraph";
/**
 * Default: duckdb
 */
export type AnalyticsEngine = "duckdb" | "clickhouse";
/**
 * Default: opensearch. postgres-fulltext is §3's reduced variant.
 */
export type SearchBackend = "opensearch" | "postgres-fulltext";
/**
 * Default: /var/lib/osprey/data
 */
export type Data = string;
/**
 * Default: /var/lib/osprey/staging
 */
export type Staging = string;
/**
 * Default: /var/lib/osprey/backups
 */
export type Backups = string;
/**
 * Default: /var/lib/osprey/ingest
 */
export type Ingest = string;
/**
 * Default: none — the owned services (workspace, api, ingest) are PULLED, by the digest recorded in versions.lock, from the registry reference harness/render.py's own service_images names. This is the operator path: the harness image itself carries no services/ or apps/workspace source, and round 05's own finding was that the documented one-command bootstrap could not Launch without it — a clean laptop has no checkout. Set to a checkout root containing services/api/Dockerfile, services/ingest/Dockerfile and apps/workspace/Dockerfile (this repository's own root, for a developer/CI run) to BUILD owned images from source instead. Declared and the Dockerfiles absent is refused by name (harness.render.MissingDockerfileError) — never silently treated as the pull path.
 */
export type SourcePath = string | null;
/**
 * Default: true — no hosted fallback
 */
export type LocalOnly = boolean;
/**
 * Default: none. A provider name, never a credential.
 */
export type HostedFallback = string | null;
/**
 * Default: empty. Which handling codes may leave for a hosted model.
 */
export type SendableHandlingCodes = string[];
/**
 * Default: keycloak (03_CONDUIT_MIDDLEWARE.md §6)
 */
export type IdentityProvider = string;
/**
 * Default: uk-law-enforcement
 */
export type HandlingScheme = string;
/**
 * Default: default
 */
export type Ontology = string;
/**
 * Default: config/real_data_exceptions.yaml. A path to the gitignored list, never its contents.
 */
export type RealDataExceptions = string;
export type Name = string;
export type Address = string;
export type Roles = string[];
export type Hosts = ClusterHost[];
/**
 * Default: false. Publish the Conduit's own port on the host in addition to the workspace's. Not needed to use the deployment — the workspace proxies /v1 — and turning it on widens the exposed surface by a whole tier. For an operator debugging the Conduit directly, or a second client that is not the Glass.
 */
export type ExposeConduit = boolean;
/**
 * Default: http://localhost:8080 — the workspace's own default published port (`OSPREY_WORKSPACE_PORT`). The origin a browser uses to reach this deployment. `06_DECISIONS.md` ADR-050 objection 2's resolution: the identity-provider realm is rendered from this value at apply time and the Glass's public client is registered with an exact redirect URI and post-logout URI derived from it — no wildcards. Override this when `OSPREY_WORKSPACE_PORT` is overridden or the deployment is reached at a different host; the renderer does not infer either from the environment.
 */
export type PublicOrigin = string;
export type Default = string;
/**
 * @minItems 1
 */
export type Providers = [MapProvider, ...MapProvider[]];
export type Id = string;
export type Label = string;
/**
 * `00_ARCHITECTURE.md` §1.2: "Four source kinds cover the field."
 */
export type MapSourceKind = "vector" | "raster" | "image" | "dem";
export type Id1 = string;
export type Redistributable = boolean;
/**
 * `00_ARCHITECTURE.md` §1.2: "`client_scope` is a required field on
 * every provider" — the three values named there exactly.
 */
export type ClientScope = "open" | "per-deployment" | "per-seat";
export type Note = string | null;
export type Source = string | null;
/**
 * Tier 4 (ADR-016): the four generic OGC service types. `None` on a
 * provider means it is tiers 1-3 (a direct `source`), not tier 4.
 */
export type OgcServiceKind = "wmts" | "wms" | "wfs" | "ogc-features";
export type Endpoint = string | null;
export type Layer = string | null;
export type TileMatrixSet = string | null;
export type Format = string | null;
export type WmtsStyle = string | null;
export type ZoomMin = number | null;
export type ZoomMax = number | null;
export type Profile1 = string | null;
export type Credential = string | null;
export type Proxy = "required" | "recommended" | "none";
export type TtlDays = number;
export type PrefetchAreas = string[];
export type Style = string | null;
export type Attribution = string;

/**
 * The whole of `osprey.yaml`.
 *
 * Validating the committed root file — which has only `map:` — must succeed, so every field here
 * has a default. `map` is `None` rather than a stub when absent: a deployment with no basemap is
 * a real state (nothing has been chosen on the Geospatial screen yet), and inventing an empty
 * `MapConfig` would fail `MapConfig`'s own `min_length=1` for no reason.
 */
export interface OspreyConfig {
  profile?: Profile;
  components?: ComponentsConfig;
  models?: ModelsConfig;
  governance?: GovernanceConfig;
  cluster?: ClusterConfig;
  network?: NetworkConfig;
  /**
   * Default: none declared
   */
  map?: MapConfig | null;
}
/**
 * `05_DEPLOYMENT.md` §2.1's Components screen. Defaults are the `local-lite` row of §1's own
 * profile table, because that is the profile this repository is demonstrable on today.
 */
export interface ComponentsConfig {
  graph_store?: GraphStore;
  analytics_engine?: AnalyticsEngine;
  search?: SearchBackend;
  storage?: StorageRoots;
  source_path?: SourcePath;
}
/**
 * `05_DEPLOYMENT.md` §2.1's Components screen: "the storage roots for data, staging and
 * backups", plus `ingest` (owner ruling R6, 27 September 2026). Paths on the deployment host,
 * not in this repository.
 */
export interface StorageRoots {
  data?: Data;
  staging?: Staging;
  backups?: Backups;
  ingest?: Ingest;
}
/**
 * `05_DEPLOYMENT.md` §2.1's Models screen: "Local only, or local with a named hosted fallback
 * — and if hosted, which handling codes may be sent to it. **Defaults to none**."
 *
 * The default here is that sentence, enforced rather than described: no hosted fallback, and an
 * empty set of sendable handling codes. `04_VAULT_BACKEND.md` §4's egress exception is off unless
 * something turns it on.
 */
export interface ModelsConfig {
  local_only?: LocalOnly;
  hosted_fallback?: HostedFallback;
  sendable_handling_codes?: SendableHandlingCodes;
}
/**
 * `05_DEPLOYMENT.md` §2.1's Governance screen: "Identity provider, handling scheme, ontology.
 * Ships with a UK law-enforcement scheme, a US criminal-intelligence scheme, and the default
 * ontology."
 *
 * `real_data_exceptions` is the **reference** ADR-049's Stage 2 §6 puts on the Governance panel —
 * a path to the local, never-committed exceptions list, not its contents. The list itself is
 * gitignored (`config/real_data_exceptions.yaml`, standing rule 3 / `CLAUDE.md` rule 9 /
 * ADR-035 §C3) and must stay that way: this field records where to look, exactly as §2.5 requires
 * of every credential, and for the same reason.
 */
export interface GovernanceConfig {
  identity_provider?: IdentityProvider;
  handling_scheme?: HandlingScheme;
  ontology?: Ontology;
  real_data_exceptions?: RealDataExceptions;
}
/**
 * Only meaningful at `profile: cluster`; declarable (and empty) at the other two so a profile
 * change does not need the file restructured.
 */
export interface ClusterConfig {
  hosts?: Hosts;
}
/**
 * One declared machine. `05_DEPLOYMENT.md` §2.1's Preflight screen runs "for `cluster`
 * connectivity to every declared host" against this list — Stage 2 §2's check, this schema's
 * declaration.
 */
export interface ClusterHost {
  name: Name;
  address: Address;
  roles?: Roles;
}
/**
 * What this deployment publishes to its host.
 *
 * `05_DEPLOYMENT.md` §7: "Every service on an internal network. Only the workspace and the
 * Conduit are exposed, behind a reverse proxy terminating TLS." Since the owner's decision of
 * 25 September 2026 (§2.6 item 1) **the workspace's own image is that reverse proxy** — its nginx
 * proxies `/v1` and the delta WebSocket to the Conduit on the internal network — so the normal
 * deployment publishes one port, not two, and the Conduit is reachable without being exposed.
 */
export interface NetworkConfig {
  expose_conduit?: ExposeConduit;
  public_origin?: PublicOrigin;
}
/**
 * `osprey.yaml`'s `map:` section.
 */
export interface MapConfig {
  default: Default;
  providers: Providers;
  [k: string]: unknown;
}
export interface MapProvider {
  id: Id;
  label: Label;
  kind: MapSourceKind;
  licence: ProviderLicence;
  source?: Source;
  service?: OgcServiceKind | null;
  endpoint?: Endpoint;
  layer?: Layer;
  tile_matrix_set?: TileMatrixSet;
  format?: Format;
  wmts_style?: WmtsStyle;
  zoom_min?: ZoomMin;
  zoom_max?: ZoomMax;
  profile?: Profile1;
  variables?: Variables;
  credential?: Credential;
  proxy?: Proxy;
  cache?: PrefetchCache | null;
  style?: Style;
  attribution: Attribution;
  [k: string]: unknown;
}
export interface ProviderLicence {
  id: Id1;
  redistributable: Redistributable;
  client_scope: ClientScope;
  note?: Note;
  [k: string]: unknown;
}
export interface Variables {
  [k: string]: string;
}
/**
 * Tier 3 only (`05_DEPLOYMENT.md` §2.2's "Prefetch area of
 * operations") — absent for tiers 1/2/4, which either need no cache
 * (local files) or aren't proxied through it the same way.
 */
export interface PrefetchCache {
  ttl_days: TtlDays;
  prefetch_areas?: PrefetchAreas;
  [k: string]: unknown;
}
