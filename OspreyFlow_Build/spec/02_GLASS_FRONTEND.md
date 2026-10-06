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

Two exceptions to the Labels column, so that nodes can be told apart (ADR-071): a view of 40 nodes or
fewer names every node at any zoom, and a node that is selected, under the pointer or on a found
path is always named.

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

Inspecting one link does not depend on the canvas at all. **Selecting** a link (a click within a
few pixels of it, or `L` / `Shift+L` from a focused node) highlights it and shows its type, the
direction between its ends, occurrence count, dates, provenance and contributing source records in
the Inspector. *Corrected 3 October 2026 (ADR-064): this paragraph said hovering or selecting an
edge opened a DOM overlay at the pointer. Hovering opened it under the pointer, so the next click
landed on the overlay and a link could not be selected; hovering now opens nothing, and the details
live in the Inspector.* A selected link can be hidden from the view (Delete); that is a view setting
for the browser tab, not a change to the working set.

**Notes on a link (ADR-075).** With a link selected, the Inspector shows a **Notes** section under its
details: a box to add a note (Add note, or Ctrl/Cmd+Enter), then the notes newest first, each with its
author and time. Everyone who can see the link sees its notes, and the section says so. On a note of
their own an analyst has **Edit** (Save, or Escape to cancel) and **Delete** (asks "Confirm delete"
first); other people's notes have neither. A failed save keeps what was typed and says why. A link
that is not in the person's view shows "This link is not in your view" and no box. The section is
offered only while a case is open. Keyboard: every step is reachable without a mouse (rule 13,
`keyboard/link-notes.spec.ts`).

**Changing a link and its history (ADR-080, §3.1f).** Under a selected link that is not a same-as or
not-the-same link the Inspector also shows **Change this link…** (a form: type, details, dates,
records behind it and a required reason) and a **Change history** list. A same-as link is not edited:
it is confirmed or marked as not the same from its menu.

**Zoom-dependent clustering is a data operation, not a rendering one.** Collapsing a community
into a meta-node, or expanding it back, happens in graphology and produces a real change to the
working set with an entry in the step history. It behaves identically whichever renderer draws
it, so it was never part of this decision.

**Resolution clustering is a separate, unrelated sense of "cluster," and neither this document nor
the Inspector's own tab list (§2) ever named a rendering convention for it — recorded here
directly, rather than left implicit.** A community (above) is a Louvain/analytics grouping
(`06_DECISIONS.md` ADR-029 — Leiden is unavailable on either compute tier), rendered as a
translucent hull. A resolution cluster (`Node.resolution.cluster_id`, `01_DOMAIN_MODEL.md`
§4) is the query-time collapse of `SAME_AS` edges scoring above the session's τ — a different axis
entirely, and the two must never share a visual channel or an analyst could not tell which kind of
grouping they were looking at.

*Collapse (B9).* Every node sharing a `cluster_id` with at least one other co-locates at
the cluster's own anchor position and gains a second, independent `@sigma/node-border` ring (never
the same attribute the interaction-state ring — on-path/selected/hover — already owns, so both can
show on one node at once). A node whose cluster splits back apart returns to where it was before it was
joined, and the layout then runs so each node has a place of its own, rather than staying wherever a
previous merge left it (the Fixture Corp walkthrough found nodes staying stacked; ADR-080
Amendment 2). This is the picture the
threshold control's own change-summary counts (`merged`/`split`/`affected`) must agree with.

*Explanation (B10).* `GET .../resolution/explain/{cluster_id}` — the per-comparison match
weights behind a cluster — renders in a transient `Popover` overlay anchored to the triggering
canvas position, the same shape edge inspection (above) already uses, opened from a cluster-aware
item in the existing radial menu. Not an Inspector tab (none is named "Resolution," and inventing
one pre-empts the Dossier, B6's own, larger, permanent surface for exactly this class of
content) and not a modal. A row is omitted, never shown redacted, if the render cannot independently
confirm both endpoints of a pairwise comparison from the response's own `member_node_ids` and this
session's already-access-controlled local graph — belt and braces against a node id the API
technically cleared but this client has not yet synced, or against a future regression, not a
claim that the API itself is untrusted.

*Highlighting (B6).* This document had no rendering convention for message-span
highlighting — recorded here directly, not left implicit. A highlighted span never
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
┌────────────────────────────────────────────────────────────────────────────────────┐
│                     OFFICIAL — the highest marking in view                         │ strip, 20px
├────────────────────────────────────────────────────────────────────────────────────┤
│ ◆ Osprey  Case 4471 — layering ▾  [ Search…  / ]  [Graph|Map]  Export ⚙  Dark  👤  │ top bar, 40px
├──┬───────────────────────────────────────────────────┬─────────────────────────────┤
│▣ │ Resolution: ●Balanced            (view toolbar)   │ ⠿ Inspector              ⋯  │ header, 28px
│◷ ├───────────────────────────────────────────────────┤ ▸ Properties                │
│↺ │  CANVAS — Graph · Map · Messages                  │ ▸ Relationships             │
│⇪ │                                                   │ ▸ Provenance                │
│  │  Selection drives the inspector.                  ├─────────────────────────────┤
│  │  Every filter dims, never removes.                │ ⠿ Metrics                ⋯  │
│  │                                                   ├─────────────────────────────┤
│  │ [3 selected  Expand  Branch…  Remove  Clear]      │ ⠿ Query builder          ⋯  │
│  ├───────────────────────────────────────────────────┤                             │
│  │ ▸ Timeline (folded until opened)                  │                             │
├──┴───────────────────────────────────────────────────┴─────────────────────────────┤
│ 12,481 nodes · 38,902 edges · 214 dimmed by filter · 6 hidden by handling ⓘ         │
└────────────────────────────────────────────────────────────────────────────────────┘
```

The rail on the left (44px; ADR-097 step 1) holds the places the analyst goes to: *Cases*, *Watches*,
*History*, *Proposed types* (administrators only, ADR-090 C3) and the *Ingest Studio*; in the Ingest
Studio it holds *Back to the investigation*. Each is an icon button whose accessible name is its label;
*Show names* widens the rail to show the labels and *Hide names* narrows it again. *Cases* opens a
drawer listing the open cases (the strip of tabs of ADR-084, as a list) with *Browse all cases*. The
**view toolbar** above the canvas holds what belongs to that view alone: the resolution threshold on
the Graph, *Add site* and *Draw boundary* on the Map. The **selection bar** at the foot of the canvas
appears when anything is selected (ADR-097 step 1; `keyboard/selection.spec.ts`). The timeline opens
folded. Above the bar, the **classification strip** names the highest protective marking among what is
on screen, by the deployment's handling scheme's order, and is never hidden (`role="note"`, "Protective
marking"). Chrome is these three rows — strip, bar, view toolbar — and no more (ADR-097 Amendment 1);
their heights are checked (`keyboard/shell.spec.ts`).

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
4. **The status bar never lies.** Counts of dimmed and handling-hidden items are always visible. Each
   count is a pair, its number in mono beside its words in the UI face, with a quiet separator between
   pairs (ADR-097 step 3).
   An analyst must never be able to mistake a filtered picture for a complete one.
5. **The signed-in principal's own identity is always visible, informationally only.** A button
   at the right-hand end of the top bar reading `<user name> · <clearance>` (e.g.
   `analyst-1 · OFFICIAL`; the subject when the token has no user name). The clearance is never
   cut short. Opening the button shows the subject, clearance and unit, and a `Sign out` control
   (`06_DECISIONS.md` ADR-065). Added by `06_DECISIONS.md`
   ADR-050, whose own objection 9 found this document silent on the element its design put here;
   this is that gap closed, not a decision made only in the ADR. Rule 3 stands unchanged: the
   Glass reads `sub` and `clearance` from the signed token and displays them, and derives nothing
   from either — a principal with a lower clearance sees exactly the same controls, differing only
   in what the Conduit itself returns. `Sign out` ends the session at the identity provider
   (`end_session_endpoint`) and clears the Glass's own memory and session storage; it does not
   itself alter what any control shows.

**Hiding panels (ADR-082).** The right-hand column (the Inspector with the metrics and the query
builder) and the timeline can each be hidden with a *Hide* button and brought back with *Show*. The
right-hand column can also be opened to the **full width** of the work area, over the canvas, so a
wide query has room, and returned with *Normal width*. Hidden contents stay mounted and keep what the
analyst typed or brushed. The choice belongs to the browser tab: it is not stored, and each panel
opens in its normal state on reload. Every one of these buttons is reachable by keyboard
(`keyboard/panel-frames.spec.ts`).

**Reordering panels (ADR-085; header from ADR-097 step 1).** The three panels of the right-hand column
(the Inspector, the Metrics panel and the Query builder) can be put in any order. Each has one header row
(28px, a hairline below): a drag handle, the panel's name at `--fs-12` 600 in secondary text, and a menu
button, *Arrange the {panel}*, whose menu holds *Move up* and *Move down*. The panel's own title is not
drawn a second time inside it. Dragging the handle onto another panel's place does the same as the
buttons, and Alt+Up and Alt+Down with focus on the header move the panel without opening the menu. The
top panel's *Move up* and the bottom panel's *Move down* are shown as unavailable but keep focus. The
order is kept in this browser for this analyst (localStorage, as the theme is), is never sent to the
server and is not part of the case; a panel the current view does not draw keeps its place for when it
returns, and a stored order can never lose or duplicate a panel. The timeline is not part of the set and
nothing floats. Both routes are reachable by keyboard (`keyboard/panel-frames.spec.ts`).

**Folding a whole panel (owner, 6 October 2026).** The panel's name in its header is a disclosure button
(a chevron, `aria-expanded`): pressed, the panel folds to its header and its height goes to the panels still
open; the last panel still open takes what is left. A folded panel's contents stay mounted, so nothing
half-written in it is lost. What is folded is kept in this browser, beside the order. Reachable by keyboard
(`keyboard/panel-frames.spec.ts`).

**Each panel folds into parts (ADR-096).** The Inspector, the Query builder and the Metrics panel each
have their own accordion: every part sits in a hairline box (`--border-subtle`, `--r-control`) under a
header row (`--fs-12` 600, a chevron on the left that turns when open), and a part folds within its own
panel only. Each panel opens on its preview and folds the rest: the Inspector a link's *Details* (then
*Change this link*, *Notes*, the link's *Emails*, *Messages* or *Events*, *Change history*) or a node's
*Properties* (then *Provenance*, *Source*, *Judgements*; with no node, *Judgements* open); the Query
builder its *Pattern* with *Preview* and *Run* (then *Add to the pattern*, *Connect* once there are two
nodes, *Save and load*); Metrics its *Ranking* (then *Community detection*, *Filter*). Parts open independently.
A link-menu choice opens its part; opening *Change this link* opens the form. A folded part keeps what
is half-written in it. The three panels are denser than the rest of the Glass: body and controls at
`--fs-12`, titles at `--fs-13`, padding at `--sp-8` and `--sp-4`. Reachable by keyboard
(`keyboard/inspector.spec.ts`, `keyboard/query-builder.spec.ts`, `keyboard/metrics-panel.spec.ts`).

**What the Inspector shows (ADR-097 step 1).** With **one node** selected, its header is the node as
the canvas draws it (shape in its channel's colour, then the type) and its name as a literal value in
mono; its parts are *Properties* (open), *Relationships* (its links in view, by type, most first),
*Provenance*, *Source* and *Judgements*. With **several**, they are shown together, not the first
alone: *Summary* (open: counts by type, and every property they all share with one value), *Selected
(n)* (ADR-093's list: centre on one, take one out) and *Links between them (n)*, by type. With
**nothing** selected: "Select a node, or press / to search." — and `/` anywhere outside a text field
moves focus to search (`keyboard/shell.spec.ts`).

**Resizing panels (ADR-086).** Every panel edge is a sash, as in VS Code: the edge between the canvas
and the right-hand column sets the column's width, the edge below each stacked panel but the last sets
that panel's height (the last takes what is left), and the edge above the timeline sets its height. A
sash is dragged with the pointer or, by keyboard, reached with Tab and moved with the arrow keys (16
pixels, 64 with Shift); Home or a double-click resets it. The column stays at least 240 pixels wide and
the canvas at least 320; a stacked panel at least 48 pixels tall; the timeline between 96 pixels and
seven tenths of the window. The sizes are kept in this browser for this analyst (localStorage, beside
the panel order), never sent and not part of the case. The canvas, the timeline and the map redraw to
their new box at once. Reachable by keyboard (`keyboard/panel-frames.spec.ts`).

### 2.0 The top bar (ADR-065; rebuilt by ADR-097 step 1)

One row, 40px. From the left:

- **The mark**: the solid-cut osprey in brass and the word *Osprey* (`spec/design/`). It is not a
  button.
- **The case menu**, `<name> ▾` (its accessible name keeps `Case: <name>`; at least 240px wide, ADR-097
  step 3): opens the cases the account can reach (the open one marked),
  `All cases`, and `New case`. The name may be cut short with an ellipsis; its full text is the
  button's title. The Ingest Studio's own "Data loaded from this studio goes into" row uses the
  same menu.
- **Search**, with its **Filters** control as an icon inside the box at its right-hand end (a small
  count beside it when filters are on). Its accessible name is still `Filters`, or `Filters (n)`.
  Choosing a result draws it with everything within three links, counted first and asked about
  when large (ADR-070). `/` anywhere outside a text field moves focus to it (ADR-097 step 1).
  The "more match" hint is laid over the page under the box and fades after four seconds; the Filters
  panel is laid over the page too, so neither makes the bar taller (ADR-071).
  The box looks at each type's identifiers and its names and titles (a person's family and given
  names, an organisation's name, a place's name, a document's title) and never at a sensitive
  property; it starts after two characters and says `Type at least 2 characters to search.` while
  there is one (ADR-074).
- **The view switch**, a segmented group named *View*: Graph, Map, and Messages when a dossier is
  open. The pressed one is drawn in primary text with a 2px underline, not in brass (ADR-097: brass is
  for the primary action, focus and the selection).
- **Export**, for the whole case, on the Graph: one menu button, `Export ▾`, that opens the export panel
  (`aria-expanded`, not a pressed state; ADR-097 step 3).
- **The theme** is an item of the account menu (ADR-097 step 3); a button of its own stands just left
  of the account only where there is no account menu (the local development bypass). Either is
  **the theme button** (a worded button that names the theme a press
  switches to: `Light` while the page is dark, `Dark` once it is light; ADR-073): switches between the
  dark default and the light theme, per browser, never sent to the server (ADR-070). The choice is
  also kept in a cookie shared by every page of the deployment (the launcher, the sign-in page and the
  setup harness follow it and carry the same button; ADR-072).
- **The account**, at the right-hand end (item 5 above).

There is no application switch: the Ingest Studio is reached from the rail, and while it is open the
bar shows a brass line under it and drops what belongs only to the Glass (search, the view switch,
Export). *Back to the investigation* on the rail returns to the Glass view that was last open. Watches,
History and Proposed types are on the rail; the resolution threshold, named **Match strictness** for what
the analyst sets with it (ADR-097 step 3), is on the Graph's view toolbar. Search is at least 280px
wide.

Every menu opens on Enter or Space, closes on Escape (focus returns to its button), on a click
outside it, and when keyboard focus moves outside it, so it never traps a keyboard user.

### 2.1 Investigation selection on load — proposed, not settled spec

**Designed, not built (ADR-052):** the Glass will show a picker of the cases the account holds a
level on before the workspace opens, and a Share panel for a case's Authors. The load order below
remains what the Glass does until then.

**This document was silent on the question — checked directly, not assumed.** Before this
proposal, the Glass created its own
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

**Superseded in part by ADR-052 Amendment 5 (29 September 2026).** Step 3 above (create a case on
every load with no id) is gone. With no case resolved, and the analyst signed in, the Glass shows a
**case picker**: the cases the caller holds a level on, each with the caller's own level, and a
"New case" form. Each original case is listed once, with its branches (ADR-084) indented beneath it,
oldest first, each said to be a branch beside its level; a branch whose original the caller cannot
see sits under its oldest visible ancestor (ADR-084 Amendment 3; `nestCases` in
`investigation/cases.ts`). The header carries a case switcher, and the Ingest Studio shows the same switcher
above its tabs ("Data loaded from this studio goes into"), with "New case" in it. Choosing a case
sets the sessionStorage key and reloads the page, because the working set, cross-filter store and
delta stream are built once per case, and it signs back in by itself (`from=case`, ADR-052 Amendment 6). Steps 1 and 2 (query parameter, then session) are unchanged.

### 2.2 Opening from the launcher

The launcher (`make launch`, `05_DEPLOYMENT.md` §3) opens the Glass with `?from=launcher`, and with
`&view=ingest` for its Ingest Studio tile. The Ingest Studio is the Ingest tab of the Glass, so the
two tiles differ only in this parameter. `from=launcher` tells the Glass that the person has just
signed in there, so it starts its own sign-in without waiting for a click; the identity provider
already knows them, so no password is asked. If that cannot be done (no identity-provider session,
or it cannot be reached) the sign-in screen appears as before, worded for the Ingest Studio when
that was the tile pressed. `view=ingest` opens the Ingest tab after the sign-in, remembered in
`sessionStorage` for ten minutes because the query does not survive the identity provider's round
trip. **This grants nothing:** the Glass still signs in with its own client and the Conduit still
checks every request against the token's roles (ADR-050). A refused sign-in (an `error` parameter
on return) is shown and is never retried automatically. Only the Ingest tab can be requested
(`apps/workspace/src/auth/launcherHandoff.ts`, `App.test.tsx`).

## 3. The five analytical capabilities

### 3.1 Network analysis

| Requirement | Implementation |
| --- | --- |
| Expand a node's relationships | Context menu on right-click, headed with the node's type and name and closed by a click elsewhere or Escape (a list, so long edge-type names stay readable; the browser's own menu is suppressed); items generated from the ontology's edge types valid for the node's type, each with a live count, or `count unavailable` if the preview failed; actions with no count show none. A double-click on a node (or Enter on a focused one) expands its neighbours across every edge type, except on a Document, which opens to read (ADR-092; its right-click menu still expands it) |
| Search Around | Multi-step, filtered traversal builder — `Person → uses → Endpoint → communicated with (≥5 events, in brush window) → Endpoint → used by → Person`. Preview count before committing to the canvas |
| Pathfinder | Select two nodes, get k-shortest paths; paths render with the on-path node state (2px primary stroke, edges thickened), everything else dims to 32% |
| Subgraph isolation | Select nodes (by lasso, or by clicking with Shift, Ctrl or Cmd held to add one at a time; a plain click selects one node alone), then **Branch selected** — the strip's button, or the same entry in any selected node's right-click menu (ADR-084 Amendment 1) — and the selection opens as a new case in a tab of its own (§3.1h, ADR-084), with its own filter state; the parent is untouched. A bounding-box selection has no implementation yet |
| Undo | Every canvas mutation is a step in an addressable history; the history panel is a list of named steps, not a stack of arrows |

**Expansion budget.** Every expansion previews its cardinality before executing. Above 500 new
nodes the action requires a filter or an explicit acknowledgement. This single control is what
stops an analyst turning a legible network into a hairball in one click, and it is the most
common complaint about link analysis tools.

### 3.1a Communities on screen (ADR-066)

A `Communities` button on the canvas draws a box round each group of closely linked nodes in the
view (Louvain, fixed seed, so the same nodes give the same groups). A group folds into one Group
Node (the box's button, `G` on a focused node, `Collapse all`, or a double-click inside the box) and
opens again (the same keys, or a double-click on the Group Node). The status bar says how many nodes
are folded into groups. It is a way of looking at the view: nothing is stored or sent to the server.
Every action is reachable by keyboard, and `keyboard/keyboard.spec.ts` proves each one.

### 3.1b Labels on nodes (ADR-076)

A `Labels` button on the canvas opens one picker for each type of node now in view, listing the
type's own properties (its identifiers, then its other properties; a sensitive property and a list
are never offered) and `Default`. The property chosen names every node of that type on the canvas,
in the search list and wherever else a node is named; a node that lacks the chosen property keeps
its default name rather than going blank. With nothing chosen a person is named "Family, Given"
(family name alone when there are no given names), a thing with a `name` (an organisation, a place) or a
`title` (a document) by it, a thing by its normalised value, and anything else by its id (corrected 6
October 2026: an extracted organisation called BPA was drawn as its id). The choice is kept in this browser only: it is not sent to the server, is not part of the
case, and is not shared with other analysts, as with the light and dark theme. The panel says so.
Reachable by keyboard (`Tab` to the button, `Enter` to open, arrow keys to choose, `Escape` to
close), and `keyboard/keyboard.spec.ts` proves it.

**How a label and a node are drawn (ADR-097 step 2).** A label is set at `--fs-12` in the theme's
primary text: in mono (`--mono`) when it is a literal value — the chosen property is one of the type's
identifiers, or with no choice the node is named by its normalised value or its id — and in `--ui`
otherwise (a person's name, a thing's name, a document's title). A label longer than 24 characters is cut in the middle with an ellipsis, so
both ends of an address or an account number stay readable; the full text is in the Inspector. A label
that would run past the canvas's right-hand edge is drawn on the node's left instead, and never before
the left edge. At 100% (a camera ratio of 1) a node is 20 pixels across in an uncrowded view, measured
from the painted pixels (`keyboard/canvas-look.spec.ts`); the far overview keeps nodes small, and
a crowded view still shrinks them as before.

**Zoom, the legend and the grid (ADR-097 step 2).** A zoom cluster at the canvas's lower right, a group
named *Zoom*: *Zoom in*, *Zoom out* and *Fit to view*; F with the canvas focused fits too (the whole graph
framed, as an arrangement frames it). A legend at the lower left lists each type in view as the canvas
draws it (shape in its channel's colour), with how many, most first; *Legend* folds it to its title. The
graph canvas, and no other surface, has DESIGN.md §9 exception 4's measurement grid: 1px `--border-subtle`
lines on an 8px lattice, fixed to the screen. *Grid* in the toolbar's Show group switches it off and on
(pressed while it shows); the choice is kept in this browser (owner, 6 October 2026). All of them come after the view's own controls in Tab order.
Reachable by keyboard (`keyboard/keyboard.spec.ts`); the painted grid is read from the pixels
(`keyboard/canvas-look.spec.ts`).

**The canvas toolbar (ADR-097 step 2, design review item 12).** The canvas's own tools are one docked
row along its top edge, *Canvas tools* (32px, `--surface-panel`, a hairline below and no shadow:
DESIGN.md §6), in labelled groups: **Select** (the lasso), **Layout** (the layout, *Bubbles by* for
Clustered bubbles, *Arrange again*), **Show** — one segmented control of *Communities* (pressed while on),
*Labels* and *Icons*, followed while Communities is on by what it found and *Collapse all* / *Expand
all* — and, at the right-hand end, **View** (*Hide selected link*, *Show hidden links (n)*, *Clear view*,
*Add files*). A menu's panel and *Clear view*'s confirmation are laid over the canvas under their
button, as overlays with a shadow. The toolbar's controls are quiet buttons at `--fs-12`; a pressed or
open one is primary text with a 2px underline. Checked in the browser (`keyboard/canvas-look.spec.ts`:
the groups, one row, no shadow); each control keeps its own keyboard case.

### 3.1c An expansion that adds nothing says so (ADR-077)

Choosing a relationship from a node's menu (or pressing `Enter`, or opening a search result) asks the
Conduit for that node's neighbours. When everything it returns is already drawn, the Glass says so
beside the node instead of staying silent: "Nothing new: everything linked by SAME_AS is already in
view." when the type was chosen, or "No links from this node." when nothing came back at all. The
message is a notice, not an error (no alert, no error colour) and `Escape` closes it. When the
expansion brings in anything new, there is no message. `keyboard/keyboard.spec.ts` proves it.

### 3.1d The right-click menu (ADR-078)

Right-click on a node (or `\`) opens a list headed by the node's type and name. The relationship
types sit under a **Show links** heading, each with its count in a quieter tone at the right edge;
everything else (link, split, find paths, explain cluster, view messages, mark for suppression) sits
under **Actions**, below a hairline. The order in which the entries are reached by keyboard is
unchanged; the headings are not focusable. The menu is drawn above the canvas's own layers, so none of
its labels or nodes show through it. All colours and spacing are from the tokens.

### 3.1e Icons on nodes (ADR-079)

A node is drawn as its type's shape and hue with an icon inside it. The icon comes from the ontology
(`EntityTypeDef.icon`); an `Icons` button beside `Labels` lets the analyst change it, for each type
of node now in view, to another of the twenty built-in drawings, to none, or to a small picture of their
own given from a file (png, jpeg, webp or gif, up to 5 MB; an SVG is refused). The picture is cut to
its middle square and kept as a 64-unit thumbnail. The choice is kept in this browser only: it is not
sent to the server, is not part of the case, and is not shared with other analysts, as with the
theme and the label choice. The panel says so. The icon is drawn in white or near-black, whichever
reads better on the fill, and fades with a dimmed or filtered-out node. A node is small until the
view is zoomed in, so the icon is a reading aid at close range, not at overview. Reachable by
keyboard (`Tab` to the button, `Enter` to open, arrow keys to choose, `Escape` to close; the file
control is an ordinary file input), and `keyboard/keyboard.spec.ts` proves it, including that a
picture given from a file reaches the canvas's pixels.

### 3.1f The right-click menu on a link (ADR-080)

Right-click on a drawn link (the click finds the nearest link within 6 pixels), or select it (`L`
steps through a focused node's links) and press `\`, to open a list titled `TYPE: A ↔ B`. A
**same-as** link offers *Collapse into one node* (*Expand* once folded), *Confirm as the same*, *Mark as
not the same*, *Explain this link*, *Add a note* and *Hide link*. A **not-the-same** link offers *Add a
note* and *Hide link* only. **Any other** link offers *Show emails (n)* (or *Show events (n)*, by what the link's events are;
ADR-089), *Change link…*, *Show change history*, *Add a
note* and *Hide link*.

*Collapse into one node* is a view, not a change: the matched nodes (the whole resolution cluster when
both ends are in one, otherwise the two ends) fold into one Group Node by the same machinery as
Communities, nothing is merged in the store (rule 6), and the fold is lost on reload. A link inside a
folded group is not drawn, so the Group Node's own menu has *Expand group*; double-click and `G` still
open it. A fold made from a same-as link is opened again whenever the resolution changes (the slider moves, or a
match is confirmed or refused), with a short notice, because the clusters it was made from are no longer
the same (ADR-080 Amendment 1). *Confirm as the same* and *Mark as not the same* open a small box that asks **why**: a
reason is required (the button stays off until there is one; Control/Cmd+Enter confirms, Escape
cancels) and is kept in the audit trail with the analyst's name. *Explain this link* opens the cluster
explanation for the cluster the two are in, or says they are not in one at the current threshold.
*Add a note*, *Change link…* and *Show change history* select the link and take the Inspector to the
matching section.

*Show emails (n)* takes the Inspector to its **Emails** section (ADR-089): the events the link stands
for, newest first, fifty at a time with *Show more*, each with its date, direction, subject and the
first words of its text. Choosing one opens it to read, with its sender, recipient, date and whole
text (ADR-095; a note says so only for an event loaded before then, when the text was cut at 4,000
characters). *Put on the canvas* in the list writes the emails (or a phone link's messages) inside the
timeline's window as Documents and draws them, exactly as the link menu's *Show emails (n)* does,
or says the view would be too full (ADR-095 decision 4). Reachable by keyboard
(`keyboard/link-events.spec.ts`). On a link between two email addresses (`Endpoint.endpoint_kind` is `email` at the source)
*Show emails (n)* also puts the emails inside the timeline's brushed window (all of them when nothing
is brushed) on the canvas as Documents, linked to both addresses, and says how many (ADR-092); past
the working set's cap nothing is added and the message says by how much and to narrow the timeline.
A link whose events carry no text (a PaySim transaction, an HMP incident) keeps the Inspector list
only. A link between two phones (`endpoint_kind` `msisdn`, `imsi` or `handle`) is named for its
**messages** (ADR-094): *Show messages (n)*, "· 3 messages", the Inspector's **Messages** list,
where a message is named by its first words and a call by its length; *Show messages* puts the
messages with text on the canvas as Documents titled by their first words, and says how many events
had none (a link of calls only is said to have none, as a notice). Proved by keyboard in `keyboard/link-menu.spec.ts`.

An opened email offers **Extract entities** (ADR-089 step 3). The email becomes a `Document` node linked
to its sender and recipient by `MENTIONED_IN`, both appear on the canvas at once, and the model's findings
are listed as suggestions with a confidence each. Nothing a model finds reaches the graph until a person
accepts it (rule 5): *Accept* on one finding writes it as an inferred node with a `MENTIONED_IN` link to the
email, both onto the canvas, where it is confirmed from the Inspector as any inferred node is. The model is
the deployment's local one unless the caller names another. Reachable by keyboard
(`keyboard/link-events.spec.ts`).

The change form asks **what stands behind the link** each time, with no default (ADR-081 Amendment
1 item 6, Amendment 2): *Direct* is offered only where the link's type is Direct and the link is not
already probabilistic; *Probabilistic* is always offered; where only one answer is possible the form
states it. The reason given for the change is the reason for a probabilistic mark, and the Inspector's
*Basis* row points to the change history for it. A link is never promoted to Direct by hand. Reachable
by keyboard (`keyboard/link-change.spec.ts`).

The Inspector's **Change this link** form (any link other than same-as and not-the-same) offers the
link type (only those the ontology allows between the two ends, never a same-as type), the properties
that type declares, the dates it covers, the records behind it, and a **required reason**. Saving
replaces the link and keeps the old one: **Change history** lists every change newest first, each with
who made it, when, the reason, and what the type, details, dates and record count were before and
after. Notes follow the link to its new version. Every write from the menu is recorded in the audit
trail attributed to the analyst. Reachable by keyboard throughout (rule 13: `keyboard/link-menu.spec.ts`,
`keyboard/link-change.spec.ts`). A menu or box that closes returns focus to the canvas.

**When no type fits, an Editor defines one there (ADR-090).** The types the form offers are the case's
own (`GET .../link-types`): the ontology's, and those proposed in the case, the cases it was branched
from, or for a link the analyst can see in it, each proposed one marked "(proposed)". **Define a new
type…** asks for a name in sentence case ("Known to"), from which its ID is made (`KNOWN_TO`, which may
be edited), whether it goes either way round, a colour and a thickness (both optional), and why no
type fits; the ends are the link's own. Proposed, it is chosen at once in the form and, being
probabilistic until an administrator decides, its basis is stated, not asked; on the canvas its links
are drawn dotted in its own colour and thickness, named by its label. The Glass reads the case's types
when a case opens and again after a proposal or a decision. A refused name is said in the server's
words. **An `osprey-admin` holder** also has **Proposed types** in the top bar: their own unit's
proposals, each with its name, ID, ends, proposer, case and reason, to **Promote…** (Direct or
Probabilistic, no default, and a new ID when the server says the name is taken by a type its links do
not fit), **Reject…**, or once promoted **Retire…**, each with a reason. Reachable by keyboard
throughout (`keyboard/link-change.spec.ts`, `keyboard/proposed-types.spec.ts`). A proposal is not yet
withdrawn from the Glass: the route exists (spec 03 §3.4) and the form does not offer it.

### 3.1g Two more layouts: a force-directed tree and clustered bubbles (ADR-083)

The Layout menu also offers **Force-directed tree** and **Clustered bubbles**. The tree grows from the
selected node (the most linked node if none is selected) and settles under the same forces as the
organic layout, with only the links of the tree pulling; each piece of the graph the root does not reach
gets a tree of its own, so nothing is left out. Links not in the tree stay, drawn faint. Clustered
bubbles draws one circle for each group, with its name and size, the group's nodes packed inside and
the circles packed against one another; a second choice, **Bubbles by**, picks *Entity type* (the
default) or *Community*. Both only move nodes: nothing is stored or removed, and both are reachable by
keyboard through the Layout choice (`keyboard/keyboard.spec.ts`).

**Arranging and the view (ADR-060 Amendment 2).** When nodes arrive (an expansion, a search result, a
delta) the nodes already settled stay exactly where they are and the new ones settle around the neighbours
they came in beside; the camera is not touched, so the view never moves under the analyst's hands. When the
analyst asks (the Layout menu, *Arrange again*), or the resolution releases nodes, everything is arranged
afresh and the view is fitted to the result; the first fill of an empty canvas is fitted too. Only nodes
that are going somewhere are animated. `keyboard/keyboard.spec.ts` proves an expansion leaves the camera and
the settled nodes where they were.

### 3.1h Branch selected, and the strip of tabs (ADR-084)

Selecting nodes shows the **selection bar** (ADR-097 step 1, below), whose **Branch to a new case** sends the nodes to a **new case of their own**, holding those nodes and the links between them, and opens it. The case you branched from is left exactly as it was. A branch is a **copy** made at that moment: later changes to either never touch the other. A selected Group Node stands for every member of its group, so choosing one chooses them all. What the new case holds is re-checked against the branching analyst's own clearance, as every read is: a node they may not see is not copied, and a request that leaves nothing to copy says only "None of the selected nodes could be branched", whatever the reason.

**Seeing and working the selection (ADR-093, ADR-097).** A selected node is drawn larger with a bold
brass ring (§4's table). While anything is selected, the **selection bar** floats at the bottom centre
of the canvas (an overlay: a shadow, no hairline): "n selected", the only live count of the selection
in the page, then *Expand* (each selected node in turn, each through its own preview and the working
set's cap), *Branch to a new case*, *Remove from view* and *Clear*; Escape clears. It replaces the
corner chip and the toolbar's *Remove selected* and *Branch selected*. A branch is named "Branch of
<case> (n nodes)", or "Branch of <case>" for the whole view; never a selection count with a middle dot. When more than one node is selected, the Inspector lists them
by name under "Selected (n)": choosing a name centres the canvas on that node and leaves the
selection as it was, and × takes it out. Proved by keyboard in `keyboard/selection.spec.ts`
(registry `SELECTION_ACTIONS`); the ring by painted pixels in `keyboard/selection-look.spec.ts`.

The selection is built with the lasso, or by clicking nodes with Shift, Ctrl or Cmd held (each adds the node, or takes it out again). *Branch to a new case* is on the selection bar and, for any node that is in the selection, *Branch selected (n)* is an entry in that node's own right-click menu (ADR-084 Amendment 1); a node outside the selection does not offer it. Both reach the same route; `keyboard/keyboard.spec.ts` proves each by keyboard.

Each branch is a case saved for the analyst who made it (they are its Author, and it is visible to nobody else until they share it). It starts with the resolution threshold, layout and timeline brush of its own, not shared with the case it came from. The events behind the links it copied (the timeline's counts, *Show emails*, an email to extract from) are read from the case they were loaded into, for the links the branch holds, wherever the analyst can see that case; nothing is copied (ADR-084 Amendment 2).

A **strip of tabs** sits under the top bar once a case has a branch. The original case is always the first tab; its open branches follow, each with a close button; the one on screen is marked. **Closing a tab only hides it** from this analyst's strip (a flag kept for them alone, which says nothing about anyone else's view). The **Branches** menu at the end of the strip lists every branch, open or hidden, as "Branches (n open of m)", so the analyst always sees the whole set they are working across; from it a branch is opened, brought back into the strip, or **discarded**. Discarding asks first and is the same soft remove as for any case: it leaves every list and nothing is deleted. Only an Author of the branch (or an administrator of the unit) is offered it, and never for the branch on screen.

Switching tab opens that case, which reloads the page, as every case switch does (§1): the working set, timeline and delta stream are each built once per case. The expansions and filters of a case are kept on the server, so they are still there; where nodes sit on screen and what was selected are not. Having several canvases live in one page, so that switching is instant and keeps the layout, is a later step (ADR-084).

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

The panel opens closed. It has three sections, **Ranking**, **Community detection** (named so since ADR-097
step 3, apart from the canvas's *Communities* view) and **Filter**, one open at a
time, and a closed section fetches nothing (ADR-070).

**Filter (ADR-088).** Two social-network filters, both of which dim and never remove (§2 rule 2). A
*Relationship strength* slider dims every link whose weight is below it and every node left with no
strong link, so the network thins to its strongly linked core and grows back as the slider returns. A
*Filter by metric* choice, any of the seven metrics above, fetches that metric's values and offers a
*Metric value at least* slider from the smallest to the largest; nodes below it dim, as does a node the
metric gave no value. The two add to each other and to the timeline's dimming, and the status bar counts
the union. A filter belongs to the view and is not stored; *Clear filters* returns the full picture.
Reachable by keyboard (`keyboard/metrics-panel.spec.ts`).

Community detection produces a **hull overlay**, not a recolour: a translucent boundary drawn
around each community at 8% channel opacity, labelled with size and dominant entity type.
Recolouring nodes by community would collide with the entity-type channel and break the one rule
the design system will not bend.

### 3.3 Pattern analysis

Three mechanisms, in increasing order of power:

**Visual query builder.** A node-and-edge pattern the analyst composes — an entity-type palette
places a node, search pins one to an already-known entity, a connect control joins two with an
edge — with per-element constraints, compiled to Gremlin in the Conduit. **Not a second drawing
canvas** (`06_DECISIONS.md` ADR-032, correcting this bullet's own earlier
"draws"): a list/palette editor built from the same native controls as every other panel, chosen
because the pattern shapes ADR-030's own compiler can express are small enough to read as a list,
and because a canvas inherits every accessibility problem `GlassCanvas` has already needed fixing
once (that ADR's own reasoning). Never expose the Gremlin; do show the estimated result count
before running, principal-filtered exactly like the result itself will be, never a raw or
unfiltered figure — access control is enforced before a count reaches the Conduit's response, not
filtered afterward, and the Glass is never shown an unfiltered count. **Patterns are saveable,
shareable and versioned** is this bullet's own unbuilt promise — only compose/preview/run are
built; saving, sharing and versioning a pattern are not yet implemented.

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
- **Brush** — drag to select a window; the graph dims everything outside it, nodes and links
  alike (a link with no event in the window dims, ADR-087), the map restricts
  to it, the histograms recompute. Brush endpoints are editable as text. The two boxes sit behind a `Set exact dates` button in the timeline's bar, and the cross-case overlay's investigation box behind an `Overlay another case` button (`06_DECISIONS.md` ADR-069).
- **Playback** — animate the brush forward at 0.5× to 8×. **The network emerges as it plays
  (ADR-087):** every node and link in the view starts dimmed and lights up as the playhead passes
  its first event in the window, then stays lit, so the analyst watches the network appear in the
  order it did; nothing moves and nothing vanishes. Nodes interpolate position and never
  cross-fade, so identity is continuous through a re-layout. The design system fixes the
  interpolation at 420ms with a dedicated easing curve. **A base duration for "1×" was left
  unstated here — a real spec gap, since closed: a full traverse of the brush window at 1× takes
  8 real seconds**
  (`playback/math.ts`'s own `PLAYBACK_DURATION_MS_AT_1X`), chosen as long enough to read a dense
  timeline's own movement and short enough not to feel stalled at 0.5× (4s) or rushed at 8× (1s).
- **No dated events** — a case whose data carries no dated events (Fixture Corp today) says so in
  the strip's place and offers neither a brush nor playback (ADR-087), so the graph is never dimmed
  for a reason the analyst cannot see. The strip returns the moment the case gains events.
- **Cyclical view** — the HMP analysis is a day-of-week and hour-of-day analysis, and a linear
  timeline cannot show that. Provide a second mode that folds the window into a weekday × hour
  grid with counts, which is the same finding the source report reached with a polar plot.
- **Multi-track mode** — one row per selected entity, events as marks. This is how a
  relay-and-cut-out pattern becomes visible: two endpoints that never overlap in time.
- **Cross-case overlay** — events from a second investigation on a distinct track, for linking
  independent cases on shared timestamps or identifiers.

Under `prefers-reduced-motion`, playback becomes stepped and re-layout becomes an instant move
with a persistent control that shows previous positions. Removing the animation removes the only
cue for what moved, so something must replace it. Built (ADR-097 step 3): once an arrangement has
moved nodes, the canvas toolbar's Show group gains *Previous positions* (*Show previous positions*,
pressed while on), which marks each moved node's last place with a hollow ring and a dashed line to
where it is now; the camera's fit and zoom are instant too. Without reduced motion there is no such
control, as the move itself shows what moved (`keyboard/keyboard.spec.ts`).

**Selecting a window (corrected 6 October 2026).** A drag across the density strip's bars is the brush:
its range of bars is the window, which dims the graph, and it stays drawn as a shaded band that can be
moved or resized; a window set another way (*Set exact dates*) is drawn the same way. The slider under the
strip zooms the axis only and never filters: a stray early date can squeeze every other bar into a
corner, and zooming past it must not change what is dimmed. Until this correction a drag across the bars
went to the chart's own pan-and-zoom, which at full range has nothing to pan, so only the slider's end
handles set a window (`keyboard/timeline-brush.spec.ts`).

**The timeline's header and axis (ADR-097 step 3, design review item 13).** *Density* and *Cyclical*
are one segmented control, *Timeline view*, in the timeline's header. Setting exact dates and
overlaying another case are in its overflow menu, *More timeline options*; *Clear filter* and playback
stay in the header, since they appear only when there is something to act on. The count axis has whole
numbers only, and every tick is set in mono. A case whose dated events all fall on one day (UTC) is
drawn by the hour (`HH:00`), with a note saying so, since one bar says nothing; not while another case
is overlaid, whose daily buckets must line up (`keyboard/timeline-playback.spec.ts`,
`src/timeline/Timeline.test.tsx`).

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
Neither this section's "Offline tiles"
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
| Selected | Drawn 1.6 times its size, with a brass ring (24% of its radius) and a surface gap (8%) inside it, and always named (ADR-093) |
| On path | 2px primary stroke, incident edges thickened |
| Dimmed | 32% channel toward panel |
| Filtered out | 12% channel, label dropped |
| Asserted | 1px border-strong |
| Inferred | 1.5px dashed 4-2, channel colour |
| Unresolved | 1.5px dotted, channel colour |

**Selected and on-path, combined — resolved here rather than left as a disclosed gap.** Selected and
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

**Links are drawn by basis (ADR-081).** The line style follows the link's basis and is never
authored: the link's own `basis` where an analyst has marked a Direct type's link probabilistic (step
B, Amendment 2), and otherwise its type's. A Direct link is solid, a Probabilistic link is dotted (a dot three pixels long and
a gap four, in screen pixels, so the pattern does not change with zoom). A dotted link keeps an
arrowhead where its type is directed; `SAME_AS` is probabilistic and undirected, so it is a plain
dotted line. A type with no basis (`NOT_SAME_AS`, or a type the ontology does not know) is drawn as
it always was. A type may declare a `colour` (one of the nine data channels, so no colour outside
the tokens) and a `thickness` from 1 to 5: the thickness is the width at the default weight and the
link's weight scales it between half and one and a half times, so a heavy link reads thicker than a
light one of the same type. A type that declares nothing keeps the ordinary colour and the
weight-only width. A found path and the selected link keep their own treatment over any declaration.
Sigma's stock plain line is one pixel wide whatever its size, so a solid undirected type that declares
a thickness, and both dotted lines, are drawn by programs of the Glass's own
(`canvas/dottedEdgePrograms.ts`); picking still treats a dotted link as one continuous line, so a
gap can be pointed at. Tests: `src/canvas/nodeAttributes.test.ts` (which program, what colour and
width) and `keyboard/link-style.spec.ts`, which reads the painted pixels along a link and fails if a
probabilistic link is not dotted or a direct one is.

**Provenance first, then basis; widths and arrowheads (ADR-097 step 2, Amendment 2).** Before the basis,
a link's stroke says where it came from (DESIGN.md §3.8): an **inferred** link — model-derived and not
yet confirmed by a person (rule 5) — is dashed (eight pixels on, four off: §3.8's `4 2` doubled so the
gap survives rasterising), and an **unresolved** one is dotted; an asserted link is drawn by its basis as
above. A link that declares no thickness is as wide as its weight on the six steps of the sequential
scale: 1, 1.25, 1.5, 2, 2.5 and 3 pixels across the normalised weight (`01_DOMAIN_MODEL.md` §6.1), so
weight shows; in a view of more than 10,000 links every such link is one pixel, where widths under a
pixel apart cannot be told apart and would cost the frame budget (§5). The arrowhead is six times the
line's width long and five times as wide, so at one pixel it can be seen beside a 20-pixel node. The
painted dash, dot, arrowhead and the heavier link's width are each read from the pixels
(`keyboard/link-style.spec.ts`).

**Reading a Document (ADR-092).** A double-click on a Document, Enter on a focused one, or *Read full screen* at the head of its right-click menu, opens it
full screen: an overlay over the whole work area (canvas, side column and timeline) with its title,
for an email its sender, recipient and date, and its full text with the entities already accepted
marked in place (the Dossier's marking); the text is the whole message (ADR-095), and a note says
so only for one loaded before then, cut at 4,000 characters. An email offers *Extract entities* and each finding's *Accept*, as the Inspector's email
view does, and the text is read again after an acceptance so the new entity is marked. Focus starts
on *Close*; Close or Escape returns to the canvas with nothing moved behind it. The text comes from
`GET .../documents/{id}/reader`. Tests: `src/reader/DocumentReader.test.tsx` and
`keyboard/reader.spec.ts` (Enter opens it, Escape closes it, Extract and Accept by keyboard). A Document written from held content (ADR-094) shows in the reader as what it is: an image as a
picture, a video as a player, both fetched with the analyst's token from `GET .../documents/{id}/file`;
*Extract entities* describes and reads an image, or transcribes a video, then extracts from that
text, which the reader then shows with the accepted entities marked (`POST .../documents/{id}/extract`
and `.../candidates/{id}/accept`). An email opened in the Inspector's Emails section offers *Read full screen* beside *Back to the list*; the reader opens on that email even before it has been written as a Document, and reads it as one from then on (ADR-092 Amendment 3).

**What a link reads as (ADR-091).** A link is labelled by its type's display name and a named count,
"Communicated with · 3 emails": the type's `label` where the ontology declares one, otherwise its
name in sentence case (COMMUNICATED_WITH reads "Communicated with"), and the count as emails where the
link is between email addresses (the same rule as *Show emails*), records otherwise. A type's name in
capitals is shown in one place only, the Inspector's *Type ID* row; the link menu's title, the
node menu's *Show links* entries, the change form's type list, the change history and the edge
overlay all use the display name. The caption is built only for a link that is labelled, so an
unlabelled link costs the frame nothing. Tests: `src/canvas/linkLabel.test.ts` and the caption cases
in `src/canvas/nodeAttributes.test.ts` (shown red with the old "TYPE (n)" label).

Dark is the working default. Light is a separately tuned ramp, not an inversion, and exists for
screenshots pasted into reports and for print. Both meet the same contrast floor. An exported
chart destined for an intelligence product should default to light. The top bar's theme button
chooses between them per browser (ADR-070); canvases draw from a hex palette that a test keeps
equal to `tokens.css`.

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
  canvas exactly like every other control on the page — corrected here (a
  container that instead captures every Tab keydown once it holds focus traps a keyboard user
  inside it for good, a real risk once a second keyboard-driven surface sits beside the canvas). Reaching
  the canvas by any means (Tab, a click, `.focus()`) with nothing selected establishes a one-node
  ring immediately, with no keypress needed after arriving. `Ctrl`/`Cmd`+`ArrowRight`/`Left`
  cycles the focused node through an already-built ring (needed for a lasso-selected set of
  non-adjacent nodes plain arrow-walk cannot reach); plain arrow keys walk edges, moving focus
  only, never the ring itself; `Enter` expands; `\` opens the radial menu as a list; `Space`
  toggles the focused node's own membership in the selection ring (added for manual link/split,
  the first action needing a keyboard-built multi-node selection at all). **`Ctrl`/`Cmd`+`Shift`+
  `ArrowRight`/`Left` walks every node in the working set, adjacency or not** — added after a real
  gap was found against this very bullet: `Explain cluster` and `Find paths to` are both gated on a *two-node*
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
- Every control is at least 24 by 24 pixels to press (WCAG 2.2 target size, ADR-097 step 3); a control
  may draw something smaller inside that box (the switch's 18px track). Checked across the harnesses
  by `keyboard/hit-targets.spec.ts`.
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
A floating control with no panel behind it (a `RadialMenu` entry in its radial layout) carries its own
raised surface, no border and the overlay shadow; it must never fall back to the browser's button face,
which drew near-white text on a pale fill. `src/design/radialMenuStyle.test.ts` holds this.
Radii: 0 for canvas and cells, 2px controls, 4px panels, 6px overlays, 999px status chips.

## 9. Assessment production

The HMP report is the model this platform exists to produce: a set of judgements, each resting on
named evidence, plus explicit gaps and assumptions (`01_DOMAIN_MODEL.md` §5). "Judgements" has
been named as one of the Inspector's five tabs (§2); this section is the first place
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
  contradicting the shipped build: the opacity convention is a per-*region*
  hull polygon or a per-*text-span* background, neither of which has a per-*node* shape — building
  one would be a new WebGL node-program visual channel, real rendering-engine work not yet
  scoped. Reusing the existing multi-node *selected* state (already real, via lasso) needs
  no new channel and reaches the same practical goal — "this is relevant" — at the cost of not
  being visually distinct from an analyst's own manual selection while a judgement's evidence is
  highlighted. `GlassCanvasHandle.highlightNodes`'s own docstring has the full record.
- Selecting a node lists, in the Judgements tab, every judgement resting on it —
  `01_DOMAIN_MODEL.md` §5's own "selecting a node lists the judgements that rest on it," given a
  concrete surface for the first time. On the canvas, a small brass count beside a node says how many
  judgements rest on it, drawn only from the judgements the principal can already list (ADR-070).
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
pattern already establishes for "something here needs a human's attention."

### 9.5 Marking a node for suppression — owner ruling R7, 27 September 2026, TENTATIVE

**The owner is revisiting this after their own usability walkthrough**, and it is written down in
that state rather than held back, because a ruling that lives only in a conversation is lost by
the next session — a genuine decision belongs in the spec, not in chat alone. `06_DECISIONS.md`
ADR-046's addendum carries the full ruling.

Retraction becomes two steps. An analyst **marks** a node for suppression from the canvas — the
radial menu's own `Mark for suppression` item — and that is immediate and reversible. Nothing is
suppressed by the mark: the node keeps its place in every read, its revision does not move, and
un-marking leaves nothing behind. The suppression itself takes effect only when its **evidence**
arrives through the Ingest Studio (step two), so that no record is ever suppressed on the strength
of a click alone.

```
POST /v1/nodes/{node_id}/suppression-mark
DELETE /v1/nodes/{node_id}/suppression-mark
```

- **A marker on the node and in the inspector**, the same list-row-plus-canvas-marker pairing §9.4
  already establishes for "something here needs a human's attention" — a marked node is *flagged*,
  never hidden.
- **Reversible**, which is why a mark is deliberately not a graph write: the graph is append-only
  (`01_DOMAIN_MODEL.md` §2.4), so marking and un-marking there would mint a revision for every
  change of mind and `superseded_by` would stop meaning "this was corrected".
- **You may mark what you can see** — the same principal rule retraction already uses, checked
  before anything is written. A node the principal cannot see is refused identically to one that
  does not exist.

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
shape's content comes from without ever stating what file it becomes — a real spec gap, closed
here rather than left a placeholder. Decided, not merely disclosed as open:

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
