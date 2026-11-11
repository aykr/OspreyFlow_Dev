// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: local-lite. Which kind of deployment: one machine (local-lite), a cloud server on managed services or a server of your own with every store in a container (small), or a cluster.
 */
export type Profile = "local-lite" | "small" | "cluster" | "cloud-platform";
/**
 * Default: arcadedb. The graph store.
 */
export type GraphStore = "arcadedb" | "janusgraph";
/**
 * Default: duckdb. Where events are counted: DuckDB inside the Conduit, or ClickHouse shared by several.
 */
export type AnalyticsEngine = "duckdb" | "clickhouse";
/**
 * Default: true. Whether a load queues entity resolution afterwards (`OSPREY_POST_INGEST_RESOLUTION`). False for a demonstration whose people must not gain automatic `SAME_AS` links; an analyst's own Resolve now still works.
 */
export type PostIngestResolution = boolean;
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
 * Default: /var/lib/osprey/ingest. The host folder of source files the Ingest Studio lists (read-only to it; uploads go to its uploaded/ folder). A relative path is read from the folder osprey.yaml is in.
 */
export type Ingest = string;
/**
 * Default: /var/lib/osprey/tiles. The host folder a built basemap lives in. A relative path is read from the folder osprey.yaml is in.
 */
export type Tiles = string;
/**
 * Default: none — the owned services (workspace, api, ingest) are PULLED, by the digest recorded in versions.lock, from the registry reference harness/render.py's own service_images names. This is the operator path: the harness image itself carries no services/ or apps/workspace source, and a review found that the documented one-command bootstrap could not Launch without it — a clean laptop has no checkout. Set to a checkout root containing services/api/Dockerfile, services/ingest/Dockerfile and apps/workspace/Dockerfile (this repository's own root, for a developer/CI run) to BUILD owned images from source instead. Declared and the Dockerfiles absent is refused by name (harness.render.MissingDockerfileError) — never silently treated as the pull path.
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
 * ADR-135: the name analysts see for this engine. Default: OpenAI, Anthropic or Gemini for those three, else the provider's name capitalised.
 */
export type Label = string | null;
/**
 * The provider's address, where it is not LiteLLM's default (an Azure deployment, a proxy)
 */
export type ApiBase = string | null;
/**
 * ADR-136: true when the deployment's organisation holds a data-processing agreement with the provider covering this key. A dataset whose egress is `contracted` is sent only to a provider marked so. Default: false.
 */
export type PrivacyContract = boolean;
/**
 * ADR-136: the agreement's reference, in words (for example DPA 2026/07); never a secret. Shown beside the mark.
 */
export type ContractReference = string | null;
/**
 * ADR-135 Amendments 4 and 7: provider (a hosted provider LiteLLM knows by name), or at profile: cloud-platform only, gateway (the client's own OpenAI-compatible AI gateway, at api_base) or bedrock (Amazon Bedrock in London). Default: provider.
 */
export type Kind = "provider" | "gateway" | "bedrock";
/**
 * ADR-135 Amendments 4 and 7: key (entered in Admin › Models, kept by the model gateway alone), or at profile: cloud-platform only, iam_role (the gateway's own IAM role: no key is stored). Default: iam_role for bedrock, else key.
 */
export type Auth = ("key" | "iam_role") | null;
/**
 * Bedrock's region (profile: cloud-platform): eu-west-2 (London) only, and the default for bedrock.
 */
export type Region = string | null;
/**
 * ADR-135: the providers an administrator enables; each key is OSPREY_MODEL_KEY_<NAME>, entered at install or with `ospreyflow models key`.
 */
export type Providers = ModelProviderConfig[];
/**
 * ADR-095: the local model that extracts entities from text. Default: qwen2.5:7b-instruct, the model the product ships with; with resources.gpu: nvidia and this not named, qwen2.5:14b-instruct (ADR-135 Amendment 1).
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
 * The alias of an organisation's own identity provider brokered by Keycloak. When set, the welcome page offers *Continue with organisation sign-in* (*Continue with <label>* when `organisation_provider` names one), which goes straight to it (ADR-115 decision 3, Amendment 5). Default: none — one *Sign in* to the OspreyFlow form.
 */
export type OrganisationSignIn = string | null;
/**
 * The provider's name as people know it, shown on the welcome page's button (Continue with <label>) and on the identity provider's own sign-in pages (for example 'Example Department account').
 */
export type Label1 = string;
/**
 * The provider's issuer, an https:// address; its discovery document is read from <issuer>/.well-known/openid-configuration (for Entra ID, https://login.microsoftonline.com/<tenant>/v2.0).
 */
export type Issuer = string;
/**
 * The application (client) id the organisation registered for OspreyFlow.
 */
export type ClientId = string;
/**
 * ADR-114 Amendment 33, 'Step 33': true joins a person arriving through the organisation to the OspreyFlow account holding the same email address, automatically, with its roles and clearance. Off by default: a person whose email an account holds is refused in words, and an administrator joins them in Admin, People and roles. Turn it on only with the organisation's security officer's written sign-off that every address its provider gives is verified and cannot be set by the person who holds it: anyone who can make the provider give an address takes over the account that holds it (the 2023 'nOAuth' account takeovers).
 */
export type TrustEmail = boolean;
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
 * Default: client. The platform's settings file, by name
 */
export type Platform = string;
/**
 * The namespace the platform's team created for the deployment (required)
 */
export type Namespace1 = string | null;
/**
 * Default: development — one copy of each store; production runs the cluster's copies (ArcadeDB 3, ClickHouse 2, Keeper 3)
 */
export type Environment = "development" | "production";
/**
 * Where every image is pulled from (required): the namespace's ECR, as `ospreyflow images push --registry` copied them there
 */
export type Registry = string | null;
/**
 * The networks (CIDR) the platform's ingress admits; empty: every address
 */
export type AllowFrom = string[];
/**
 * Default: none — the platform's own certificate. The Kubernetes Secret holding the certificate for the deployment's names (its id. and bi. names among them), where the platform's wildcard does not cover them
 */
export type TlsSecret = string | null;
/**
 * The hosts a SQL or API connection may reach, each with its networks in egress_nets: rendered as both the namespace's egress and the Conduit's own allow-list (OSPREY_CONNECTOR_EGRESS), so the two never disagree
 */
export type ConnectorHosts = string[];
/**
 * Default: false. Publish the Conduit's own port on the host in addition to the workspace's. Not needed to use the deployment — the workspace proxies /v1 — and turning it on widens the exposed surface by a whole tier. For an operator debugging the Conduit directly, or a second client that is not the Glass.
 */
export type ExposeConduit = boolean;
/**
 * Default: http://ospreyflow.localhost. The origin a browser uses to reach the Glass; the identity provider is `id.` and the dashboards `bi.` in front of the same host, with the same scheme and port, and the front proxy publishes that port (ADR-114 Amendment 4). `06_DECISIONS.md` ADR-050 objection 2's resolution: the identity-provider realm is rendered from this value at apply time and the Glass's public client is registered with an exact redirect URI and post-logout URI derived from it — no wildcards. Change this to move the deployment to another name or port; nothing else needs to agree with it.
 */
export type PublicOrigin = string;
/**
 * The server certificate, then its intermediates, in PEM: an absolute path.
 */
export type Certificate = string;
/**
 * The certificate's private key in PEM, unencrypted: an absolute path. Owned by the installing account, mode 600; the front proxy runs as that account to read it.
 */
export type Key = string;
/**
 * Optional: the organisation's root certificate (PEM), an absolute path. With it, the certificate's chain is checked to reach it, and the host's own tools trust it.
 */
export type Ca = string | null;
/**
 * Small on a server of your own, with network.tls only: also publish port 80, and only to send people to the https:// address. Default: false — port 443 alone.
 */
export type RedirectHttp = boolean;
/**
 * Small on a server of your own, with network.tls only: the one address of the server the front proxy publishes on. Default: none — every interface.
 */
export type ListenAddress = string | null;
/**
 * The provider the map opens on, by its id
 */
export type Default = string;
/**
 * Every basemap offered
 *
 * @minItems 1
 */
export type Providers1 = [MapProvider, ...MapProvider[]];
/**
 * The provider's own name, as map.default names it
 */
export type Id = string;
/**
 * What the Glass's map menu calls it
 */
export type Label2 = string;
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
 * WMTS: the query parameter the provider's key goes in
 */
export type CredentialParam = string | null;
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
 * Default: only_me. Whom a new hotlist's alerts reach: its owner alone (only_me), or also the owner's team, the people of the owner's organisational unit (team). Applies to hotlists made after it is set, never to an existing one.
 */
export type HotlistAudience = "only_me" | "team";
/**
 * Default: true. Whether a hotlist's owner may choose its audience, when making it or later. When false, every new hotlist takes hotlist_audience and a change is refused.
 */
export type HotlistAudienceEditable = boolean;
/**
 * Default: none. The private hosts a SQL or API connection may reach: each a host name in full (nomis-replica.client.internal) or a network inside 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10 or fc00::/7 (10.20.0.0/16) that a connection's host name resolves into. Everything else inside a network stays refused. Never admitted, whatever is listed: this machine, a cloud's metadata services (169.254.0.0/16, fd00:ec2::/32, 100.100.0.0/16), Docker's and the cluster's own names, and any address in the Conduit's own networks or the deployment's own services'. A host must still be on the egress allow-list.
 */
export type PrivateHosts = string[];
/**
 * Default: none. The name of each SQL or API connection's secret (NOMIS_REPLICA for OSPREY_CONNECTION_SECRET_NOMIS_REPLICA in deployment.env). Only the Conduit is given a declared secret, every other service having it blanked, and a connection whose secret is not declared reads nothing.
 */
export type Secrets = string[];
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
 * Default: osprey-<profile>, rendered to deploy/generated/<profile>/. Names this deployment's Compose project, its volumes and its rendered folder, so a second deployment on the same machine shares none of them.
 */
export type Name2 = string | null;
/**
 * Default: 2480. The port on this machine (127.0.0.1 only) the graph store's own tools reach it at. A deployment installed beside another with ospreyflow install --name is given one of its own, so the two share no port.
 */
export type GraphPort = number | null;
/**
 * Default: the handling scheme's highest. The highest marking this deployment may hold: a load or an import marked above it is refused before anything is written, in words that say this limit and never the item's content. A demo pack that declares no highest marking is judged as the scheme's highest, so under a lower setting it is refused. One of the handling scheme's classifications.
 */
export type HighestMarking = string | null;
/**
 * Default: ospreyflow. The GOV.UK look, for a service on a gov.uk domain only.
 */
export type Brand = "ospreyflow" | "govuk";
/**
 * Default: none. The service's name, in the page title.
 */
export type ServiceName = string | null;
/**
 * Default: none. The organisation in the GOV.UK footer and the page title.
 */
export type Organisation = string | null;
/**
 * Default: none. The phase banner shows at alpha or beta.
 */
export type Phase = "alpha" | "beta" | "live" | "none";
/**
 * Default: 5x5x5. The scheme drawn items are graded in: 5x5x5; 3x5x2, whose handling code (P or C) is part of the grade and never merged with the marking; or the path of a scheme file (.yaml, beside this file unless absolute) naming its own scheme and each part's grades.
 */
export type Scheme = string;
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
export type Region1 = string;
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
 * The memory the stores are sized to, in GiB (as Docker reports it). Default: none — the stores keep their fixed sizes.
 */
export type MemoryGib = number | null;
/**
 * Overrides the graph store's heap (-Xmx), in GiB; at most 31.
 */
export type GraphHeapGib = number | null;
/**
 * Overrides OpenSearch's heap (-Xms and -Xmx), in GiB.
 */
export type SearchHeapGib = number | null;
/**
 * Overrides PostgreSQL's shared_buffers, in GiB.
 */
export type PostgresSharedBuffersGib = number | null;
/**
 * Default: none — the local engine runs on the CPU. nvidia: the ollama service reserves every NVIDIA GPU, and the extraction model is qwen2.5:14b-instruct unless models.extraction names one. The NVIDIA driver and Container Toolkit are the administrator's to install.
 */
export type Gpu = "none" | "nvidia";

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
  /**
   * Default: none — only at profile: cloud-platform (ADR-148)
   */
  cloud_platform?: CloudPlatformConfig | null;
  network?: NetworkConfig;
  /**
   * Default: none declared
   */
  map?: MapConfig | null;
  reporting?: ReportingConfig;
  monitoring?: MonitoringConfig;
  connectors?: ConnectorsConfig;
  /**
   * Default: none — one-time codes
   */
  mail?: MailConfig | null;
  welcome?: WelcomeConfig;
  deployment?: DeploymentConfig;
  appearance?: AppearanceConfig;
  grading?: GradingConfig;
  external?: ExternalConfig;
  resources?: ResourcesConfig;
}
/**
 * `05_DEPLOYMENT.md` §2.1's Components screen. Defaults are the `local-lite` row of §1's own
 * profile table, because that is the profile this repository is demonstrable on today.
 */
export interface ComponentsConfig {
  graph_store?: GraphStore;
  analytics_engine?: AnalyticsEngine;
  post_ingest_resolution?: PostIngestResolution;
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
  /**
   * ADR-114 Amendment 6: one provider, read as a one-entry `providers` whose roles default to it; its key is OSPREY_MODEL_PROVIDER_KEY. Not with `providers`.
   */
  provider?: ModelProviderConfig | null;
  providers?: Providers;
  defaults?: Defaults;
  extraction?: Extraction;
  vision?: Vision;
  transcription?: Transcription;
  embedding?: Embedding;
}
/**
 * A client's own model provider (ADR-114 decision 11, Amendment 6 point 4; ADR-135), reached
 * through the deployment's LiteLLM gateway, for material whose handling code is in
 * `models.sendable_handling_codes` only; anything else runs on the local model. Its key is never
 * here: it is `OSPREY_MODEL_KEY_<NAME>` at install (`OSPREY_MODEL_PROVIDER_KEY` for the single
 * `models.provider`), kept in the deployment's `deployment.env` and read by the gateway alone.
 */
export interface ModelProviderConfig {
  name: Name;
  label?: Label;
  roles: Roles;
  api_base?: ApiBase;
  privacy_contract?: PrivacyContract;
  contract_reference?: ContractReference;
  kind?: Kind;
  auth?: Auth;
  region?: Region;
}
/**
 * The roles it takes, each with the provider's model for it
 */
export interface Roles {
  [k: string]: string;
}
/**
 * ADR-135: each role's default engine, `local` or an enabled provider's name. A role not named runs on `local` (for the single `provider`, on it).
 */
export interface Defaults {
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
  /**
   * Small on a server of your own only (ADR-114 Amendment 33 decision 4): the organisation's identity provider that `organisation_sign_in` names, which `ospreyflow install` and `ospreyflow repair-sign-in` register in Keycloak. Default: none — people sign in with accounts an administrator makes.
   */
  organisation_provider?: OrganisationProvider | null;
  marking?: Marking;
  real_data_exceptions?: RealDataExceptions;
}
/**
 * ADR-114 Amendment 33 decision 4: the organisation's own identity provider (OpenID Connect —
 * Entra ID, ADFS, an internal Keycloak), brokered by the deployment's Keycloak. Names and
 * addresses only: the client secret is `OSPREY_ORG_SIGN_IN_SECRET` in the installer's
 * environment, kept in `deployment.env` and set through Keycloak's admin API, never here
 * (`05_DEPLOYMENT.md` §2.5). A person arriving through it gets no role and no clearance until an
 * administrator grants them (the owner's answer 6: no group-to-role mapping).
 */
export interface OrganisationProvider {
  label: Label1;
  issuer: Issuer;
  client_id: ClientId;
  trust_email?: TrustEmail;
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
 * ADR-148: only meaningful at `profile: cloud-platform`. What is this deployment's own (its
 * namespace, its environment, its registry, who may reach it, where its enabled hosts are); what
 * is the platform's (ingress class and annotations, storage class, egress policy kind, its
 * secrets' names) is in the platform's settings file, `harness/cloud_platform/platforms/
 * <platform>.yaml`, so another shared platform is a new file, not a new profile.
 */
export interface CloudPlatformConfig {
  platform?: Platform;
  namespace?: Namespace1;
  environment?: Environment;
  registry?: Registry;
  allow_from?: AllowFrom;
  egress_nets?: EgressNets;
  tls_secret?: TlsSecret;
  connector_hosts?: ConnectorHosts;
}
/**
 * For each host the namespace reaches (a model provider, a proxied map provider, the mail server, a connector host, S3 and STS unless the platform's settings name theirs), the networks (CIDR) its traffic is allowed to; a host with none is refused at render. No network wider than /16 (IPv4) or /48 (IPv6), and never a default route
 */
export interface EgressNets {
  [k: string]: string[];
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
  /**
   * Small on a server of your own only (ADR-114 Amendment 33): the organisation's own certificate and key, served by the front proxy with no certificate management and no call out. Default: none — Small's front proxy obtains a certificate itself, which needs a public name and the internet.
   */
  tls?: TlsFiles | null;
  redirect_http?: RedirectHttp;
  listen_address?: ListenAddress;
}
/**
 * ADR-114 Amendment 33 decision 3: the organisation's own certificate for a Small on a server
 * of its own. Paths on the server, absolute; the front proxy mounts the two files read-only and
 * the key is never copied (not into the deployment folder, not into a backup). Checked before
 * anything starts by `harness/tls_check.py`.
 */
export interface TlsFiles {
  certificate: Certificate;
  key: Key;
  ca?: Ca;
}
/**
 * `osprey.yaml`'s `map:` section.
 */
export interface MapConfig {
  default: Default;
  providers: Providers1;
  [k: string]: unknown;
}
export interface MapProvider {
  id: Id;
  label: Label2;
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
  credential_param?: CredentialParam;
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
 * Monitoring and alerts (`06_DECISIONS.md` ADR-133 ruling 3): whom a new hotlist's alerts reach
 * in the shared alert queue, and whether its owner may change that. A hotlist made before the
 * setting existed keeps `only_me` whatever is set here.
 */
export interface MonitoringConfig {
  hotlist_audience?: HotlistAudience;
  hotlist_audience_editable?: HotlistAudienceEditable;
}
/**
 * The Studio's SQL and API connectors (`06_DECISIONS.md` ADR-140 Amendments 13 and 15). A
 * connector never reaches inside the deployment or its network unless the operator admits a
 * client's private database or API here; the installer's setting, never Admin's.
 */
export interface ConnectorsConfig {
  private_hosts?: PrivateHosts;
  secrets?: Secrets;
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
 * Which deployment this is, on a machine that may run more than one (ADR-132 Amendment 1).
 */
export interface DeploymentConfig {
  name?: Name2;
  graph_port?: GraphPort;
  highest_marking?: HighestMarking;
}
/**
 * How every page of the deployment looks (ADR-132): the deployment's brand, which is not the
 * viewer's light or dark choice. `govuk` is the GOV.UK look the Service Manual requires on a
 * `*.service.gov.uk` service: its header and footer, GDS Transport, its colours and the light
 * page. The network's own colours and shapes are the same under either brand. Read by the Glass
 * from `/deployment.json`; the Admin console's Appearance tab is to write the same section.
 */
export interface AppearanceConfig {
  brand?: Brand;
  service_name?: ServiceName;
  organisation?: Organisation;
  phase?: Phase;
}
/**
 * The deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11 and Amendment 6): the
 * scheme every drawn node and link is graded in, chosen at install (`install.yaml`'s
 * `grading.scheme`) and shown read-only in Admin. Changed only by `ospreyflow grading change`
 * (C13), which changes the items and this setting together: editing this alone would leave the
 * items' grades in the old scheme.
 */
export interface GradingConfig {
  scheme?: Scheme;
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
  region: Region1;
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
/**
 * ADR-114 Amendment 33 decision 6: the stores sized to the server's memory. `memory_gib` is
 * measured once, at install (`server.memory_gib: auto`), and written here, so the render reads a
 * number and never the machine; resizing is an edit and `ospreyflow apply`. The three overrides
 * win over the rule (`harness/profiles.py`). Unset, every store keeps today's values.
 */
export interface ResourcesConfig {
  memory_gib?: MemoryGib;
  graph_heap_gib?: GraphHeapGib;
  search_heap_gib?: SearchHeapGib;
  postgres_shared_buffers_gib?: PostgresSharedBuffersGib;
  gpu?: Gpu;
}
