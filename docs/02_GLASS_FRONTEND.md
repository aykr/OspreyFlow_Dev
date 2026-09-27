# 02 — The Glass (Frontend)

## 1. Stack

| Concern | Choice | Licence | Why |
| --- | --- | --- | --- |
| Framework | React 18 + TypeScript, Vite | MIT | Largest pool of maintainers; the requirement is a long-lived platform, not a clever one |
| Graph data model | graphology | MIT | Typed graph structure, and its algorithm packages give the browser compute tier for free |
| Graph rendering | **Sigma.js v3** (WebGL) | MIT | See ADR-002. Scale ceiling is the binding constraint |
| Map | **MapLibre GL JS** | BSD-3 | Vector tiles, offline tile support, and `@sigma/layer-maplibre` projects the graph onto it |
| Charts | Apache ECharts | Apache-2.0 | Histograms and timeline density; canvas-rendered, handles the row counts |
| Tables | TanStack Table (headless) | MIT | Virtualised; styling stays ours |
| State | Zustand + Immer | MIT | The working set is one store; avoid a framework that fights a 50k-node object |
| Data fetching | TanStack Query | MIT | |
| Worker orchestration | Comlink | Apache-2.0 | Layout and metrics run off the main thread |

No component library. The design system in `design/tokens.css` is specific enough that a generic
kit would be fought rather than used. Build the twenty primitives listed in §8.

### Why Sigma.js rather than Cytoscape.js

Both the research brief and the Gemini specification nominate Cytoscape.js, with the Gemini
version adding a WebGL "fallback" that transitions to Sigma.js above 10,000 nodes.

Shipping two renderers is the problem. Every node state in the design system — nine channels,
three provenance strokes, six interaction states, dimming by oklab mix — would need two
implementations that must agree pixel-for-pixel, or analysts will see the picture change when
they cross a threshold they cannot see. That is a permanent maintenance tax paid against the
maintainability constraint, and the failure mode is subtle rather than loud.

Pick one, and pick the one whose ceiling is higher. Sigma.js v3 renders via WebGL with
graphology as the data layer; the practical ceiling is in the hundreds of thousands of nodes
where Cytoscape's canvas renderer degrades around ten thousand. The 50k working-set cap sits
inside Sigma's comfortable range and outside Cytoscape's.

The cost is real and should be understood before the decision is accepted: custom node
rendering in Sigma means writing WebGL programs, where Cytoscape offers CSS-like styling. Three
things make that cost affordable here:

- The design system's node vocabulary is deliberately small — a fill from nine channels, one of
  a handful of shapes, and a stroke that varies in width and dash pattern. That is one
  parameterised program, not nine.
- Sigma v3 ships the plugins this design needs: `@sigma/node-border`, `@sigma/edge-curve`,
  `@sigma/node-image`, `@sigma/export-image`, `@sigma/layer-maplibre`.
- Labels, hover cards and context menus are DOM overlays positioned from Sigma's camera, not
  WebGL. The rich parts stay in HTML where they are easy.

Cytoscape.js remains a dependency for nothing. If a specific layout algorithm is wanted from its
ecosystem, port the algorithm, not the renderer.

### 1.1 Semantic zoom: cluster overview to individual link

Moving between the shape of the whole network and the detail of one relationship is the core
navigation of link analysis, so it is specified rather than left to the renderer's defaults.

The renderer choice does not compromise it. Zoom and pan is where WebGL is strongest — the camera
transform is a GPU uniform, so panning a 50,000-node set holds 60 fps where a canvas renderer is
re-rasterising every element on the CPU. The axis the analyst actually feels is smoothness at
scale, and that improves rather than degrades.

What produces the *semantic* behaviour — different information at different zoom levels — is not
a built-in on either library. It is `nodeReducer` and `edgeReducer`, functions Sigma calls per
element per frame, returning the display attributes for the current camera ratio. That is a
deliberate hook, and it gives finer control than a stylesheet would.

Four zoom bands, all driven from the reducers:

| Band | Camera | Nodes | Edges | Labels |
| --- | --- | --- | --- | --- |
| **Overview** | zoomed out | Community hulls drawn; nodes at minimum radius | Only above the strength filter; aggregated between hulls | None |
| **Structure** | mid | Full channel fill and shape | All edges, width by weight | Top-degree nodes only |
| **Neighbourhood** | in | Full node vocabulary, all six states | Directional arrows, curved parallel edges via `@sigma/edge-curve` | All node labels |
| **Link detail** | closest | Node labels plus key properties | Per-edge label: type, occurrence count, interval | Edge labels on |

Three rules that make the transitions usable rather than jarring:

- **Nothing appears or disappears abruptly.** Labels and edges fade across a band boundary rather
  than popping, and the thresholds are set so that a band change never coincides with the
  natural resting zoom of a common layout.
- **Zoom never changes what exists, only what is drawn.** An edge hidden at Overview is still in
  the working set, still counted in the status bar, still selectable by search. Zoom is not a
  filter, and the two must never be confused — a filter dims and reports; zoom just draws less.
- **`hideEdgesOnMove` during interaction, never at rest.** Dropping edges while the camera is
  moving is what buys the frame budget at 250,000 edges. They return the moment the camera
  settles.

Inspecting one link does not depend on the canvas at all. Hovering or selecting an edge opens a
DOM overlay anchored to Sigma's camera showing the edge's type, occurrence count, interval,
provenance and contributing source records. Rich per-edge decoration is the one area where WebGL
is genuinely more awkward than a CSS-styled canvas — multi-line edge labels and badges are hard
in a shader — and the overlay is the answer: it applies to the one or two edges under attention,
where HTML is easy and cheap, rather than to all 250,000.

**Zoom-dependent clustering is a data operation, not a rendering one.** Collapsing a community
into a meta-node, or expanding it back, happens in graphology and produces a real change to the
working set with an entry in the step history. It behaves identically whichever renderer draws
it, so it was never part of this decision.

**Resolution clustering is a separate, unrelated sense of "cluster," and neither this document nor
the Inspector's own tab list (§2) named a rendering convention for it before Phase 6a — recorded
here, retroactively for Stage 2 and directly for Stage 3, rather than left implicit in
`07_BUILD_PLAN.md`'s own narrative.** A community (above) is a Louvain/analytics grouping
(`06_DECISIONS.md` ADR-029 — Leiden is unavailable on either compute tier), rendered as a
translucent hull. A resolution cluster (`Node.resolution.cluster_id`, `01_DOMAIN_MODEL.md`
§4) is the query-time collapse of `SAME_AS` edges scoring above the session's τ — a different axis
entirely, and the two must never share a visual channel or an analyst could not tell which kind of
grouping they were looking at.

*Collapse (Stage 2, B9).* Every node sharing a `cluster_id` with at least one other co-locates at
the cluster's own anchor position and gains a second, independent `@sigma/node-border` ring (never
the same attribute the interaction-state ring — on-path/selected/hover — already owns, so both can
show on one node at once). A node whose cluster splits back apart returns to its own deterministic
scatter position rather than staying wherever a previous merge left it. This is the picture the
threshold control's own change-summary counts (`merged`/`split`/`affected`) must agree with.

*Explanation (Stage 3, B10).* `GET .../resolution/explain/{cluster_id}` — the per-comparison match
weights behind a cluster — renders in a transient `Popover` overlay anchored to the triggering
canvas position, the same shape edge inspection (above) already uses, opened from a cluster-aware
item in the existing radial menu. Not an Inspector tab (none is named "Resolution," and inventing
one pre-empts the Dossier, B6/Stage 4's own, larger, permanent surface for exactly this class of
content) and not a modal. A row is omitted, never shown redacted, if the render cannot independently
confirm both endpoints of a pairwise comparison from the response's own `member_node_ids` and this
session's already-access-controlled local graph — belt and braces against a node id the API
technically cleared but this client has not yet synced, or against a future regression, not a
claim that the API itself is untrusted.

*Highlighting (Stage 4, B6).* This document had no rendering convention for message-span
highlighting before Stage 4 — recorded here directly, not left implicit. A highlighted span never
gets a solid channel fill behind its text: that is exactly what would risk the contrast floor over
dense prose, so instead it reuses the same "8% channel opacity" convention already specified for
the community-hull overlay above (§3.2), composed via CSS `color-mix()` against the entity's own
channel token rather than a solid background — theme-aware for free, since it mixes against the
already theme-aware surface a span sits on rather than computing a fixed colour once. Text colour
is never touched, so a highlighted run introduces no new foreground/background pairing for
axe-core's contrast check to evaluate at all; the only new visual element is the run's own
underline, reusing the canvas's existing solid/dashed `provenanceStroke` distinction (asserted/
inferred) rather than a second visual language for the same fact. As with the explain-cluster row
above, a span naming a node the requesting principal cannot see is never returned by the Conduit
in the first place (`03_CONDUIT_MIDDLEWARE.md` §3.6) — omitted, not rendered redacted — so the
Dossier itself needs no separate leak-defense filter the way `visiblePairs` gives the explain
overlay one; there is nothing to filter client-side because the array it receives is already
narrowed.

## 2. Workspace layout

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ ⬛ Case 4471 — layering            [ Search entities, identifiers, documents  ⌘K ] │
│                                              Resolution: ●Balanced   Export  ⚙   │
├──────────┬────────────────────────────────────────────────┬──────────────────────┤
│ FILTERS  │  CANVAS                              [⊞ ⊙ ⌖ ⧉] │ INSPECTOR            │
│          │                                                │                      │
│ Entity   │   The working set, one view at a time:          │ ▸ Properties         │
│  type ▤  │   Graph · Map · Matrix                          │ ▸ Provenance         │
│ Time  ▤  │                                                │ ▸ Relationships      │
│ Source▤  │   Selection drives the inspector.               │ ▸ Judgements         │
│ Strength │   Every filter on the left dims, never removes. │ ▸ Source document    │
│  ▬▬●▬▬   │                                                │                      │
│ Degree   │                                                │ [Confirm] [Split]    │
│  ▬●▬▬▬   │                                                │                      │
│          ├────────────────────────────────────────────────┤                      │
│ Handling │  TIMELINE  ▏▁▃▅█▇▃▁▁▂▅█▆▂▁▁▁▃▇█▅▂▁              │                      │
│  ▤       │  ├────[═══ brush ═══]──────────────────────┤    │                      │
│          │  Mon Tue Wed Thu Fri Sat Sun   ◂ play ▸ 1×      │                      │
├──────────┴────────────────────────────────────────────────┴──────────────────────┤
│ 12,481 nodes · 38,902 edges · 214 dimmed by filter · 6 hidden by handling ⓘ       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Four rules govern this layout, and they are what make it an analytical workspace rather than a
set of widgets:

1. **One working set, many views.** Graph, Map and Matrix are three renderings of the same
   graphology instance. Switching view never refetches and never loses selection.
2. **Filters dim, they do not remove.** A filtered node stays in place at 12% channel mix with
   its label dropped. Removing nodes destroys the analyst's spatial memory of the network, which
   is most of what they are actually using to navigate.
3. **Everything cross-filters.** A brush on the timeline dims the graph, restricts the map and
   recomputes the histograms. A lasso on the canvas filters the timeline. A histogram bar click
   filters everything. This is the Gotham pattern and it is the core interaction of the product.
4. **The status bar never lies.** Counts of dimmed and handling-hidden items are always visible.
   An analyst must never be able to mistake a filtered picture for a complete one.
5. **The signed-in principal's own identity is always visible, informationally only.** A small
   element in the top-bar chrome, beside `History` — `<subject> · <clearance>` (e.g.
   `analyst-1 · OFFICIAL`), with a `Sign out` control beside it. Added by `06_DECISIONS.md`
   ADR-050, whose own objection 9 found this document silent on the element its design put here;
   this is that gap closed, not a decision made only in the ADR. Rule 3 stands unchanged: the
   Glass reads `sub` and `clearance` from the signed token and displays them, and derives nothing
   from either — a principal with a lower clearance sees exactly the same controls, differing only
   in what the Conduit itself returns. `Sign out` ends the session at the identity provider
   (`end_session_endpoint`) and clears the Glass's own memory and session storage; it does not
   itself alter what any control shows.

### 2.1 Investigation selection on load — proposed, not settled spec

**Found during Stage 3a's own rehearsal, 23 September 2026 — this document was silent on the
question, checked directly, not assumed.** Before this proposal, the Glass created its own
investigation via `POST /v1/investigations` on every load, unconditionally — an operator who had
already created and seeded an investigation via the API (`DEMO_GUIDE.md` §3.3–3.4) saw an empty
working set, because the Glass never looked at what already existed. The only way to point the
Glass at a specific investigation was to open the browser console and set
`sessionStorage["ospreyflow.investigationId"]` by hand before reloading.

**The minimal fix, implemented, pending the owner's acceptance as spec:** on load, the Glass
resolves an investigation id in this order —

1. a `?investigation=<id>` query parameter on the page URL, if present;
2. otherwise, `sessionStorage["ospreyflow.investigationId"]`, if a prior load in this browser tab
   set one;
3. otherwise, `POST /v1/investigations` creates a new one, exactly as before.

Whichever id resolves is written back to `sessionStorage` immediately, so a reload of the plain
URL (no query parameter) still finds the same investigation rather than falling through to
create a second one. This closes the gap with the smallest change that removes the manual
`sessionStorage` step — it does not validate the URL-supplied id against `GET
/v1/investigations/{id}` before use (an invalid or unauthorised id surfaces however the first
investigation-scoped request already reports that failure today, not as a special case here).

**What is not decided by this proposal:** whether the Glass should instead show an
investigation-picker screen, whether an invalid URL id should have its own dedicated error state,
and whether the query parameter should survive into the URL the Glass itself sets during
navigation (it does not today — this is load-time resolution only, not a routing scheme). Left
for the owner to accept, amend or reject as real spec.

## 3. The five analytical capabilities

### 3.1 Network analysis

| Requirement | Implementation |
| --- | --- |
| Expand a node's relationships | Radial context menu on right-click; items generated from the ontology's edge types valid for the node's type, each with a live count |
| Search Around | Multi-step, filtered traversal builder — `Person → uses → Endpoint → communicated with (≥5 events, in brush window) → Endpoint → used by → Person`. Preview count before committing to the canvas |
| Pathfinder | Select two nodes, get k-shortest paths; paths render with the on-path node state (2px primary stroke, edges thickened), everything else dims to 32% |
| Subgraph isolation | Lasso or bounding box, then "Branch to new tab" — the selection opens as a new working set with its own filter state; the parent is untouched |
| Undo | Every canvas mutation is a step in an addressable history; the history panel is a list of named steps, not a stack of arrows |

**Expansion budget.** Every expansion previews its cardinality before executing. Above 500 new
nodes the action requires a filter or an explicit acknowledgement. This single control is what
stops an analyst turning a legible network into a hairball in one click, and it is the most
common complaint about link analysis tools.

### 3.2 Social network analysis

Metrics panel, computed on the working set in a Web Worker, recomputed on filter change:

- Degree, weighted degree
- Betweenness (exact to 20k nodes, Brandes-sampled above)
- Eigenvector / PageRank
- Local clustering coefficient
- **Clique Metric** (defined in `01_DOMAIN_MODEL.md` §6.2)
- Community assignment (Louvain, connected-components split — `06_DECISIONS.md` ADR-029)

Each metric is applied to the canvas as **size**, never as colour — colour is reserved for
entity type. The sequential ramp from the design system is available for a heatmap overlay when
the analyst explicitly asks for one, and it is monotonic in lightness so a greyscale print of the
chart still reads.

The metric panel is a ranked list, not a chart. Clicking a row selects and centres that node.
Two metrics can be shown side by side, which is how the Clique Metric earns its keep — the
insight is "high clique score, low degree centrality", and that comparison has to be visible in
one glance.

Community detection produces a **hull overlay**, not a recolour: a translucent boundary drawn
around each community at 8% channel opacity, labelled with size and dominant entity type.
Recolouring nodes by community would collide with the entity-type channel and break the one rule
the design system will not bend.

### 3.3 Pattern analysis

Three mechanisms, in increasing order of power:

**Visual query builder.** A node-and-edge pattern the analyst composes — an entity-type palette
places a node, search pins one to an already-known entity, a connect control joins two with an
edge — with per-element constraints, compiled to Gremlin in the Conduit. **Not a second drawing
canvas** (`06_DECISIONS.md` ADR-032, Phase 7 Stage 4, correcting this bullet's own earlier
"draws"): a list/palette editor built from the same native controls as every other panel, chosen
because the pattern shapes ADR-030's own compiler can express are small enough to read as a list,
and because a canvas inherits every accessibility problem `GlassCanvas` has already needed fixing
once (that ADR's own reasoning). Never expose the Gremlin; do show the estimated result count
before running, principal-filtered exactly like the result itself will be, never a raw or
unfiltered figure (`CLAUDE.md` rules 3 and 7). **Patterns are saveable, shareable and versioned**
is this bullet's own unbuilt promise — Stage 4 built compose/preview/run only; see
`07_BUILD_PLAN.md`'s Phase 7 known-gaps list.

**Hotlists and watchlists.** A list of identifiers with an owner and a review date. Any ingest
that touches a listed identifier raises an alert. The CoLP journey turns on exactly this — a SIM
seized in a warrant matches a number already logged, and an officer is notified. Alerts carry
the matched identifier, the triggering document, and a one-click jump into a pre-populated
investigation.

**Saved-pattern monitors.** A saved visual query run on a schedule against new data. Matches
raise alerts with the same shape as hotlist alerts. This is the CoLP deck's "automatic daily
searches" requirement.

Every alert names the rule that fired and shows the evidence. Borrowing from the way fraud
decisioning products present their scores: an alert that cannot explain itself is an alert the
analyst will learn to dismiss.

### 3.4 Temporal analysis

The timeline is the second most important control in the product after the canvas.

- **Density strip** — event counts per bucket, bucketed automatically to the window, drawn from
  the analytics store not the graph.
- **Brush** — drag to select a window; the graph dims everything outside it, the map restricts
  to it, the histograms recompute. Brush endpoints are editable as text.
- **Playback** — animate the brush forward at 0.5× to 8×. Nodes interpolate position and never
  cross-fade, so identity is continuous through a re-layout. The design system fixes the
  interpolation at 420ms with a dedicated easing curve. **A base duration for "1×" was left
  unstated here — a real spec gap, found and closed while building Stage 4f
  (`07_BUILD_PLAN.md`): a full traverse of the brush window at 1× takes 8 real seconds**
  (`playback/math.ts`'s own `PLAYBACK_DURATION_MS_AT_1X`), chosen as long enough to read a dense
  timeline's own movement and short enough not to feel stalled at 0.5× (4s) or rushed at 8× (1s).
- **Cyclical view** — the HMP analysis is a day-of-week and hour-of-day analysis, and a linear
  timeline cannot show that. Provide a second mode that folds the window into a weekday × hour
  grid with counts, which is the same finding the source report reached with a polar plot.
- **Multi-track mode** — one row per selected entity, events as marks. This is how a
  relay-and-cut-out pattern becomes visible: two endpoints that never overlap in time.
- **Cross-case overlay** — events from a second investigation on a distinct track, for linking
  independent cases on shared timestamps or identifiers.

Under `prefers-reduced-motion`, playback becomes stepped and re-layout becomes an instant move
with a persistent control that shows previous positions. Removing the animation removes the only
cue for what moved, so something must replace it.

### 3.5 Geospatial analysis

MapLibre GL JS with `@sigma/layer-maplibre`, so the graph draws over the map in the same
projection and a node with coordinates sits where it belongs.

| Capability | Implementation |
| --- | --- |
| Point and cluster plotting | Supercluster; clusters expand on zoom |
| Heat map | Density layer from `AnalyticsPort.geo_bins`, server-side binned — never ship a million points to the client |
| Snail trail | Ordered sighting track for one entity over the brush window, animated with playback |
| Convoy analysis | Two or more entities co-located within a distance and time tolerance; tolerances are user-set and shown |
| Incident comparison | Two or more geo-temporal windows side by side, sharing a colour ramp |
| Site geospatial | A georeferenced floor plan or aerial image as a raster layer with a drawn grid, for fixed-site analysis |
| Basemap switching | Layer control listing every provider declared in `osprey.yaml`; attribution and any licence note render with the map and on every export |
| Gazetteer search | Place and address lookup against the locally ingested gazetteer; no hosted geocoder is ever called |
| Boundary layers | Administrative, postcode and jurisdiction geometry as toggleable overlays; a drawn or selected boundary is a spatial filter like any other |
| Offline tiles | PMTiles from a local file or a local tile server; no network call in an air-gapped deployment |

Provider configuration is in `00_ARCHITECTURE.md` §1.2. The map component reads the registry and
renders whatever kinds are declared — `vector`, `raster`, `image`, `dem` — with no per-provider
code. Adding a force's corporate WMTS service is a `osprey.yaml` entry.

**Site geospatial is not an afterthought.** The HMP analysis is an aerial photograph of a single
site with a superimposed grid, and half the finding is "these four yards, adjacent to this
wing." A platform that only does street-map geocoding cannot do prison, campus, port, airport or
stadium analysis. Support an uploaded image with two or more control points and a drawn grid,
and let a `Location` entity be a grid cell.

**Which tier serves a tier-1/2 local PMTiles source over HTTP — proposed, not settled spec.**
Found during Stage 3a's own rehearsal, 23 September 2026: neither this section's "Offline tiles"
row above nor `05_DEPLOYMENT.md` §2.2 names which component actually puts a tier-1/2 local
`source` on the wire to the browser (checked directly, not assumed silent) — `osprey.yaml`'s own
`source: file:///data/tiles/osm-local.pmtiles` is an on-disk path, and a browser cannot fetch a
`file://` URI at all, so the map view rendered blank the moment a real basemap build existed to
try. The fix implemented pending the owner's acceptance: the Conduit serves it, at `GET
/v1/map/local-source/{provider_id}` (`services/api/app.py`), the smallest correct option given
`05_DEPLOYMENT.md` §2.4's own guard table — the Conduit is already the one exposed service
serving `/v1/map/providers` and the tier-3/4 tile proxy, so this is a third sibling route, not a
new exposed surface. `mapconfig_loader.public_view()` rewrites a `file://` source to this route
rather than handing the Glass the raw path; the route answers a ranged `GET` (PMTiles' own access
pattern — the client reads its own directory and tile blocks via byte ranges against the single
file, never downloading it whole) and 404s with a named `detail` when the file has not been
built. The Glass runs a preflight check against this route before mounting the map
(`apps/workspace/src/map/basemapAvailability.ts`) and shows "Basemap not built" with the route's
own detail message in place of a blank canvas when it 404s.

**What is not decided by this proposal:** whether a `local-lite`/`small`/`cluster` deployment
profile should instead serve the file from a dedicated static-file sidecar rather than the
Conduit itself (a real question once this is more than a single-file demo case), and whether the
same route should also serve a tier-2 OS OpenData PMTiles build once one exists (nothing about
this fix is tier-1-specific — a tier-2 provider's own `source` is rewritten by the same `file://`
check in `public_view()` — but no tier-2 provider ships today to exercise it against). Left for
the owner to accept, amend or reject as real spec.

## 4. Design system binding

`design/tokens.css` is authoritative and is extracted verbatim from the brand foundations. Do not
introduce a colour that is not a token. Three rules carry most of the weight:

**Colour is data.** The chrome is a twelve-step neutral ramp at chroma 0.005. One accent, brass,
carries primary actions, focus and selection, and its hue band is struck out of the data palette.
Everything else you see in colour is information.

**Hue is entity type; shape is entity type too.** Nine channels, each paired with a shape, so hue
never carries a distinction on its own. Protanopia and deuteranopia separation holds above ΔE 20;
tritanopia does not and cannot at nine hues, which is why shape and label pairing is the
mitigation and is not optional.

**Provenance is stroke; state is mix.** Asserted is solid, inferred is dashed, unresolved is
dotted. Dimming mixes the channel toward the panel surface in oklab at 32%, filtered-out at 12%,
so a de-emphasised node still declares what it is.

Node state vocabulary, implemented once in the Sigma node program:

| State | Treatment |
| --- | --- |
| Default | channel fill, 1px subtle stroke |
| Hovered | 1.5px primary stroke |
| Selected | 2px brass stroke, 1px surface gap |
| On path | 2px primary stroke, incident edges thickened |
| Dimmed | 32% channel toward panel |
| Filtered out | 12% channel, label dropped |
| Asserted | 1px border-strong |
| Inferred | 1.5px dashed 4-2, channel colour |
| Unresolved | 1.5px dotted, channel colour |

**Selected and on-path, combined — resolved here rather than left as a disclosed gap
(`07_BUILD_PLAN.md`'s own Phase 8 entry had recorded the finding, not the fix).** Selected and
on-path are both a 2px stroke, and the code that first implemented them differentiated a
select-and-on-path node from a selected-only one by stroke hue alone — a colour-only distinction,
WCAG 1.4.1, for that one combination. Both states already carry their own non-colour cue in the
table above — the 1px surface gap (selected) and the thickened incident edges (on-path) — so the
fix asks nothing new of the palette: **the two cues are independent and both apply when both
states hold.** A selected node on the active path shows the surface gap *and* thickened incident
edges together; stroke hue is decorative reinforcement in that combined case, never the only
signal distinguishing it from a selected-but-off-path node. Binding on both states, not a choice
between them — the "which state owns the non-colour channel" question the disclosed gap left open
is answered: both, via the channel each already had.

Dark is the working default. Light is a separately tuned ramp, not an inversion, and exists for
screenshots pasted into reports and for print. Both meet the same contrast floor. An exported
chart destined for an intelligence product should default to light.

Type: Atkinson Hyperlegible Next for interface, IBM Plex Mono for literal values and every
tabular figure. The reason is operational, not aesthetic — analysts read identifiers all day and
a confusable `1 l I` or `0 O` is a real error. Every identifier, hash, timestamp and account
number in the product is set in mono. Mono means "this is a value you can copy."

### 4.1 Error surfacing

A client-side call that fails must never be dropped silently — the working set's own binding
requirement (`06_DECISIONS.md`, standing rule 2) extended to every surface that issues a request,
not only the canvas. Two patterns, not one, because the two classes of surface that issue a
request are not interchangeable:

- **`ActionErrorOverlay` — canvas-anchored.** A `Popover` positioned at the `x`/`y` of the
  cursor or selection that triggered the failed action (`manualAssertion`, `expandNode`,
  `explainCluster`, the pathfinder's own error state), Escape-dismissed like every other canvas
  overlay. Applies where the failure is a consequence of a specific point on the canvas the
  analyst was just looking at — the overlay's own position is part of what makes the failure
  legible, tying it back to the node, edge or selection it came from.
- **The panel inline banner — non-canvas surfaces.** A plain `error` state rendered as a
  `role="alert"` paragraph inside the panel itself (`QueryBuilderPanel`'s own precedent, reused
  by the hotlist/monitor/alert-inbox panels), not positioned relative to anything on the canvas.
  Applies to every ordinary form-and-list panel beside the canvas — there is no cursor position or
  selected element for the failure to anchor to, and forcing an `x`/`y` popover onto a surface with
  neither would need an invented anchor point the failure has no real relationship to.

Both satisfy the same requirement — a thrown client call is always visible, never swallowed — by
the mechanism proper to where the request was issued from, not by one component doing double duty
across two different kinds of surface.

## 5. Performance budget

Measured on a 2021-class laptop, integrated graphics, against a 50k-node / 250k-edge working
set. These are pass/fail gates in CI, not aspirations.

| Interaction | Budget |
| --- | --- |
| Initial working-set render | < 2.5 s to first interactive frame |
| Pan / zoom | 60 fps sustained |
| Timeline brush drag | 30 fps minimum, filter applied within one frame of release |
| Node hover to inspector populated | < 100 ms |
| Expansion of ≤ 500 nodes | < 800 ms end to end |
| Layout run (ForceAtlas2, 50k) | Off main thread; main thread never blocked > 16 ms |
| Metric recompute on filter change | < 500 ms for ≤ 20k, otherwise progressive with a visible indicator |

Techniques that are required rather than optional: layout and metrics in Web Workers via
Comlink; label rendering only above a zoom threshold and only for nodes above a degree
threshold; edge rendering with level-of-detail so that below a zoom threshold only edges above
the strength filter draw; the working set streamed as deltas so the first meaningful frame does
not wait for the whole payload.

## 6. Accessibility floor

Not negotiable and cheaper to build in than to retrofit.

- Every canvas action reachable by keyboard. Tab and Shift+Tab move focus in and out of the
  canvas exactly like every other control on the page — corrected in Phase 7 Stage 4 (a
  container that instead captures every Tab keydown once it holds focus traps a keyboard user
  inside it for good, found once a second keyboard-driven surface sat beside the canvas). Reaching
  the canvas by any means (Tab, a click, `.focus()`) with nothing selected establishes a one-node
  ring immediately, with no keypress needed after arriving. `Ctrl`/`Cmd`+`ArrowRight`/`Left`
  cycles the focused node through an already-built ring (needed for a lasso-selected set of
  non-adjacent nodes plain arrow-walk cannot reach); plain arrow keys walk edges, moving focus
  only, never the ring itself; `Enter` expands; `\` opens the radial menu as a list; `Space`
  toggles the focused node's own membership in the selection ring (`07_BUILD_PLAN.md` Phase 6a
  Stage 1: added for manual link/split, the first action needing a keyboard-built multi-node
  selection at all). **`Ctrl`/`Cmd`+`Shift`+`ArrowRight`/`Left` walks every node in the working
  set, adjacency or not** — added 27 September 2026 (round 12d) after a real gap was found
  against this very bullet: `Explain cluster` and `Find paths to` are both gated on a *two-node*
  selection, and until this binding existed no keyboard route built one for two nodes that share
  no edge. Plain arrow-walk follows edges so it cannot leave a component; `Ctrl`/`Cmd`+Arrow
  cycles only within the existing ring; `Space` toggles only what is focused. Two entities found
  by identifier — how an analyst reaches them — are exactly that case, so both actions were
  mouse-only in practice while the keyboard registry recorded them as covered. Proven by
  `apps/workspace/keyboard/keyboard.spec.ts`'s own "Ctrl+Shift+Arrow reaches a node arrow-walk
  cannot" case, over a deliberately disconnected fixture node.
- The canvas exposes an accessible alternative view — the Matrix view is not a novelty, it is
  the screen-reader-navigable rendering of the same data.
- Focus is a 2px brass outline at 2px offset, everywhere, never suppressed.
- All nine channels paired with shape; colour never sole carrier.
- `prefers-reduced-motion` honoured as described in §3.4.
- Contrast floor met in both themes; verify with automated checks in CI, not by eye.

## 7. Copy rules

The interface's words are part of the design.

- Name things as an analyst names them: "Add to investigation", not "Persist entity".
- An action keeps its name through the flow. The button that says "Confirm" produces "Confirmed."
- Errors say what happened and what to do: "Query timed out at 30s. Narrow the date range."
  Not "An error occurred."
- Degraded states are explicit: "Partial result: 2 of 9 sources offline."
- Never use a confidence word loosely. "Likely" in this product means the configured probability
  band, and appears only where a band has been set.

## 8. Component inventory

Twenty primitives, built once, in `src/design/`:

`Button` · `IconButton` · `Input` · `Select` · `Combobox` · `Slider` · `RangeSlider` ·
`Checkbox` · `RadioGroup` · `Toggle` · `Tabs` · `Panel` · `Drawer` · `Popover` · `Tooltip` ·
`ContextMenu` · `RadialMenu` · `Table` · `Histogram` · `Toast`

Docked panels get a hairline and no shadow; overlays get a shadow and no hairline. Never both.
Radii: 0 for canvas and cells, 2px controls, 4px panels, 6px overlays, 999px status chips.

## 9. Assessment production

The HMP report is the model this platform exists to produce: a set of judgements, each resting on
named evidence, plus explicit gaps and assumptions (`01_DOMAIN_MODEL.md` §5). "Judgements" has
been named as one of the Inspector's five tabs (§2) since Phase 4; this section is the first place
that names what the tab actually contains.

### 9.1 The Judgements tab

A `Table` (§8; headless, per §1's TanStack Table choice) listing every judgement in the current
investigation: statement (truncated), probability band, evidence count, author. Selecting a row
opens a `Drawer` (§8) holding the full authoring surface below. Gaps and assumptions get their own
`Tabs` (§8) panes within the same Drawer, not separate top-level Inspector tabs — all three are one
assessment surface, and splitting them across the Inspector's own limited tab budget would scatter
a single analytical object across three places.

**Judgement authoring.** Statement (`Input`, multi-line); probability band via `Select`, populated
from the active deployment's yardstick file (§9.3); an evidence picker drawing from the current
canvas selection or `Combobox` search, split into `supporting`/`contradicting`
(`01_DOMAIN_MODEL.md` §5's own field names). **A judgement cannot be saved with zero supporting
references** — A13's own literal assertion — so the `Save` `Button` is disabled, not merely
validated on submit, until at least one evidence item is attached: the constraint is visible
before the analyst attempts to save, per §7's own copy-rule discipline of saying what will happen
rather than erroring after the fact.

**Gap authoring.** Question (`Input`); linked entities via multi-select from the canvas selection;
status via `Select` (`open`/`tasked`/`answered`/`closed`, `01_DOMAIN_MODEL.md` §5's
`IntelligenceGap.status`).

**Assumption authoring.** Statement (`Input`); `if_false_impact` (`Input`, free text — the
domain model's own field, carried through verbatim rather than renamed for the UI); linked
judgements via multi-select against the investigation's own judgement list.

### 9.2 Bidirectional evidence highlighting

- **Selecting a judgement highlights its own `supporting`/`contradicting` items on the canvas —
  built as the *selected* node state (`GlassCanvasHandle.highlightNodes`), not the "8% channel
  opacity" overlay this section originally specified.** Corrected here rather than left
  contradicting the shipped build (Phase 8 Stage 4c): the opacity convention is a per-*region*
  hull polygon or a per-*text-span* background, neither of which has a per-*node* shape — building
  one would be a new WebGL node-program visual channel, real rendering-engine work Stage 4c was
  not scoped for. Reusing the existing multi-node *selected* state (already real, via lasso) needs
  no new channel and reaches the same practical goal — "this is relevant" — at the cost of not
  being visually distinct from an analyst's own manual selection while a judgement's evidence is
  highlighted. `GlassCanvasHandle.highlightNodes`'s own docstring has the full record.
- Selecting a node lists, in the Judgements tab, every judgement resting on it —
  `01_DOMAIN_MODEL.md` §5's own "selecting a node lists the judgements that rest on it," given a
  concrete surface for the first time.
- **A judgement is hidden from the Judgements tab in full, not shown with a citation marked
  unavailable, when the viewing principal's access does not cover at least one of its own
  `supporting` references** — `06_DECISIONS.md` ADR-046's own decision: a conclusion a viewer
  cannot verify is an unsupported assertion wearing the same formatting as a supported one, and
  displaying it invites the deference the evidence-link requirement exists to prevent. An
  unreadable `contradicting` reference does not hide the judgement; it renders a distinct
  review-flag chip (§9.4) instead, since a fuller-access reviewer should know a counter-
  consideration existed that this viewer could not see.

### 9.3 Yardstick display

The active deployment's yardstick (`01_DOMAIN_MODEL.md` §5, `ontology/yardstick/*.yaml`) renders as
a fixed reference strip inside the judgement authoring `Drawer` — band label and numeric range — so
an analyst chooses against the organisation's own configured scale, never one hardcoded into the
component. The band `Select`'s own options are generated from the loaded yardstick file; swapping
the file changes the options with no Glass code change, matching `01_DOMAIN_MODEL.md` §5's "a
revision is a config change."

### 9.4 Review flag

A judgement flagged for review (`01_DOMAIN_MODEL.md` §5 — triggered when a node it cites is split,
corrected or retracted) shows a status chip on its own row in the Judgements tab (the `999px`
status-chip radius §8 already specifies), and a corresponding marker on the flagging node if it is
currently on the canvas — the same list-row-plus-canvas-marker pairing the resolution-conflict
pattern (Phase 6a) already establishes for "something here needs a human's attention."

## 10. Export

The workspace layout (§2) already sketches an `Export ⚙` control in the top bar; this section gives
it its own surface. Three artefact shapes share one handling gate — there is one gate, not three.

### 10.1 Triggers

| Shape | Source | Format |
| --- | --- | --- |
| Chart | The current canvas (`@sigma/export-image`, §1) or a saved metric/histogram/timeline view (ECharts' own export) | PNG |
| Subgraph | The current working set, or a lassoed selection via the same "Branch to new tab" mechanism §3.1 already defines | JSON |
| Report | The investigation's assessment objects (§9), assembled with their own cited evidence — the artefact A15 itself names ("Export the chart and the assessment") | Self-contained HTML |

**File formats, recorded here rather than left undetermined.** This document named where each
shape's content comes from without ever stating what file it becomes — a real spec gap, found
while Stage 4h (`07_BUILD_PLAN.md`) gave the rendering pipeline an owning stage rather than
leaving it a placeholder. Decided, not merely disclosed as open:

- **Chart — PNG**, `@sigma/export-image`'s own native output for the canvas case; ECharts' own
  export for a histogram/timeline/metric view produces the same.
- **Subgraph — JSON**, the working set's own `Node`/`Edge` wire shape
  (`03_CONDUIT_MIDDLEWARE.md` §3.2's delta protocol already defines it, `model_dump(mode="json")`)
  — no new format invented; a subgraph export is a snapshot in the same shape the Glass already
  receives over the wire.
- **Report — a self-contained HTML document.** Judgement/gap/assumption content, cited evidence
  and the yardstick band render inline as prose, styled against `design/tokens.css`'s own light
  theme (§4's "an exported chart destined for an intelligence product should default to light,"
  extended here to the report as a whole). Chosen over a PDF pipeline deliberately: this build
  does not need to own a PDF-rendering dependency to produce "a document handed to someone" (`08_
  ACCEPTANCE_SCENARIOS.md`'s own framing of what A13–A15 exist to prove) — a single HTML file
  opens in any browser and is printable to PDF by the recipient, at their own discretion, with
  nothing lost from the source document in that conversion. **Revisit if** a recipient-side print
  step turns out to be an unacceptable hand-off in practice; the shape to build then is a real PDF
  pipeline, not assumed necessary now.

### 10.2 Handling gate

- Evaluates every node and edge in the selection against the handling scheme
  (`03_CONDUIT_MIDDLEWARE.md` §6: "`POST /export` evaluates every node and edge in the selection
  against the handling scheme").
- A blocked item renders in a named list inside the export `Drawer` — entity or edge label, its own
  blocking handling code (e.g. `S2`) — never a generic "export blocked" message: A15's own literal
  assertion is that blocking items are named, and §7's own copy rule ("Errors say what happened and
  what to do") applies here as much as anywhere else in the product.
- **Justification form.** Overriding a block requires a free-text justification (`Input`,
  multi-line) and an originator reference (`Input`), both recorded, per `03_CONDUIT_MIDDLEWARE.md`
  §6's "Override requires a justification and an originator reference, both recorded." The `Export`
  button stays disabled until both fields are non-empty — the same disabled-until-valid pattern
  §9.1's judgement `Save` button already uses.
- **A report export additionally walks every assessment object's own `supporting` citations, not
  only the canvas selection** — `06_DECISIONS.md` ADR-046's own decision, required rather than
  optional: a judgement citing evidence outside the *exporting analyst's own* access is refused and
  named in the same blocker list above, since no recheck against the eventual recipient's access is
  possible once the artefact has left the boundary (ADR-045).

### 10.3 Manifest and mark

- Every export carries a withheld-item manifest by count (`03_CONDUIT_MIDDLEWARE.md` §6). Per
  `06_DECISIONS.md` ADR-045, this ships by default (`disclose`); a deployment may configure `omit`
  to suppress it, in which case the export `Drawer` shows no manifest text at all rather than a
  zeroed or placeholder count. The export `Drawer`'s own footer is where the manifest and the
  Osprey mark both render. Per `06_DECISIONS.md` ADR-047, the
  mark carries the artefact's own highest handling level, not only provenance: a chart gets a
  visible footer/watermark plus embedded machine-readable image metadata carrying the same fields;
  a subgraph carries the mark as a top-level structured field with no visual rendering; a report
  carries both. The export pipeline never produces an artefact with no mark at all.
- The manifest renders as plain text beside the `Export` button — "N items withheld by handling" —
  reusing the exact status-bar phrasing (§2's own "6 hidden by handling") rather than a second
  wording for the same fact, so an analyst who has read that count all session recognises it on the
  export screen without re-learning it.

### 10.4 Theme

Light is the default rendering for a chart export (§4: "An exported chart destined for an
intelligence product should default to light"), regardless of which theme the analyst is currently
working in; a toggle lets them override back to dark before exporting.
