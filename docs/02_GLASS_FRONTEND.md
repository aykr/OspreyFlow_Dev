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
`07_BUILD_PLAN.md`'s own narrative.** A community (above) is a Leiden/analytics grouping, rendered
as a translucent hull. A resolution cluster (`Node.resolution.cluster_id`, `01_DOMAIN_MODEL.md`
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
- Community assignment (Leiden)

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

**Visual query builder.** A node-and-edge pattern the analyst draws, with per-element
constraints, compiled to Gremlin in the Conduit. Never expose the Gremlin; do show the estimated
result count before running. Patterns are saveable, shareable and versioned.

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
  interpolation at 420ms with a dedicated easing curve.
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

Dark is the working default. Light is a separately tuned ramp, not an inversion, and exists for
screenshots pasted into reports and for print. Both meet the same contrast floor. An exported
chart destined for an intelligence product should default to light.

Type: Atkinson Hyperlegible Next for interface, IBM Plex Mono for literal values and every
tabular figure. The reason is operational, not aesthetic — analysts read identifiers all day and
a confusable `1 l I` or `0 O` is a real error. Every identifier, hash, timestamp and account
number in the product is set in mono. Mono means "this is a value you can copy."

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

- Every canvas action reachable by keyboard. Tab moves between nodes in the current selection
  ring, arrow keys walk edges, `Enter` expands, `\` opens the radial menu as a list, `Space`
  toggles the focused node's own membership in the selection ring (`07_BUILD_PLAN.md` Phase 6a
  Stage 1: added for manual link/split, the first action needing a keyboard-built multi-node
  selection at all — walking with arrow keys moves focus only, never the ring itself).
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
