# 00 — Architecture

## 1. The shape of the system

```
                          THE GLASS  (stateless, horizontally scaled)
   ┌──────────────────────────────────────────────────────────────────────────┐   ┌────────────────────┐
   │  React + TypeScript workspace                                            │   │ IDENTITY PROVIDER  │
   │  Views: Graph (Sigma) · Map (MapLibre) · Timeline · Reports               │   │ Keycloak realm     │
   │  Places: Cases · Watches · Alerts · Ownership · History · Explore ·       │◄─►│ people, roles,     │
   │          Questions · Ingest Studio · Admin area                           │   │ dashboard          │
   │  One working set in browser memory; the rail follows /v1/me/rights        │   │ identities;        │
   └───────────────────────────────┬──────────────────────────────────────────┘   │ OIDC for the Glass,│
                       HTTPS (REST + SSE) · WebSocket for working-set deltas       │ Superset and each  │
   ┌───────────────────────────────┴──────────────────────────────────────────┐   │ dashboard          │
   │  THE CONDUIT  (stateless FastAPI, horizontally scaled)                    │◄─►│ (admin API: the    │
   │                                                                           │   │ Admin area's       │
   │  API surface ── Rights (ADR-112) ── Case levels (ADR-052) ── Audit        │   │ people/dashboards) │
   │        │                │                                                 │   └────────────────────┘
   │  Job orchestration: ingest → extract → resolve → load → score            │
   │  Rule gate (ADR-109): typology rules judge a load before commit and after │   ┌────────────────────┐
   │  Reports (ADR-111): one count behind the Reports view and the feed ───────┼──►│ REPORTING (opt-in) │
   └───┬──────────────┬──────────────┬───────────────┬────────────────────────┘   │ report-sync pulls  │
       │ GraphPort    │ AnalyticsPort│ ComputePort   │ ModelPort                   │ the feed as each   │
   ┌───┴──────────────┴──────────────┴───────────────┴────────────────────────┐   │ dashboard → mart   │
   │  THE VAULT                                                                │   │ (Postgres          │
   │  Graph store      Columnar OLAP     Graph compute      Model serving      │   │ osprey_reports) →  │
   │  ArcadeDB /       DuckDB /          graphology /       LiteLLM →          │   │ Superset / BI via  │
   │  JanusGraph       ClickHouse        rustworkx /        Ollama / vLLM      │   │ a read-only login  │
   │                                     GraphFrames        + Whisper + VLM    │   └────────────────────┘
   │                                                        Recogniser: Stanza │
   │  Working-set cache: Valkey     Object store: MinIO     Index: OpenSearch  │
   │  Conduit stores: Postgres (cases, grants, alerts, audit, export ledger)   │
   └───────────────────────────────────────────────────────────────────────────┘
```

Everything between tiers crosses a named port. Nothing else does. The two boxes on the right sit
outside the three tiers: the identity provider says who someone is (§1.3), and the reporting
components (§1.4) are consumers of the Conduit's feed, never readers of the Vault.

### 1.1 How the map is rendered

Both input documents specify Leaflet.js. This pack uses **MapLibre GL JS** (BSD-3) instead, and
Leaflet is not a dependency. The reason is the line above it in the diagram: the canvas is
Sigma.js, and the graph has to draw over the map in the same projection rather than beside it.

The rendering path:

```
MapLibre GL JS  ──  basemap, WebGL vector tiles
      │
      ├─ @sigma/layer-maplibre  ──  the Sigma graph canvas, camera-synced to the map
      ├─ Supercluster           ──  point clustering, expands on zoom
      ├─ MapLibre heatmap layer ──  fed by AnalyticsPort.geo_bins, binned server-side
      └─ raster layer           ──  georeferenced site imagery with drawn grid
```

What this buys over Leaflet:

- **One renderer, one camera.** `@sigma/layer-maplibre` projects the graph into the map's
  coordinate system, so a node with coordinates sits where it belongs and pan, zoom and rotate
  move both together. With Leaflet you run a WebGL graph over a DOM-and-canvas map and reconcile
  two camera models by hand.
- **WebGL throughout.** Leaflet is DOM-and-canvas based and degrades on the layer counts this
  product needs. MapLibre is GPU-rendered, which matters when a heat layer, a cluster layer, a
  snail trail and a graph overlay are live at once.
- **Vector tiles and offline.** MapLibre reads PMTiles from a local file, which is what makes the
  air-gapped requirement work without standing up a tile server. Raster tiles remain supported
  for scanned or georeferenced imagery.
- **Rotation and pitch.** Needed for site geospatial, where an aerial photograph is rarely
  north-aligned.

Leaflet's advantages are a smaller bundle and a larger plugin ecosystem. Neither outweighs the
projection problem here. If a Leaflet-only plugin proves necessary, `@sigma/layer-leaflet` also
exists and the swap is confined to `src/map/` — but treat that as a fallback, not a plan.

For point layers beyond roughly 500k features, **deck.gl** (MIT) composes with MapLibre as an
additional overlay. Do not add it in v1; server-side binning through `AnalyticsPort.geo_bins`
handles the volumes in the acceptance scenarios, and shipping a million raw points to the client
is the mistake the binning exists to prevent.

Full capability detail is in `02_GLASS_FRONTEND.md` §3.5; the decision record is ADR-014.

### 1.2 Geospatial data sources and provider choice

A fair catch: v1.1 covered basemap *rendering* and said almost nothing about geospatial
*reference data*. These are three separate concerns and only the first is fixed.

| Concern | Fixed or configurable | Ships as | Where it lives |
| --- | --- | --- | --- |
| Map renderer | **Fixed** — MapLibre GL JS | — | `apps/workspace/src/map/` |
| Basemap provider | **Configurable, swappable at any time** | OpenStreetMap, local tiles | `osprey.yaml` → provider registry |
| Gazetteer and reference data | **Configurable connectors** | OSM-derived gazetteer | `services/ingest/connectors/geo/` |
| Hosted provider credentials | **Optional, off by default** | — | Conduit tile proxy |

The renderer stays fixed for the projection reason in §1.1. Everything a deployment actually
needs to vary — which maps, whose data, online or offline — varies without touching it.

#### Providers ship as a tiered set, and the default needs no procurement

Four provider tiers ship in the repository. A deployment starts on tier 1 with nothing to sign,
and moves when entitlement or an existing corporate service allows. Moving is configuration.

| Tier | Provider | Data licence | Needs | Air-gapped |
| --- | --- | --- | --- | --- |
| **1 — default** | OpenStreetMap, built to local PMTiles | ODbL | Nothing | Yes |
| **2 — open UK** | OS OpenData (Open Zoomstack and friends) | Open Government Licence | Nothing — OGL is open to anyone, not just the public sector | Yes |
| **3 — entitled** | OS Data Hub premium (NGD, MasterMap, AddressBase, Places) | PSGA or a commercial OS licence | An OS Data Hub account and API key | Cached only |
| **4 — generic OGC** | Any WMTS, WMS, WFS or OGC API – Tiles/Features service | Whatever the service is under | A service URL, and credentials if it has them | Yes, if the service is internal |

Tier 4 is the one that matters most for a client base. It is not a vendor integration — it is
support for the open standards that ESRI ArcGIS Enterprise, GeoServer, QGIS Server, most national
mapping agencies and almost every corporate GIS already speak. In a government or enterprise
deployment the commonest real requirement is not Google or Mapbox but "connect to the WMTS
service we already run behind the firewall," and one generic implementation answers that for
every client at once. Build tier 4 properly and the long tail of named providers largely
disappears.

**Tier 1 is the shipped default and it is complete.** One button on the harness's Geospatial
screen downloads a Geofabrik extract, runs planetiler to produce PMTiles, and loads the
OSM-derived gazetteer, with progress shown as it goes. The
result is a fully working map and geocoder with no account, no key, no network at runtime and no
procurement conversation. That matters beyond convenience: the demo, the acceptance scenarios and
CI all run on tier 1, so the platform's tests never depend on someone's entitlement.

Two MapLibre styles ship with it, dark and light, built against `design/tokens.css` rather than
against a vendor's default palette. A basemap that fights the data palette is worse than no
basemap — the nine entity channels have to stay the most saturated thing on screen, so the
shipped styles are deliberately desaturated and sit on the neutral ramp.

**Tier 2 is a one-line swap** and is the right default for most UK deployments once someone has
downloaded the files. OS Open Zoomstack is a vector basemap under OGL, so it behaves exactly like
tier 1: local PMTiles, no key, air-gapped.

**Tier 3 is where OS becomes free-at-the-point-of-use for UK public sector** under the Public
Sector Geospatial Agreement, which covers premium products through the OS Data Hub. It is also
the first tier that involves a hosted API, which changes the security posture — see the proxy and
the caution below.

**Tier 4 covers everything else through standards rather than integrations.** Four service types:
`wmts` and `wms` for raster tiles, `wfs` and `ogc-features` for vector features that become
`Location` or `Jurisdiction` entities. Capabilities documents are parsed at registration, so
registering a service discovers its available layers, projections and zoom ranges rather than
asking someone to type them.

#### The provider registry

MapLibre consumes any style plus vector or raster sources, so a provider is data, not code.

```yaml
# osprey.yaml
map:
  default: osm-local
  providers:

    # Tier 1 — ships with the platform, no credentials, works offline
    - id: osm-local
      label: "OpenStreetMap"
      kind: vector
      source: file:///data/tiles/gb-osm.pmtiles
      style: bundled:osprey-dark            # and bundled:osprey-light
      attribution: "© OpenStreetMap contributors"
      licence: ODbL

    # Tier 2 — drop in the download, change `default`, restart
    - id: os-zoomstack
      label: "OS Open Zoomstack"
      kind: vector
      source: file:///data/tiles/os-open-zoomstack.pmtiles
      style: bundled:osprey-dark
      attribution: "Contains OS data © Crown copyright and database right 2026"
      licence: OGL-UK-3.0

    # Tier 3 — hosted, credentialed, proxied. Off unless explicitly enabled.
    - id: os-ngd
      label: "OS National Geographic Database"
      kind: vector
      source: "os-datahub://ngd/tiles"      # resolved by the tile proxy, never by the browser
      credential: env:OS_DATAHUB_API_KEY    # a reference, never a value
      proxy: required
      cache: {ttl_days: 30, prefetch_areas: [area-of-operations]}
      attribution: "Contains OS data © Crown copyright and database right 2026"
      licence: PSGA
      licence_note: "PSGA member licence. Not redistributable outside the licensed body."

    # Tier 4 — a service the client already runs. Capabilities parsed at registration.
    - id: wmts-corporate
      label: "Corporate aerial"
      kind: raster
      service: wmts
      endpoint: "https://gis.internal/geoserver/gwc/service/wmts"
      layer: "aerial:latest"
      licence: {id: internal, redistributable: false, client_scope: per-deployment}

    # Anything else — declared by profile rather than inline
    - id: esri-imagery
      profile: esri-arcgis-online          # providers/esri-arcgis-online.yaml
      variables: {service: World_Imagery}
      credential: env:ESRI_API_KEY

    - id: site-4471
      label: "HMP site aerial"
      kind: image                           # georeferenced, with control points
      source: file:///data/sites/4471.tif
```

Four source kinds cover the field: `vector` (PMTiles or MVT), `raster` (XYZ, WMTS or WMS),
`image` (a georeferenced photograph or plan, as in the HMP site analysis) and `dem` for terrain.
Every provider the registry lists appears in the map's layer control; the analyst switches
freely, and attribution and any licence note follow the layer onto every export.

**`kind: image` here is a different mechanism from a site plan as reference geodata** (the
"Geospatial reference data as entities" table below, "Site plans" row). This entry is
ops-provisioned, deployment-wide config: an already-georeferenced raster (a GeoTIFF with its own
embedded control points, or otherwise pre-registered) that a deployment drops into `osprey.yaml`
ahead of time, the same way any other provider is. It is not how an analyst's own uploaded site
photo becomes calibrated or becomes `Location` entities — that is a per-investigation capability
built on the connector framework (`services/api/sites.py`, `services/ingest/connectors/geo/
site_grid.py`), producing its own georeferencing live from control points the analyst places, and
it does not touch this registry at all. The two can describe the same physical site without
being the same object: a site an analyst has calibrated once could, later, be promoted to a
`kind: image` entry for other investigations to reuse as a basemap layer — but that promotion
step does not exist yet, and nothing does it silently.

Swapping the default at implementation time is three actions on the Set-up console's Geospatial
screen — add the provider, make it the default, run **Verify** — or the same three headlessly
(`05_DEPLOYMENT.md` §2.3). No rebuild, no code change, no migration. Existing investigations keep working because nothing
in the data model references a provider — see §1.2.1.

#### The tile proxy

Tier 3 providers are reached through a proxy in the Conduit, never directly from the browser.
Three reasons, each sufficient on its own:

- **Credentials.** An OS Data Hub key in frontend code is a published key. The registry holds a
  reference (`env:OS_DATAHUB_API_KEY`); the proxy resolves it.
- **Egress policy.** Default-deny egress is the platform's posture (`05_DEPLOYMENT.md` §7). The
  tile proxy is a named, auditable exception with one allowed destination, rather than the
  frontend acquiring general internet access.
- **Caching and entitlement.** The proxy caches tiles to object storage, which keeps usage inside
  whatever the licence permits and makes the map usable when the link is slow or absent.

**A caution that is easy to miss.** Tile requests to a hosted provider disclose where you are
looking. A pattern of requests for high-zoom tiles over one secure site, made from an identifiable
network, is an intelligence leak in itself, regardless of what the tiles contain and regardless of
handling markings on the data — the leak is the request, not the payload. For any investigation
whose area of interest is itself sensitive, use a tier 1 or tier 2 local provider, or prefetch the
area of operations into the proxy cache in advance so that live requests reveal nothing. The
harness asks about this at `init` and the map shows a small hosted-provider indicator whenever a
tier 3 layer is live, so the analyst always knows which mode they are in.

#### Provider profiles — the long tail without the maintenance

Anything beyond the four tiers is a **profile**: a validated YAML file in `providers/`, not code.
A profile declares the endpoint shape, style mapping, attribution, licence terms and auth
pattern for one provider. The registry entry then references it by id.

The distinction is about who carries the cost. Every provider shipped as *code* is a permanent
commitment — a style to maintain against the design tokens, a parity test in CI, a licence
review, and a support call when the vendor changes an endpoint. Ten of those is ten forever. A
profile costs one file and one **Verify** run, can be written by a client's own GIS
team, and can be wrong without breaking anyone else.

```yaml
# providers/esri-arcgis-online.yaml
id: esri-arcgis-online
label: "ESRI ArcGIS Online"
vendor: ESRI
kind: raster
service: xyz                    # xyz | wmts | wms | wfs | ogc-features | pmtiles | mvt | image
endpoint: "https://services.arcgisonline.com/ArcGIS/rest/services/{service}/MapServer/tile/{z}/{y}/{x}"
variables:
  service: {default: "World_Imagery", options: [World_Imagery, World_Topo_Map]}
auth:
  type: none                    # none | api_key_query | api_key_header | bearer | basic | oauth2
projection: EPSG:3857
zoom: {min: 0, max: 19}
style: bundled:osprey-raster-overlay
attribution: "Esri, Maxar, Earthstar Geographics"
licence:
  id: "esri-terms"
  redistributable: false
  client_scope: per-deployment
  note: "Subject to the deployment's own ESRI licence. Confirm before use."
proxy: recommended
```

Profiles to ship in `providers/`, each with a Verify fixture and none with a support
commitment beyond that:

Scoped to the UK and the US for now. Other geographies are a profile each when a client needs
one, which is the point of the format.

| Group | Profiles |
| --- | --- |
| UK | OS Data Hub (Maps, Vector Tile, Features), OS Open Zoomstack |
| US | USGS The National Map (topo, imagery, shaded relief, hydro), USGS 3DEP elevation, Census TIGERweb |
| Commercial | ESRI ArcGIS Online, Mapbox, MapTiler |
| Open hosted | OpenFreeMap, Protomaps |
| Self-hosted | GeoServer, QGIS Server, TileServer GL, Martin, pg_tileserv |

**Implementation note — OS Open Zoomstack appears twice, deliberately, not by inconsistency.** The tier-2 table above lists it as a local drop-in ("nothing needed",
air-gapped); the UK profile group here lists it again. These are two different consumption paths
for the same open dataset, not a duplicate entry to reconcile: a deployment that downloads
Zoomstack once and serves it from a local PMTiles file uses the tier-2 path (`osprey.yaml`'s own
`kind: vector` / `source: file://...` entry, no credential); a deployment that fetches it live
from OS Data Hub's own vector tile API instead uses the profile path
(`providers/os-open-zoomstack.yaml`), since OS Data Hub still requires a free API key for
rate-limiting even on fully open products — an `auth`/`endpoint` shape only a profile declares.
Both stay `redistributable: true` / `client_scope: open` under OGL either way.

ESRI stays in a narrowed list because a large share of US state and local agencies are already
ESRI shops with an existing enterprise licence, which usually makes tier 4 against their own
ArcGIS Enterprise the path rather than the hosted profile. The self-hosted group stays for the
same reason: in both countries the commonest real answer is a service the client already runs.

Two providers are deliberately absent and the reason should be recorded rather than rediscovered:

- **Google Maps.** Its terms generally prohibit using its tiles outside its own SDK. MapLibre can
  render them; you are not licensed to. Not supportable at any tier, and no profile ships.
- **Bing Maps.** Bing Maps for Enterprise has been on a retirement path with Azure Maps as the
  successor. Confirm where that has landed before promising it to a client; a profile can be
  written in an afternoon once the answer is known.

#### Satellite and aerial imagery is a separate axis

Maxar, Planet, Airbus and Vexcel are frequently what a client is actually paying for, and they do
not behave like basemaps. Imagery is scene-based, dated, and cloudy: the analyst needs a capture
date picker, a cloud-cover filter, and the ability to compare two dates over the same footprint.
Modelling that as another entry in the basemap layer control produces a bad version of both.

Treat it as its own capability when a client needs it: a `providers/imagery/` profile group with
a STAC-based catalogue interface — most current imagery providers expose STAC, which makes this
a standards problem like tier 4 rather than four integrations. Not in v1; the acceptance
scenarios use a static georeferenced image, which is the `image` source kind.

#### Licensing across multiple clients

With one deployment, licensing is a procurement question. With several clients it becomes a
technical constraint on the product, because the failure mode is easy to walk into: build a demo
on OS tiles under a PSGA entitlement, show it to a commercial client, and that is a breach. PSGA
covers the licensed body, not your product.

Three rules, enforced rather than documented:

1. **Licensed data is never baked into an image or a release artefact.** The bundle step refuses
   to package tiles or gazetteers whose profile says `redistributable: false`, and names them.
2. **`client_scope` is a required field** on every profile: `open` (redistributable, tier 1 and
   most OGL data), `per-deployment` (licensed to the deploying body — OS under PSGA, ESRI, a
   corporate WMTS), or `per-seat`. The export gate reads it: an export containing a
   `per-deployment` basemap carries the licence note, and the packaging step will not ship it.
3. **The demo and CI run on tier 1 only.** Enforced in CI by rejecting any non-`open` provider in
   the demo configuration. This is the commercial argument for the tier 1 default as much as the
   technical one — it means there is always a version of the product you can show anyone.

#### 1.2.1 What must stay stable across a swap

The reason a swap is safe is that nothing analytical depends on the provider. Four rules enforce
that, and **Verify** on the Geospatial screen checks them:

1. **A `Location` is never keyed on a provider identifier.** Its primary key is a ULID. UPRN,
   TOID, OSM node id and Geonames id are entries in the `identifiers` list, exactly like a PNC
   number on a `Person`. Key a location on UPRN and a move from OS to OSM breaks every edge
   pointing at it — this is the single most expensive mistake available in this area.
2. **Coordinates are stored in WGS84** and only ever projected for display. Tiles are Web
   Mercator; the data is not. See §1.2.2 — with the UK and US both in scope this stops being a
   formality.
3. **Attribution and licence travel with the layer**, onto screenshots and exports, because the
   obligation does.
4. **Styles reference design tokens, not literal colours**, so a new basemap inherits the theme
   rather than importing a vendor's.

**Verify** runs after any provider change: it fetches a sample tile at three zoom levels,
asserts the CRS and the zoom range the platform expects, renders a fixture graph over it and
compares against a stored reference for contrast floor compliance, and confirms attribution is
present. Two minutes, and it catches the usual failures — a provider whose maximum zoom stops
short of what site analysis needs, or a basemap bright enough to swallow the data palette.

#### 1.2.2 Coordinate reference systems

Supporting the UK and the US together makes reprojection a required capability rather than a
nicety, because neither country's authoritative data arrives in the projection the tiles use.

| Where | Common CRS | Note |
| --- | --- | --- |
| Tiles, everywhere | EPSG:3857 Web Mercator | Display only |
| Canonical storage | EPSG:4326 WGS84 | Every coordinate in the graph and the event tables |
| UK authoritative data | EPSG:27700 OSGB36 British National Grid | OS products, most UK public-sector GIS, and grid references in source documents |
| US authoritative data | EPSG:4269 NAD83, plus State Plane zones | County and state data is very often State Plane; the zone varies by state and sometimes within one |
| US federal | EPSG:4326 or NAD83 | TIGER/Line and USGS services generally offer both |

Three consequences for implementation:

- **Reprojection happens at ingest, once.** Incoming geodata is transformed to WGS84 on the way
  into the reference partition and the event tables, with the source CRS recorded alongside the
  original coordinates, exactly as the Knowledge Adapters retain `value_raw`. Reprojecting at
  query time would be both slow and a source of drift between views.
- **The source CRS must be declared, never guessed.** A file whose CRS cannot be determined from
  its metadata or a sidecar is rejected with a named error. Guessing between NAD83 and a State
  Plane zone silently places points hundreds of miles from where they belong, and the failure
  looks like ordinary data rather than an error.
- **Tier 4 services must be asked in a CRS the platform supports.** WMS and WFS advertise their
  available CRS in their capabilities document; `osprey map add` reads it and refuses a service
  that offers neither WGS84 nor Web Mercator rather than registering something that will
  misplace data later.

Use `pyproj` server-side and `proj4js` in the browser for the few display-time cases that need
it — chiefly showing a British National Grid reference in the inspector alongside the lat/long,
because UK source documents quote grid references and an analyst needs to match them by eye.

**Implemented as Knowledge Adapters** — `coordinate_lon`/`coordinate_lat` for a bare
coordinate, `geometry_ref` (the same reprojection, returning a deterministic reference instead)
and `grid_ref` (parsing a British National Grid reference first) for a `Location` — dispatched by
the same recipe-engine `transform:` mechanism every other normaliser uses
(`01_DOMAIN_MODEL.md` §7.1). `source_crs` is declared once per connector, the same way
`date_order` is (not needed for `grid_ref` — a grid reference is EPSG:27700 by construction); an
undeclared, unrecognised, or out-of-bounds-after-reprojection CRS is rejected, named and counted.
A `Location` node holds `geometry_ref` only, never coordinates directly — see
`03_CONDUIT_MIDDLEWARE.md` §5.1, which this build got wrong once and corrected rather than
patched. Tested against EPSG:27700 and two different NAD83 State Plane zones (Texas Central and
California Zone III), each with real place coordinates, so the two US zones are proven distinct
rather than merely "NAD83, handled somehow".

#### Gazetteers swap in parallel

A basemap is a picture; the geocoder needs data, and it follows the same tiers.

**United Kingdom**

| Tier | Gazetteer | Gives you |
| --- | --- | --- |
| 1 | OSM extract, place and address features | Place names, roads, POIs, coarse addresses |
| 2 | OS Open Names, Open UPRN, Code-Point Open, Boundary-Line | Place names, address points with UPRN, postcode and administrative geometry |
| 3 | AddressBase Premium, OS Places, NGD | Full address gazetteer, classification, lifecycle |

**United States**

| Tier | Gazetteer | Gives you |
| --- | --- | --- |
| 1 | OSM extract | Place names, roads, POIs, coarse addresses |
| 2 | USGS GNIS, Census TIGER/Line, National Address Database | Place names, roads and address ranges, administrative and statistical geography, address points where states contribute |
| 3 | State, county or city parcel and address data; a commercial gazetteer | Authoritative local addressing |

**The US has no AddressBase.** This is the significant structural difference and it is worth
knowing before a client conversation. TIGER/Line gives address *ranges* along road segments, not
address points; the National Address Database is voluntary and state-contributed, so coverage is
uneven; and authoritative address-point data is usually held at county or municipal level in
whatever format that authority happens to publish. A US deployment will often federate several
tier 3 sources across its area of operations rather than loading one national file.

That makes rule 1 in §1.2.1 load-bearing rather than merely tidy. Because a `Location` is keyed
on a ULID with UPRN, GNIS feature id, TIGER GEOID and any county parcel identifier all held as
identifiers, a US deployment can attach three county gazetteers and a state file to the same
location set without any of them being the key. Had the design keyed on an address identifier,
the US case would have needed a different data model from the UK one.

Because of that rule, moving up a tier enriches existing `Location` entities rather than
replacing them: the reference partition loads a new version, resolution attaches the new
identifiers, and previously resolved locations gain a UPRN or a parcel id without losing their
edges. An address that was `unresolved` under OSM may become `inferred` under AddressBase or a
county file; one already confirmed by an analyst stays confirmed.

Neither country's geocoder calls a hosted service at query time. The US Census Geocoder and OS
Places are used at load time to populate the reference partition, never with document content in
a live request.

**On Google, Bing and ESRI**, which the CoLP deck lists. The software licence is not the issue —
MapLibre is ours. The *data* terms are. Google's terms generally prohibit using its tiles outside
its own SDK, so it is not a supportable provider here whatever the code allows. ESRI and most
corporate WMTS services can be consumed as raster sources under their own licences. Treat each
commercial provider as a procurement question, not a technical one, and record the answer in the
provider entry's `licence` and `licence_note`. The platform will render whatever you are entitled
to render; it will not tell you what you are entitled to.

Verify the current OS Data Hub product names, endpoints and PSGA terms at implementation time
rather than trusting this document — OS revises both, and the registry exists so that a revision
is a configuration change.

#### Geospatial reference data as entities

This is the part that was missing. Basemaps are pictures; a gazetteer is data, and the platform
needs both. Reference geodata is ingested through the ordinary connector framework and becomes
`Location` entities and lookup tables, so it participates in search, resolution and traversal.

**"Site plans" here (the row below) is a distinct mechanism from `kind: image` above** — the
provider registry is a picture, this table is data, and a site plan is deliberately both at
once but through two separate paths: see the callout under "Four source kinds cover the field"
above for what stays separate and why.

| Source | Format | What it becomes | Note |
| --- | --- | --- | --- |
| OS Open Names | CSV / GeoPackage | Place-name gazetteer | Resolves free-text place mentions from extraction |
| OS Open UPRN | CSV | Address-point lookup | The `UPRN` referenced by the address normaliser |
| OS AddressBase | GML / CSV | Full address gazetteer | PSGA entitlement required |
| OS Boundary-Line, Code-Point Open | Shapefile / CSV | Administrative and postcode geometry | Aggregation and jurisdiction edges |
| OSM extract (Geofabrik) | PBF | Named features, roads, POIs | Where OS is unavailable or out of area |
| Force or agency boundaries | Shapefile / GeoJSON | `Jurisdiction` entities | Local, almost always |
| Site plans | GeoTIFF / image + control points | Site grid cells as `Location` | The HMP case |
| OGC services | WFS | Live feature layers | Cached, not queried per interaction |

Two design points that follow from this:

- **Geocoding is always a local lookup, never a hosted call.** An address or place name extracted
  from a document resolves against the reference partition, in-deployment. This holds at every
  tier: a hosted address API such as OS Places is used at *load* time to bulk-populate the
  partition, never at query time with document content in the request. An air-gapped deployment
  could not call out anyway, and sending extracted intelligence text to a hosted geocoder would
  breach the handling model in §5 regardless of connectivity. Basemap tiles are the only
  geospatial traffic permitted to leave the deployment, and only through the proxy.
- **A gazetteer match is `inferred`, like any other derived link.** "This statement mentions
  Cranford" producing a `Location` edge is a resolution decision with a confidence, not a fact.
  It follows the same provenance rules as a model extraction and is confirmable by an analyst.

Tile and gazetteer preparation is offline and one-off, and it is a button. **Build local basemap**
on the harness's Geospatial screen does the whole tier 1 path — download the extract, run
planetiler, load the gazetteer — with progress shown. Tiers 2 and 3 accept a prepared PMTiles file
or a credential reference on the same screen. See `05_DEPLOYMENT.md` §2.2.

### 1.3 The request path and analyst sign-in

**The request path (first paragraph) is decided — the owner's decision of 25 September 2026, and
it is built. Analyst sign-in (the rest) is accepted and built** (ADR-050 and its amendments; the
launcher's and the Set-up console's own sign-in, ADR-051).

The Glass is served by the workspace container's nginx, which also reverse-proxies the Conduit's
API (/v1) and the delta WebSocket to the Conduit over the deployment's internal network. The
browser therefore has one origin, the workspace's; the Glass bundle carries no Conduit address and
is portable across deployments unchanged; and the Conduit's host port is published only when the
deployment's configuration asks for it, for headless clients. Only the workspace and the identity
provider are reachable from the browser.

An analyst signs in with OpenID Connect authorization code flow with PKCE against the deployment's
identity provider, with the Glass registered as a public client. Credentials are entered at the
identity provider, never in the Glass. The Glass receives a signed access token carrying the
principal's subject, clearance, organisational unit, roles and receivable handling codes, holds it
in memory, and sends it as a bearer token on every request; nginx forwards it unchanged. The
Conduit verifies the signature against the identity provider's published keys and resolves the
principal from the claims. The Glass may display what the token asserts about the analyst; it never
derives access from it. Access control is applied in the Conduit's query, as everywhere else in the
system.

When a token expires during an investigation the Glass preserves only the investigation id, the
current selection and the view state in session storage — small identifiers, not the working set —
re-authenticates with a fresh authorization-code round, and re-fetches the working set from the
Conduit before restoring the view. No refresh token is held in the browser. It neither continues on
a stale token nor discards the analyst's place in the investigation. Signing out clears the Glass's
memory and session storage and ends the identity-provider session.

The analyst's token and the Conduit's owner-side token exchange are distinct mechanisms: the former
is how an interactive caller is identified; the latter is how the Conduit evaluates a watch as its
owner, and it is never used for the interactive caller.

### 1.4 Identity, rights, administration and reporting — the interfaces outside the tiers

Built 11 October 2026 (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-111 and its Amendment 2, ADR-112,
ADR-052 Amendment 12). Each interface below has one owner and one direction:

| Interface | From → to | What crosses it | What guards it |
| --- | --- | --- | --- |
| Sign-in (OIDC, code + PKCE) | Glass → identity provider | a person's credentials, entered there only | the identity provider |
| Bearer token | Glass → Conduit | subject, clearance, unit, roles, handling codes | signature against the realm's keys |
| `GET /v1/me/rights` | Conduit → Glass | the caller's rights, from their roles | — (the Glass only hides; the Conduit refuses) |
| `/v1/admin/*` | Glass's Admin area → Conduit → identity provider's admin API | people's `roles`, dashboard identities, component health, feed freshness | `manage_people` / `manage_dashboards` / `administer_system`; only `osprey-dashboard-*` clients; a dashboard's clearance capped at its registrar's |
| `…/access` (the Share panel) | Glass → Conduit | who holds which level on a case, by account id | the case's Author (or the administrator's safety net) and `share_case` |
| `…/reports/feed` | report-sync → Conduit | figures only (CSV/JSON), counted as the dashboard | the dashboard's own token (client credentials), its clearance and its case grants; each read in the export ledger |
| Reporting mart | report-sync → Postgres `osprey_reports` | the feed's rows, upserted; per-case pull times and failures | owned by report-sync; never the Conduit's tables |
| Mart reader | Superset / a BI tool → `osprey_reports` | `SELECT` only | the read-only login `osprey_reports_reader` |
| Embedded board | Glass → Conduit (`/v1/reports/dashboards`) → Superset (guest token) | a five-minute read-only token for one board, rows limited to its identity | `read_reports`; the viewer could count every figure the identity counts; framed only by the Glass |
| Superset sign-in (OIDC) | Superset → identity provider | a person's identity; `osprey-admin` → Superset Admin, other roles → Gamma | id_token verified against the realm's keys and issuer |

**Three axes of authorisation, never folded into one.** *Clearance and handling* decide what a
principal can **see**, applied in the adapter's query (§5, rule 3). *Case levels* — Viewer, Editor,
Author (ADR-052) — decide **where** a principal can act. *Rights* — 42 named rights bundled into four
roles, Analyst, Data Engineer, Admin and Reports Viewer (ADR-112) — decide **what** a principal can
do; each route declares the right it needs (`require_right`), and a route without one fails the
route-rights test. A right never widens what a principal can see, and a level never confers a right.

**A dashboard is an identity like a person.** An administrator registers it in the Admin area (a
confidential client whose secret is shown once); a case's Author gives its account Viewer on the
case; `report-sync` pulls each granted case's feed as that identity every interval, one pull per
slot across instances, and writes the mart. Revoking the grant empties the next pull. The Admin
area shows each dashboard's freshness from the mart's `pulls` table — aggregates only, never which
cases it reads.

**The Set-up console and the Admin area are different places.** The harness is the pre-launch
Set-up console (`05_DEPLOYMENT.md` §2); everything an administrator does after launch is in the
Glass's Admin area, behind the same sign-in as everything else.

## 2. The four ports

These are the swap boundaries. Each is a Python `Protocol` in `packages/ports/`, each has a
conformance test suite in `tests/conformance/`, and a component is only supported if it passes
its suite. Adding a new backend means writing an adapter and turning the suite green — no
changes above the port.

Two narrower ports sit beside the four, each also a `Protocol` with its suite written first, but
neither is a tier boundary the way the four are: **`RecognisePort`** (`packages/ports/recognise.py`,
ADR-098 decision 2), the fast named-entity pass *Extract entities* runs, served by Stanza in its own
`ner` sidecar — and, since ADR-108, by spaCy and transformers adapters a pipeline's extract node may
name (`recognise_spacy`, `recognise_transformers`) — whose findings are proposals like a model's; and **`MediaStore`**
(`packages/ports/media.py`, ADR-094), which keeps a file's bytes in the object store under a
reference, never in the graph.

### 2.1 GraphPort

Persistent property graph: write, traverse, subgraph extraction, schema management.

```python
class GraphPort(Protocol):
    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]: ...
    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]: ...
    async def get_node(self, node_id: NodeId, principal: Principal) -> Node | None: ...
    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph: ...
    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]: ...
    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph: ...
    async def neighbourhood_stats(self, node_id: NodeId, principal: Principal) -> NeighbourhoodStats: ...
    async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...
    async def revert_schema(self, to_version: int) -> SchemaReport: ...
```

Gremlin is the query language; TinkerPop 3.8 is the target. **The transport is the adapter's
business.** WebSocket with GraphBinary is the default where an engine runs a Gremlin Server
listener, but some engines expose Gremlin over an HTTP command endpoint instead and run no
separate listener. Either is conformant — what the port guarantees is the language and the fact
that it never crosses into the Conduit's callers, not the socket underneath. An adapter records
its transport in its README and proves itself the same way regardless: the conformance suite.
On ArcadeDB 26.10.1 the adapter's Gremlin runs on the engine's Groovy engine
(`-Darcadedb.gremlin.engine=groovy`), because the default grammar parser refuses the bound variables
and closures its writes use; that engine answers over HTTP only to `root`, the user the adapter
connects as (ADR-101 decision 2). Rewriting the Gremlin for the grammar parser is future work.

**Gremlin never leaves the Vault.** The Conduit builds Gremlin; the Glass never sees it and
never sends it. This is what makes a future move to SQL/PGQ or openCypher an adapter change
rather than a frontend rewrite. It is also the security boundary: an analyst cannot author a
traversal that bypasses the access filter (§5).

**`GraphPort` grew beyond this illustrative snippet** — transactions and schema management first,
then `find_node` and `revert_elements`, without re-litigating the snippet each time
(`01_DOMAIN_MODEL.md` §8 records why: the doc never specified the request/response shapes either,
and a real adapter has to). The port also gained `get_node(..., include_superseded: bool = False)`
and `supersede_node(node_id, replacement, tx) -> NodeId`, closing a gap the schema already
implied: `01_DOMAIN_MODEL.md` §2.4 requires a correction to write a new revision and point the old
one forward, and without this method nothing actually enforced that a superseded node stops
appearing in ordinary reads. The workflows that call it — retraction, the judgement-review loop —
are not yet implemented; the capability belongs on the port now, against the one adapter that
exists, the same reasoning as `find_node`.
`supersede_node` also repoints every edge incident to the old node onto the new one (cloned, not
moved — confirmed empirically that ArcadeDB does not support relinking an edge's endpoints after
creation), so a correction cannot silently disconnect a node from its own network. `supersede_edge`
is the same operation for an edge: `01_DOMAIN_MODEL.md` §5's `Judgement.supporting`/`contradicting`
can cite an `EdgeId` directly, so an edge needs the same "corrected, not vanished" guarantee — it
has nothing to repoint, since nothing else in the domain model references an edge by id.
Later reads, each with the access step on the element and on both ends of every link: `edges_among`
(the links among a set of nodes, ADR-098 decision 1), and `type_counts` and `most_connected` (the
Explore panel's counts and degree ranking, ADR-100 Amendment 1). `expand_candidate_count` takes the
case's `datasets` (ADR-099 decision 4).

Supported adapters: `arcadedb`, `janusgraph`. Candidate: `hugegraph`.

> **Bulk writes (ADR-058, accepted in its Amendment 1).** `upsert_nodes` and `upsert_edges` are the low-volume write
> path: merge-on-write, a weight against the live corpus, one element's worth of round trips each. A set that arrives
> together (a seed; the Enron and PaySim seeds load in bulk by default, Amendment 10) goes through the optional
> `BulkGraphLoader` capability, which an adapter may declare and which the caller falls back from to chunked
> `upsert_*` where it is absent.

### 2.2 AnalyticsPort

Columnar aggregation over event-shaped data: temporal histograms, geospatial binning, baseline
statistics, cross-filter counts. This is SQL, not traversal.

```python
class AnalyticsPort(Protocol):
    async def histogram(self, req: HistogramRequest, principal: Principal) -> Histogram: ...
    async def geo_bins(self, req: GeoBinRequest, principal: Principal) -> list[GeoBin]: ...
    async def cross_filter(self, req: CrossFilterRequest, principal: Principal) -> dict[str, Histogram]: ...
    async def baseline(self, req: BaselineRequest, principal: Principal) -> BaselineResult: ...
```

It has grown beyond this snippet like `GraphPort`: `first_seen` (when each node first appears in
the events, ADR-087 decision 1) and `list_events` (a paged read of the events themselves, ADR-089
decision 2), each taking the principal like the rest.

**There is no `raw_sql` escape hatch, deliberately.** An arbitrary SQL string cannot be
access-filtered — the same reason the Conduit never accepts free-form Gremlin (ADR-003). Every
`AnalyticsPort` method takes a `Principal` and the adapter injects the filter into the `WHERE`
clause before the query runs. A method that would let a caller write its own predicate over the
event tables is a hole straight through the handling model, whatever the calling code intends.
If an aggregate is needed that the port cannot express, add a typed method with a request object
and a conformance case, not a passthrough.

Results are Arrow tables end to end — Arrow IPC from Vault to Conduit, Arrow IPC over the wire
to the Glass where the size warrants it. Do not round-trip histogram data through JSON.

Supported adapters: `duckdb`, `clickhouse`.

### 2.3 ComputePort

Graph algorithms: centrality, community detection, the Clique Metric, shortest path at scale, and
— since ADR-109 — cumulative beneficial ownership and distance-decayed risk propagation.
Separate from `GraphPort` because it has a different scaling profile — batch, memory-hungry,
tolerant of staleness — and a different deployment shape.

```python
class ComputePort(Protocol):
    async def centrality(self, req: CentralityRequest) -> dict[NodeId, float]: ...
    async def communities(self, req: CommunityRequest) -> dict[NodeId, CommunityId]: ...
    async def clique_metric(self, req: CliqueMetricRequest) -> dict[NodeId, CliqueScore]: ...
    async def shortest_paths(self, req: PathRequest) -> list[Path]: ...
    async def temporal_motifs(self, req: MotifRequest) -> list[MotifMatch]: ...
    async def ownership(self, req: OwnershipRequest) -> OwnershipTrace: ...       # ADR-109 phase C
    async def propagate(self, req: PropagationRequest) -> PropagationResult: ...  # ADR-109 phase E
```

`ownership` and `propagate` are implemented on two tiers that must agree exactly — rustworkx in the
Conduit and a graphology harness in Node (`compute_graphology_tier1`) — and each is called with a
subgraph already read *as the reader* through `GraphPort`, so a node the reader cannot see never
enters the arithmetic (rule 3). Neither writes anything: due diligence and neighbourhood risk are
reads (ADR-109 ruling 9).

Three tiers of implementation, selected by working-set size, not by deployment profile:

| Working set | Engine | Where it runs |
| --- | --- | --- |
| ≤ 20k nodes | graphology + graphology-metrics | Browser, in a Web Worker |
| ≤ 2M nodes | rustworkx (Apache 2.0, Rust core) | Conduit worker process |
| > 2M nodes | GraphFrames on Spark, or HugeGraph Vermeer | Vault, batch |

The browser tier matters: it is what makes the timeline slider feel instant. See §4.

### 2.4 ModelPort

Language, speech and vision inference. One OpenAI-compatible base URL, one config file.

```python
class ModelPort(Protocol):
    async def extract(self, req: ExtractionRequest) -> ExtractionResult: ...
    async def transcribe(self, req: TranscribeRequest) -> Transcript: ...
    async def describe_image(self, req: VisionRequest) -> ImageAnalysis: ...
    async def embed(self, texts: Sequence[str]) -> list[Vector]: ...
```

Backed by a LiteLLM proxy (MIT, self-hostable, runs air-gapped) in front of Ollama on a laptop
and vLLM on a GPU cluster. Model choice, routing, fallback, per-team budgets and rate limits are
`litellm-config.yaml`. The model for each job (extraction, vision, transcription, embedding) is the
deployment's own, chosen on the setup harness's *Models* screen from a closed list of pinned models,
written to `osprey.yaml` as `models.*` and rendered into the proxy's routing table (ADR-095); a name
off the list is refused, and the conformance suite keeps its own small model.

## 3. Quality attributes and how each is actually achieved

Stating an attribute is not achieving it. Each row names the mechanism and the test that proves
it.

| Attribute | Mechanism | Proof |
| --- | --- | --- |
| Open source | Licence register (§7); CI gate fails the build on a non-allowlisted licence | `make licence-check` |
| Frontend scale | Glass and Conduit are stateless; session state in Valkey; WebGL renderer | k6 script: 500 concurrent sessions, p95 interaction < 150 ms |
| Working-set scale | Server-side working set in Valkey, delta-streamed; browser holds ≤ 50k nodes | Load a 50k-node set, timeline scrub at 60 fps |
| Backend scale | Graph store and OLAP engine scale independently; compute is batch | Ingest 100M edges on the cluster profile |
| Maintainable | Monorepo, per-service Dockerfiles, Renovate, no cross-service version pins | Upgrade any one service without touching another's lockfile |
| Model flexible | ModelPort + LiteLLM | Swap extraction model, re-run extraction golden set, diff |
| Transportable | Same images in both profiles; harness generates config, not architecture | Same acceptance suite passes on `local-lite` and `cluster` |

## 4. Where the data actually lives during analysis

This is the single most consequential design decision in the platform, and the one the input
documents leave vague. "Load data into the memory cache for analysis" can mean three different
things; OspreyFlow does all three, at different scales.

**The persistent graph** lives in the Vault. It may be arbitrarily large. Nobody queries it
interactively.

**The working set** is what one analyst is currently investigating: the subgraph they have
expanded into, plus the events attached to it. It is bounded at **50,000 nodes and 250,000
edges** by policy, held server-side in Valkey keyed by `investigation_id`, and streamed to the
browser as deltas over a WebSocket. It is the unit of undo, of branching to a new tab, and of
save/restore.

**The browser set** is the working set, in memory, in a graphology instance. Filters — timeline
brush, histogram selection, map viewport, degree threshold — operate on the browser set only,
with no network call. This is why scrubbing the timeline is instant and why the five analytical
views cross-filter each other without a round trip.

**Beside the graph, four kinds of record are deliberately kept out of it (ADR-109):**

- **Screening lists** live in their own Postgres store (`services/api/screening.py`), deployment-wide,
  loaded and replaced a whole list at a time, each entry marked synthetic or not (the loader refuses a
  list not marked synthetic unless the owner's exceptions file names it). Only a listed party a
  customer is found to match enters a case's graph, as a scored, `inferred` `SAME_AS` — never a
  merge (rule 6). A real list is admitted only through the licence register and the owner's local
  exceptions list (rule 9).
- **Held rows** — rows a pre-commit rule could not judge — wait in a quarantine store
  (`services/api/held_rows.py`) with their marking, reaching no graph or analytics store until a
  reviewer releases or rejects them (`09_INGEST_STUDIO.md` §6).
- **KYC status and risk are never stored.** They are computed at each read, as the reader, from what
  the reader can see (`services/api/kyc.py`); two analysts with different clearances may read
  different scores, and neither score is a record.
- **The daily KYC expiry sweep** is the deployment's first periodic pass: a lifespan task that one
  replica a day claims through Valkey (`SET NX`), raising an alert when a verifying document lapses —
  the change stream never sees a clock pass (`services/api/kyc_sweep.py`).

Expanding beyond the working-set cap does not silently truncate. The Glass offers three explicit
choices: expand into a new branch tab, apply a filter before expanding, or promote the expansion
to a batch job whose result is a saved subgraph. Silent truncation of an intelligence picture is
a correctness failure, not a performance trade-off.

## 5. Access control and audit as architecture, not a feature

The HMP Hollywood report carries a handling instruction (`P — lawful sharing permitted`), an
action code (`A1 covert development`) and a sanitisation code (`S2 consult originator`) on its
face. None of the other input documents model this, and it cannot be retrofitted later — it has
to be on every node and edge from the first write.

- Every node and edge carries a `handling` block (see `01_DOMAIN_MODEL.md` §5).
- The Conduit resolves a `Principal` from the session token and passes it into every
  `GraphPort` and `AnalyticsPort` read. Every read method takes one — including the aggregate
  ones. A count is a read: `neighbourhood_stats` returns a degree, and an unfiltered degree
  discloses the existence of neighbours the principal may not see just as plainly as returning
  them would. Any read signature without a `Principal` is a defect, not an optimisation. Adapters inject the filter into the traversal or the
  `WHERE` clause. **No adapter may accept a call without a `Principal`** — enforced by the
  conformance suite, which asserts that an unauthorised principal cannot observe a filtered
  node's existence, not merely its properties.
- The `Principal` also carries the datasets of the case its request path names
  (`Principal.datasets`, ADR-099). The adapter limits every read to them in the same access step as
  handling, so a node of another dataset is as absent as a hidden one. A request that names no case
  carries none and reads nothing; only the Conduit's own background work (resolution, a load's
  lookups, seeding) reads unlimited (`datasets=None`), and no request handler can make that
  principal.
- Seeing is not doing. A case level (ADR-052) and a right (ADR-112) are checked in the Conduit
  before a route runs — a missing level is the same 404 as a missing case, a missing right a 403 —
  and neither changes the `Principal` filter the adapter applies (§1.4).
- Redaction is not deletion: a filtered node is absent from the result, and the count is
  reported as filtered so the analyst knows the picture is incomplete. Showing a confident but
  partial network without saying so is worse than showing nothing.
- Every read, expansion, query and export is written to an append-only audit stream with
  principal, timestamp, query, result cardinality and justification string. The justification
  is a required field on any expansion that crosses a handling boundary.

## 6. Repository layout

The product tree, as of 11 October 2026 (ADR-054 keeps the specification, the build record and the
test suites beside it rather than inside it, and local data outside version control altogether):

```
OspreyFlow_Core/
├── apps/workspace/             # The Glass. React + TS + Vite; src/ holds, among others:
│   ├── canvas/ timeline/ map/  #   the five views' renderers and the working set (workingset/)
│   ├── inspector/ metrics/     #   the right-hand panels (patterns/ is the Query builder)
│   ├── alerts/ ownership/      #   the Alerts and Ownership places (ADR-109)
│   ├── reports/ admin/         #   the Reports view (ADR-111) and the Admin area (ADR-110 Am. 1)
│   ├── investigation/          #   the case picker, switcher, datasets and Share panel (ADR-052)
│   ├── rights/                 #   what the rail and views show for the caller's rights (ADR-112)
│   ├── ingest/                 #   the Ingest Studio: dag/ (pipelines home and canvas), map/, verify/, publish/
│   └── design/                 #   tokens.css, primitives
├── services/
│   ├── api/                    # The Conduit. FastAPI; the rule gate, held rows, screening, KYC, sweep
│   ├── ingest/                 # Connectors, the engine, the pipeline runner, Knowledge Adapters
│   ├── extract/                # Multimodal extraction workers
│   ├── resolve/                # Splink entity resolution
│   ├── ner/                    # The recogniser sidecar: Stanza (ADR-098)
│   ├── geocoder/               # Gazetteer matching: a scored, inferred SAME_AS, never a merge
│   ├── compute/                # ComputePort workers
│   └── report_sync/            # Feeds each dashboard's figures into the reporting mart (ADR-111 Am. 2)
├── packages/
│   ├── ports/                  # Protocol definitions — the architecture
│   ├── adapters/               # graph_arcadedb, analytics_duckdb, compute_rustworkx,
│   │                           # compute_graphology_tier1, model_litellm, recognise_stanza,
│   │                           # recognise_spacy, recognise_transformers, media_objectstore
│   ├── ontology/               # Schema definition (default.yaml, v16), packs, validation
│   ├── schemas/                # Shared Pydantic + generated TypeScript types
│   └── demo_fixtures/          # Synthetic fixtures (rule 9), e.g. Operation Ledger
├── connectors/ providers/      # Connector and map-provider profiles (YAML)
├── recipes/                    # Published ingest recipes — the repository is the record
├── harness/                    # The Set-up console: pre-launch setup (post-launch is the Glass's Admin area)
├── deploy/                     # Generated compose files per profile; superset/ (the reference dashboard image)
└── scripts/                    # Operational modules, `python -m scripts.<name>`
```

The adapters named in §2 as supported but not listed above — `graph_janusgraph`,
`analytics_clickhouse`, and Spark or Vermeer for the third compute tier — are the ports' planned
second implementations, not yet built; each lands with its conformance suite green (rule 1).

Shared types are generated, not hand-mirrored: Pydantic models in `packages/schemas` are the
source of truth and TypeScript types are emitted from their JSON Schema at build time. A drift
between the API contract and the client types must be a build failure.

## 7. Licence register

The build fails if a dependency's licence is not on the allowlist.

**Allowed outright:** Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, MPL-2.0, SIL-OFL-1.1,
PSF-2.0, Python-2.0, Unlicense, CC0-1.0, CC-BY-3.0, CC-BY-4.0. The last five arrive almost
exclusively through transitive dependencies — documentation, data files, small utility packages —
and excluding them would fail the build on packages nobody chose and nobody can avoid.

**Requires review:** LGPL-3.0, LGPL-2.1. Not on the allowlist, because the condition that makes
them acceptable here — dynamic linking only — is not something `pip-licenses` or
`license-checker` can see. Both tools read declared metadata; neither inspects linkage. So an
LGPL dependency fails the check and is admitted only by a recorded exception naming the package,
the linkage mode and who assessed it. Do not write an unenforceable qualifier into the
allowlist and assume the tooling honours it.

**Fetched at deployment, not shipped in the repository:** the basemap's label glyphs, Noto Sans
Regular from the OpenMapTiles fonts release v2.0 (SIL-OFL-1.1), installed into the tiles folder by
`scripts.fetch_basemap_glyphs`, pinned by SHA-256 and served by the deployment itself, never from a
CDN (spec 02 §3.4). Like the OpenStreetMap data the basemap is built from (ODbL), it is data the
deployment holds, not a dependency of the code.

**ADR-108 additions (9–10 October 2026), each on the allowlist unless said otherwise:** spaCy
(MIT) and its `en_core_web_sm` pipeline (MIT); Hugging Face `transformers` (Apache-2.0) with
`torch` (BSD-3-Clause); the `dslim/bert-base-NER` weights (MIT, per its model card), fetched once
into the local Hugging Face cache and served from disk thereafter; `geopy` (MIT — its *online*
geocoders are governed by ADR-108 ruling Q5, local gazetteers first and any online use disclosed
per run). **Recorded LGPL exception:** `deepparse` (LGPL-3.0) — imported unmodified as a separate,
user-replaceable installed package, never vendored, statically bundled or modified; assessed
10 October 2026 under ADR-108 (the owner's authorisation of the dependency set is in the ADR).
Jube (AGPL) and AMLTRIX (commercial, unverifiable as open source) are rejected with CoreNLP below;
the AML typologies are our own rules (`services/ingest/typologies.py`).

**ADR-111 Amendment 2 additions (11 October 2026) — the reference dashboard, in its own container
(`deploy/superset/`), never imported by OspreyFlow's code:** Apache Superset (Apache-2.0), the
official image pinned by digest; Authlib (BSD-3-Clause) for its single sign-on. **Recorded LGPL
exception:** `psycopg2-binary` 2.9.6 (LGPL-3.0, with its bundled libpq under the PostgreSQL
licence) — Superset's own Postgres driver, installed unmodified as a separate package inside the
Superset image only, never vendored, statically bundled into OspreyFlow or modified; assessed
11 October 2026 by the owner ("psycopg2 + exception"). **ADR-111 Amendment 3:**
`@superset-ui/embedded-sdk` (Apache-2.0; 0.4.0 since ADR-111 Amendment 4, with Superset 6.1.0) in the Glass, with `@superset-ui/switchboard`
(Apache-2.0) and `jwt-decode` (MIT). The BSD alternative, pg8000, was tried first
and does not work with Superset: it types a string parameter as `varchar`, and Superset looks
charts and dashboards up by the URL's id as a string, so every edit and delete answered "Not found".

**ADR-114 Amendment 4 addition (12 October 2026):** Caddy (Apache-2.0), the deployment's front
proxy, the official image `caddy:2.11.4-alpine` run unmodified in its own container and locked by
digest in `versions.lock` like every other third-party image; nothing of OspreyFlow imports it.

**ADR-114 decision 9 addition (13 October 2026):** ClickHouse server (Apache-2.0), the
Enterprise profile's analytics store, the official image `clickhouse/clickhouse-server:25.8.33.6`
run unmodified; the adapter talks to it over HTTP with `httpx`, so no ClickHouse driver is imported.
**ADR-114 decision 8 addition (13 October 2026):** the Blob media adapter (`adapters/media_blob`)
speaks Azure Blob's REST interface with `httpx` and Shared Key signing, so no Azure SDK is imported.
Its tests run against Azurite (MIT), `mcr.microsoft.com/azure-storage/azurite:3.35.0`, a test-only
image that never ships in a deployment.

**PaySim (ADR-055 Amendment, ADR-114 decision 5, 11 October 2026) — data, CC BY-SA 4.0**, verified
from Kaggle's metadata for `ealaxi/paysim1` (Edgar Lopez-Rojas). Redistributable as a downloadable demo
pack, never in a repository, with its attribution and licence text; anything derived from it and
redistributed carries the same licence. Not on the code allowlist: it is data, recorded here. `make
licence-check` admits it only for a pack delivered by download (`delivery: download` in
`scripts/demo_registry.py`) and flags it for anything seeded or bundled (ADR-114 Amendment 1); the
pack carries `packages/demo_fixtures/licences/paysim/LICENSE.txt` and `ATTRIBUTION.md`.

**ADR-109 data sources (10 October 2026) — data, not code, and never in the repository or CI.**
**OpenSanctions** consolidated data: CC-BY-NC 4.0 for the bulk data — attribution required, and
**non-commercial use only**; any commercial or client-facing use needs OpenSanctions' commercial
licence first. Admitted only through the owner's local `config/real_data_exceptions.yaml` (rule 9,
ADR-035 §C3), on the owner's device, for local development or an owner-run demonstration;
`scripts/load_screening_list.py` refuses a list not marked synthetic unless that file names it.
**ICIJ Offshore Leaks**: real people's data (ODbL for the database, with ICIJ's own terms of use);
the same local-only admission. What the repository and CI hold is
`packages/demo_fixtures/screening_list_synthetic.yaml` — invented names, marked synthetic.

The rejections below matter more than the acceptances, because each is a component someone will
otherwise reach for by reflex. Two of them appear in the input documents.

| Rejected | Licence | Replacement | Note |
| --- | --- | --- | --- |
| Redis (7.4+) | RSALv1 / SSPLv1 | **Valkey** (BSD-3, Linux Foundation) | The Gemini spec specifies Redis for the cache while correctly rejecting FalkorDB for SSPL. Same trap. ADR-004 |
| Elasticsearch | SSPL / Elastic Licence | **OpenSearch** (Apache-2.0) | Named as the JanusGraph index in the Gemini spec. Same trap |
| Neo4j Community | GPLv3 | ArcadeDB / JanusGraph | GPL reciprocity on a platform intended for wide distribution |
| ArangoDB | BSL 1.1 | ArcadeDB | Relicensed 2024 |
| FalkorDB | SSPLv1 | rustworkx for in-memory algorithms | Correctly rejected by the Gemini spec; retained here |
| Mapbox GL JS v2+ | Proprietary | **MapLibre GL JS** (BSD-3) | The v1 fork is the maintained open path |
| MongoDB | SSPL | PostgreSQL / MinIO | |
| Highcharts, AG Grid Enterprise | Commercial | Apache ECharts, TanStack Table | |
| Grafana (9+) | AGPLv3 | Perses, or Grafana as a separate unbundled deployment | AGPL is acceptable for an unmodified separate service, not for bundling |
| Stanford CoreNLP | GPL-3.0 | **Stanza** (Apache-2.0), held at 1.10.1 | Stanza 1.11.0 to 1.15.0 pull in `udtools` (GPL-2.0-or-later) and `udapi` (GPL-3.0-or-later). ADR-098 |

Fonts: Atkinson Hyperlegible Next and IBM Plex Mono are both SIL OFL 1.1. Self-host them; do not
load from a CDN — an air-gapped deployment must render correctly.

`make licence-check` runs `pip-licenses` and `license-checker` against the allowlist and fails
on any addition. Run it in CI on every pull request, not nightly. A sidecar's own environment is out
of its sight, so the `ner` image gates its licences itself at build (`services/ner/licence_gate.py`,
the same allowlist, default-deny; ADR-098 Amendment 1).

Prove the check works with a committed fixture — a lockfile containing a known GPL-licensed
package, and a test asserting `licence-check` rejects it by name. A licence gate nobody has
watched fail is a gate nobody knows the state of, and the fixture makes that proof run on every
pull request rather than once at setup.

## 8. What this architecture deliberately does not do

Recorded so that a later reader does not mistake an omission for an oversight.

- **No real-time streaming ingestion in v1.** Batch and micro-batch only. A Kafka or NATS lane
  can be added behind the ingest service later; building it now would cost the schedule and the
  acceptance scenarios do not need it.
- **No graph-native vector search in v1.** Embeddings live in OpenSearch, not in the graph
  store, so that the graph store stays swappable. ArcadeDB's native vector support is a reason
  to revisit, not a reason to depend on it.
- **No multi-tenancy in v1.** One deployment serves one organisation. Handling markings
  partition data within it; they are not a tenancy boundary.
  *Amended by ADR-056 (30 September 2026): one deployment may hold several vaults, one per dataset,
  within the same organisation. A vault is not a tenant; the organisation is still one.*
  *Datasets (ADR-099) also partition what a case reads within the one organisation, enforced in
  every read like handling; they are not a tenancy boundary either.*
- **No mobile client.** The workspace targets a desktop analyst at ≥ 1440px. Responsive down to
  1024px for review, not for analysis.
