// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: local-lite. Which kind of deployment: one machine (local-lite), a cloud server on managed services (small), or a cluster.
 */
export type Profile = "local-lite" | "small" | "cluster";
/**
 * Default: arcadedb. The graph store.
 */
export type GraphStore = "arcadedb" | "janusgraph";
/**
 * Default: duckdb. Where events are counted: DuckDB inside the Conduit, or ClickHouse shared by several.
 */
export type AnalyticsEngine = "duckdb" | "clickhouse";
/**
 * Default: opensearch. Search; postgres-fulltext is the lighter variant.
 */
export type SearchBackend = "opensearch" | "postgres-fulltext";
/**
 * Default: /var/lib/osprey/data. Where the deployment keeps its data inside the containers.
 */
export type Data = string;
/**
 * Default: /var/lib/osprey/staging. Where loads stage their rows before they reach the graph.
 */
export type Staging = string;
/**
 * Default: /var/lib/osprey/backups. Where backups are written.
 */
export type Backups = string;
/**
 * Default: /var/lib/osprey/ingest. The host folder of source files the Ingest Studio lists (read-only to it; uploads go to its uploaded/ folder).
 */
export type Ingest = string;
/**
 * Default: /var/lib/osprey/tiles. The host folder a built basemap lives in.
 */
export type Tiles = string;
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
 * LiteLLM's name for the provider: openai, anthropic, gemini, azure, bedrock…
 */
export type Name = string;
/**
 * The provider's address, where it is not LiteLLM's default (an Azure deployment, a proxy)
 */
export type ApiBase = string | null;
/**
 * ADR-095: the local model that extracts entities from text. Default: qwen2.5:7b-instruct, the model the product ships with.
 */
export type Extraction = "qwen2.5:7b-instruct" | "qwen2.5:14b-instruct";
/**
 * ADR-095: the local model that describes an image and reads its text.
 */
export type Vision = "moondream:1.8b-v2-q4_K_M";
/**
 * ADR-095: the local model that transcribes a video's speech.
 */
export type Transcription = "Systran/faster-whisper-tiny.en";
/**
 * ADR-095: the local model that turns text into vectors.
 */
export type Embedding = "all-minilm:22m-l6-v2-fp16";
/**
 * Default: keycloak. The identity provider people sign in through.
 */
export type IdentityProvider = string;
/**
 * Default: uk-law-enforcement. The handling scheme every item is marked under.
 */
export type HandlingScheme = string;
/**
 * Default: default. The ontology the deployment starts from.
 */
export type Ontology = string;
/**
 * The alias of an organisation's own identity provider brokered by Keycloak. When set, the welcome page offers *Continue with organisation sign-in*, which goes straight to it (ADR-115 decision 3). Default: none — one *Sign in* to the OspreyFlow form.
 */
export type OrganisationSignIn = string | null;
/**
 * The protective marking shown where no case data is on screen: the welcome page, Home, the Ingest Studio and the Admin area; inside a case, the strip shows this or the highest marking on screen, whichever is higher (ADR-115 decision 2). One of the handling scheme's classifications. Default: the scheme's lowest.
 */
export type Marking = string | null;
/**
 * Default: config/real_data_exceptions.yaml. A path to the gitignored list, never its contents.
 */
export type RealDataExceptions = string;
/**
 * The machine's name
 */
export type Name1 = string;
/**
 * Where the machine is reached
 */
export type Address = string;
/**
 * What runs on it
 */
export type Roles1 = string[];
export type Hosts = ClusterHost[];
/**
 * The Kubernetes namespace the deployment is installed in (05_DEPLOYMENT.md §3b)
 */
export type Namespace = string;
/**
 * The storage class each store's own volumes use; the cluster's default when unset
 */
export type StorageClass = string | null;
/**
 * Required for a cluster: the storage class of the one volume every Conduit shares (ReadWriteMany) — EFS on AWS, Azure Files on Azure
 */
export type SharedStorageClass = string | null;
/**
 * Default: false. Publish the Conduit's own port on the host in addition to the workspace's. Not needed to use the deployment — the workspace proxies /v1 — and turning it on widens the exposed surface by a whole tier. For an operator debugging the Conduit directly, or a second client that is not the Glass.
 */
export type ExposeConduit = boolean;
/**
 * Default: http://ospreyflow.localhost. The origin a browser uses to reach the Glass; the identity provider is `id.` and the dashboards `bi.` in front of the same host, with the same scheme and port, and the front proxy publishes that port (ADR-114 Amendment 4). `06_DECISIONS.md` ADR-050 objection 2's resolution: the identity-provider realm is rendered from this value at apply time and the Glass's public client is registered with an exact redirect URI and post-logout URI derived from it — no wildcards. Change this to move the deployment to another name or port; nothing else needs to agree with it.
 */
export type PublicOrigin = string;
/**
 * The provider the map opens on, by its id
 */
export type Default = string;
/**
 * Every basemap offered
 *
 * @minItems 1
 */
export type Providers = [MapProvider, ...MapProvider[]];
/**
 * The provider's own name, as map.default names it
 */
export type Id = string;
/**
 * What the Glass's map menu calls it
 */
export type Label = string;
/**
 * `00_ARCHITECTURE.md` §1.2: "Four source kinds cover the field."
 */
export type MapSourceKind = "vector" | "raster" | "image" | "dem";
/**
 * The licence's identifier, e.g. ODbL-1.0 or OGL-UK-3.0
 */
export type Id1 = string;
/**
 * Whether the tiles may be passed on to others
 */
export type Redistributable = boolean;
/**
 * Who the licence covers: anyone, this deployment, or each seat
 */
export type ClientScope = "open" | "per-deployment" | "per-seat";
/**
 * Anything the licence asks to be said
 */
export type Note = string | null;
/**
 * Where the tiles are: a file (file://…pmtiles) or a provider's address; one of source, service and endpoint, or profile
 */
export type Source = string | null;
/**
 * Tier 4 (ADR-016): the four generic OGC service types. `None` on a
 * provider means it is tiers 1-3 (a direct `source`), not tier 4.
 */
export type OgcServiceKind = "wmts" | "wms" | "wfs" | "ogc-features";
/**
 * An OGC service's base address (with service), never a tile URL
 */
export type Endpoint = string | null;
/**
 * The service's layer to show
 */
export type Layer = string | null;
/**
 * WMTS: the tile matrix set
 */
export type TileMatrixSet = string | null;
/**
 * WMTS: the tile image format
 */
export type Format = string | null;
/**
 * WMTS: the service's STYLE
 */
export type WmtsStyle = string | null;
/**
 * The lowest zoom the provider serves
 */
export type ZoomMin = number | null;
/**
 * The highest zoom the provider serves
 */
export type ZoomMax = number | null;
/**
 * A ready-made provider (providers/<profile>.yaml) to use
 */
export type Profile1 = string | null;
/**
 * The provider's key, as env:VARIABLE — a name, never the key itself
 */
export type Credential = string | null;
/**
 * Whether tiles are fetched through the Conduit (which caches them and keeps the key on the server) rather than by the browser
 */
export type Proxy = "required" | "recommended" | "none";
/**
 * How long a fetched tile is kept, in days
 */
export type TtlDays = number;
/**
 * Areas whose tiles are fetched ahead of use
 */
export type PrefetchAreas = string[];
/**
 * The map style: bundled:osprey-dark, bundled:osprey-light, or the profile's own
 */
export type Style = string | null;
/**
 * The credit shown on the map, as the licence asks
 */
export type Attribution = string;
/**
 * Default: false — run report-sync
 */
export type Sync = boolean;
/**
 * Default: 900. How often each case is pulled into the mart, in seconds.
 */
export type SyncIntervalSeconds = number;
/**
 * Default: 256m. Report sync's memory limit.
 */
export type SyncMemory = string;
/**
 * Default: false — run Superset
 */
export type Superset = boolean;
/**
 * Default: 2g. Superset's memory limit.
 */
export type SupersetMemory = string;
/**
 * The mail server's name
 */
export type Host = string;
/**
 * Default: 587. The mail server's port.
 */
export type Port = number;
/**
 * The address invitations come from
 */
export type FromAddress = string;
/**
 * Default: true. Whether mail is sent over TLS (STARTTLS).
 */
export type Starttls = boolean;
/**
 * Default: none — a relay that takes mail without signing in. With one, the password comes from OSPREY_SMTP_PASSWORD at install.
 */
export type Username = string | null;
/**
 * Default: on. Off for an internal-only deployment.
 */
export type About = boolean;
/**
 * Default: no link. Where people get help with their account.
 */
export type AccountHelp = string | null;
/**
 * Default: no link. The organisation's accessibility statement.
 */
export type Accessibility = string | null;
/**
 * Default: no link. The organisation's privacy notice.
 */
export type Privacy = string | null;
/**
 * Default: no link. A page saying whether the service is up.
 */
export type ServiceStatus = string | null;
/**
 * The managed server's address
 */
export type Host1 = string;
/**
 * Its port
 */
export type Port1 = number;
/**
 * The deployment's database on it
 */
export type Database = string;
/**
 * The login, which needs CREATEROLE and CREATEDB there
 */
export type User = string;
/**
 * Default: require. A managed server is reached over TLS.
 */
export type Sslmode = "require" | "verify-ca" | "verify-full";
/**
 * Host and port, no scheme: always HTTPS
 */
export type Endpoint1 = string;
/**
 * The region the buckets live in
 */
export type Region = string;
/**
 * Default: instance — the server's own cloud identity, no key anywhere; `keys` reads OSPREY_S3_ACCESS_KEY and OSPREY_S3_SECRET_KEY at apply.
 */
export type Credentials = "instance" | "keys";
/**
 * Each bucket is <prefix><name>, as OpenTofu made them
 */
export type BucketPrefix = string;
/**
 * The Blob storage account
 */
export type BlobAccount = string;
/**
 * The container media is kept in
 */
export type BlobContainer = string;
/**
 * The managed cache's address
 */
export type Host2 = string;
/**
 * Its port
 */
export type Port2 = number;
/**
 * Whether it is reached over TLS
 */
export type Tls = boolean;
/**
 * The domain's HTTPS address
 */
export type Url = string;

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
  reporting?: ReportingConfig;
  /**
   * Default: none — one-time codes
   */
  mail?: MailConfig | null;
  welcome?: WelcomeConfig;
  external?: ExternalConfig;
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
  tiles?: Tiles;
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
  provider?: ModelProviderConfig | null;
  extraction?: Extraction;
  vision?: Vision;
  transcription?: Transcription;
  embedding?: Embedding;
}
/**
 * A client's own model provider (ADR-114 decision 11, Amendment 6 point 4), reached through the
 * deployment's LiteLLM gateway. For each role it names, it **replaces** the local model — for
 * material whose handling code is in `models.sendable_handling_codes` only; anything else runs on
 * the local model. Its key is never here: it is `OSPREY_MODEL_PROVIDER_KEY` at install.
 */
export interface ModelProviderConfig {
  name: Name;
  roles: Roles;
  api_base?: ApiBase;
}
/**
 * The roles it takes, each with the provider's model for it
 */
export interface Roles {
  [k: string]: string;
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
  organisation_sign_in?: OrganisationSignIn;
  marking?: Marking;
  real_data_exceptions?: RealDataExceptions;
}
/**
 * Only meaningful at `profile: cluster`; declarable (and empty) at the other two so a profile
 * change does not need the file restructured.
 */
export interface ClusterConfig {
  hosts?: Hosts;
  namespace?: Namespace;
  storage_class?: StorageClass;
  shared_storage_class?: SharedStorageClass;
}
/**
 * One declared machine. `05_DEPLOYMENT.md` §2.1's Preflight screen runs "for `cluster`
 * connectivity to every declared host" against this list — Stage 2 §2's check, this schema's
 * declaration.
 */
export interface ClusterHost {
  name: Name1;
  address: Address;
  roles?: Roles1;
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
  /**
   * Keep fetched tiles a while
   */
  cache?: PrefetchCache | null;
  style?: Style;
  attribution: Attribution;
  [k: string]: unknown;
}
/**
 * The terms the tiles come under
 */
export interface ProviderLicence {
  id: Id1;
  redistributable: Redistributable;
  client_scope: ClientScope;
  note?: Note;
  [k: string]: unknown;
}
/**
 * Values the profile's addresses are filled with
 */
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
/**
 * Dashboards for the business (`06_DECISIONS.md` ADR-111 Amendment 2): the report sync service
 * and Superset, each a component of its own with its own memory, both off by default.
 */
export interface ReportingConfig {
  sync?: Sync;
  sync_interval_seconds?: SyncIntervalSeconds;
  sync_memory?: SyncMemory;
  superset?: Superset;
  superset_memory?: SupersetMemory;
}
/**
 * The mail server the identity provider sends invitations and sign-in resets through
 * (`06_DECISIONS.md` ADR-114 Amendment 5). Without one, people are signed in by a one-time code.
 * **No password here**: `osprey.yaml` never holds a secret (§2.5); the install reads it from
 * `OSPREY_SMTP_PASSWORD` and keeps it in the deployment's own `deployment.env`.
 */
export interface MailConfig {
  host: Host;
  port?: Port;
  from_address: FromAddress;
  starttls?: Starttls;
  username?: Username;
}
/**
 * The welcome page before sign-in (ADR-115 decision 8): its About section, and the footer's
 * links — the deploying organisation's own documents, each shown only when its address is
 * given.
 */
export interface WelcomeConfig {
  about?: About;
  account_help?: AccountHelp;
  accessibility?: Accessibility;
  privacy?: Privacy;
  service_status?: ServiceStatus;
}
/**
 * What a cloud runs for the deployment instead of a container (ADR-114 decision 8).
 */
export interface ExternalConfig {
  postgres?: ExternalPostgres | null;
  object_store?: ExternalObjectStore | null;
  media?: ExternalMedia | null;
  valkey?: ExternalValkey | null;
  search?: ExternalSearch | null;
}
/**
 * A cloud's managed PostgreSQL (`05_DEPLOYMENT.md` §3a). The password is never here: it arrives
 * at apply as `OSPREY_POSTGRES_PASSWORD`, from the cloud's secret store.
 */
export interface ExternalPostgres {
  host: Host1;
  port?: Port1;
  database?: Database;
  user?: User;
  sslmode?: Sslmode;
}
/**
 * A cloud's S3 (`05_DEPLOYMENT.md` §3a) for staging, site images, tiles, backups and media.
 */
export interface ExternalObjectStore {
  endpoint: Endpoint1;
  region: Region;
  credentials?: Credentials;
  bucket_prefix?: BucketPrefix;
}
/**
 * Media on Azure Blob (`05_DEPLOYMENT.md` §3a); the account key arrives at apply as
 * `AZURE_STORAGE_KEY`.
 */
export interface ExternalMedia {
  blob_account: BlobAccount;
  blob_container?: BlobContainer;
}
/**
 * A cloud's managed Valkey or Redis (`05_DEPLOYMENT.md` §3b: ElastiCache, Azure Cache for
 * Redis); a cluster's replicas share it. Its password, if any, arrives as `VALKEY_PASSWORD`.
 */
export interface ExternalValkey {
  host: Host2;
  port?: Port2;
  tls?: Tls;
}
/**
 * A cloud's managed OpenSearch (`05_DEPLOYMENT.md` §3b: Amazon OpenSearch Service).
 */
export interface ExternalSearch {
  url: Url;
}
