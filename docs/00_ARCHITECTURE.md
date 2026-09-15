# 00 — Architecture

## 1. The shape of the system

```
                          THE GLASS  (stateless, horizontally scaled)
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  React + TypeScript workspace                                            │
   │  Canvas (Sigma/graphology) · Timeline · Map (MapLibre) · Dossier · Query  │
   │  One working set in browser memory, driven by one shared filter state     │
   └───────────────────────────────┬──────────────────────────────────────────┘
                       HTTPS (REST + SSE) · WebSocket for working-set deltas
   ┌───────────────────────────────┴──────────────────────────────────────────┐
   │  THE CONDUIT  (stateless FastAPI, horizontally scaled)                    │
   │                                                                           │
   │  API surface ── Working-Set Service ── Access Control ── Audit            │
   │        │                │                                                 │
   │  Job orchestration: ingest → extract → resolve → load → score            │
   └───┬──────────────┬──────────────┬───────────────┬────────────────────────┘
       │ GraphPort    │ AnalyticsPort│ ComputePort   │ ModelPort
   ┌───┴──────────────┴──────────────┴───────────────┴────────────────────────┐
   │  THE VAULT                                                                │
   │  Graph store      Columnar OLAP     Graph compute      Model serving      │
   │  ArcadeDB /       DuckDB /          graphology /       LiteLLM →          │
   │  JanusGraph       ClickHouse        rustworkx /        Ollama / vLLM      │
   │                                     GraphFrames        + Whisper + VLM    │
   │  Working-set cache: Valkey     Object store: MinIO     Index: OpenSearch  │
   └───────────────────────────────────────────────────────────────────────────┘
```

Everything between tiers crosses a named port. Nothing else does.

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

Swapping the default at implementation time is three actions on the admin console's Geospatial
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

**Implemented in Phase 2** as Knowledge Adapters — `coordinate_lon`/`coordinate_lat` for a bare
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

## 2. The four ports

These are the swap boundaries. Each is a Python `Protocol` in `packages/ports/`, each has a
conformance test suite in `tests/conformance/`, and a component is only supported if it passes
its suite. Adding a new backend means writing an adapter and turning the suite green — no
changes above the port.

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

**Gremlin never leaves the Vault.** The Conduit builds Gremlin; the Glass never sees it and
never sends it. This is what makes a future move to SQL/PGQ or openCypher an adapter change
rather than a frontend rewrite. It is also the security boundary: an analyst cannot author a
traversal that bypasses the access filter (§5).

**`GraphPort` grew beyond this illustrative snippet from Phase 1 on** — transactions and schema
management first, then `find_node` and `revert_elements` in Phase 2, without re-litigating the
snippet each time (`01_DOMAIN_MODEL.md` §8 records why: the doc never specified the request/
response shapes either, and a real adapter has to). Phase 2 also added
`get_node(..., include_superseded: bool = False)` and `supersede_node(node_id, replacement, tx)
-> NodeId`, closing a gap the schema already implied: `01_DOMAIN_MODEL.md` §2.4 requires a
correction to write a new revision and point the old one forward, and nothing before Phase 2
actually enforced that a superseded node stops appearing in ordinary reads. The workflows that
call it — Phase 6's retraction, Phase 8's judgement-review loop — land later; the capability
belongs on the port now, against the one adapter that exists, the same reasoning as `find_node`.
`supersede_node` also repoints every edge incident to the old node onto the new one (cloned, not
moved — confirmed empirically that ArcadeDB does not support relinking an edge's endpoints after
creation), so a correction cannot silently disconnect a node from its own network. `supersede_edge`
is the same operation for an edge: `01_DOMAIN_MODEL.md` §5's `Judgement.supporting`/`contradicting`
can cite an `EdgeId` directly, so an edge needs the same "corrected, not vanished" guarantee — it
has nothing to repoint, since nothing else in the domain model references an edge by id.

Supported adapters: `arcadedb`, `janusgraph`. Candidate: `hugegraph`.

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

Graph algorithms: centrality, community detection, the Clique Metric, shortest path at scale.
Separate from `GraphPort` because it has a different scaling profile — batch, memory-hungry,
tolerant of staleness — and a different deployment shape.

```python
class ComputePort(Protocol):
    async def centrality(self, req: CentralityRequest) -> dict[NodeId, float]: ...
    async def communities(self, req: CommunityRequest) -> dict[NodeId, CommunityId]: ...
    async def clique_metric(self, req: CliqueMetricRequest) -> dict[NodeId, CliqueScore]: ...
    async def shortest_paths(self, req: PathRequest) -> list[Path]: ...
    async def temporal_motifs(self, req: MotifRequest) -> list[MotifMatch]: ...
```

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
`litellm-config.yaml`. Changing the extraction model is a YAML edit and a restart of one
container.

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
- Redaction is not deletion: a filtered node is absent from the result, and the count is
  reported as filtered so the analyst knows the picture is incomplete. Showing a confident but
  partial network without saying so is worse than showing nothing.
- Every read, expansion, query and export is written to an append-only audit stream with
  principal, timestamp, query, result cardinality and justification string. The justification
  is a required field on any expansion that crosses a handling boundary.

## 6. Repository layout

```
ospreyflow/
├── apps/
│   └── workspace/              # The Glass. React + TS + Vite
│       ├── src/canvas/         # Sigma renderer, programs, interaction
│       ├── src/timeline/       # Temporal view
│       ├── src/map/            # MapLibre view
│       ├── src/dossier/        # Object explorer / entity detail
│       ├── src/workingset/     # graphology store, delta protocol client
│       └── src/design/         # tokens.css, primitives
├── services/
│   ├── api/                    # The Conduit. FastAPI
│   ├── ingest/                 # Connectors, normalisation, Knowledge Adapters
│   ├── extract/                # Multimodal extraction workers
│   ├── resolve/                # Splink entity resolution
│   └── compute/                # ComputePort workers (rustworkx / Spark submit)
├── packages/
│   ├── ports/                  # Protocol definitions — the architecture
│   ├── adapters/
│   │   ├── graph_arcadedb/
│   │   ├── graph_janusgraph/
│   │   ├── analytics_duckdb/
│   │   ├── analytics_clickhouse/
│   │   ├── compute_rustworkx/
│   │   ├── compute_spark/
│   │   └── model_litellm/
│   ├── ontology/               # Schema definition, migrations, validation
│   └── schemas/                # Shared Pydantic + generated TypeScript types
├── harness/                    # Browser setup harness and admin console; headless CLI
├── deploy/
│   ├── compose/                # Generated compose files per profile
│   └── cluster/                # Generated Kubernetes manifests
├── tests/
│   ├── conformance/            # Port conformance suites
│   ├── golden/                 # Extraction golden sets
│   └── scenarios/              # Acceptance scenarios A and B
└── docs/                       # This spec pack, kept in-repo
```

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

Fonts: Atkinson Hyperlegible Next and IBM Plex Mono are both SIL OFL 1.1. Self-host them; do not
load from a CDN — an air-gapped deployment must render correctly.

`make licence-check` runs `pip-licenses` and `license-checker` against the allowlist and fails
on any addition. Run it in CI on every pull request, not nightly.

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
- **No mobile client.** The workspace targets a desktop analyst at ≥ 1440px. Responsive down to
  1024px for review, not for analysis.
