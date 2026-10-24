# 02 — The Glass (Frontend)

## 1. Stack

| Concern | Choice | Licence | Why |
| --- | --- | --- | --- |
| Framework | React 19 + TypeScript, Vite (React 18 until the owner's dependency upgrade of 19 October 2026) | MIT | Largest pool of maintainers; the requirement is a long-lived platform, not a clever one |
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
| **Overview** | zoomed out | Community hulls drawn; nodes at minimum radius (above 10,000 nodes: dots, ADR-119) | Only above the strength filter; aggregated between hulls (above 10,000 links: one link per pair of communities, ADR-119) | None |
| **Structure** | mid | Full channel fill and shape (above 10,000 nodes: a dot in the channel colour, ADR-119) | All edges, width by weight (above 10,000 links: one link per pair of communities, ADR-119) | Top-degree nodes only |
| **Neighbourhood** | in | Full node vocabulary, all six states | Directional arrows, curved parallel edges via `@sigma/edge-curve` | All node labels |
| **Link detail** | closest | Node labels plus key properties | Per-edge label: type, occurrence count, interval | Edge labels on |

A large case (more than 10,000 links) opens grouped by community, as Clustered bubbles, so the links
between communities run between real groups; a selected or emphasised node, and a selected or
on-path link, are always drawn in full (ADR-119).

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
│ ◆ Osprey  Case 4471 — layering ▾  [ Search…  / ]  [Graph|Map]  Export ⚙        👤  │ top bar, 44px
├──┬───────────────────────────────────────────────────┬─────────────────────────────┤
│▣ │ Resolution: ●Balanced            (view toolbar)   │ ▾ Inspector              ⋯  │ header, 28px
│◷ ├───────────────────────────────────────────────────┤ ▸ Properties                │
│↺ │  CANVAS — Graph · Map · Messages                  │ ▸ Relationships             │
│⇪ │                                                   │ ▸ Provenance                │
│  │  Selection drives the inspector.                  ├─────────────────────────────┤
│  │  Every filter dims, never removes.                │ ▸ Metrics                ⋯  │
│  │                                                   ├─────────────────────────────┤
│  │ [3 selected  Expand  Branch…  Remove  Clear]      │ ▸ Query builder          ⋯  │
│  ├───────────────────────────────────────────────────┤                             │
│  │ ▸ Timeline ▁▂▅▃▁▆▂  2001-05-14 to 2001-12-03 (34px)│                             │
├──┴───────────────────────────────────────────────────┴─────────────────────────────┤
│ 12,481 nodes  38,902 edges  214 dimmed by filter  6 hidden by handling    Tip …  Next tip │
└────────────────────────────────────────────────────────────────────────────────────┘
```

The rail on the left (48px with 36px buttons, DESIGN.md v0.3 §5a; ADR-097 step 1) holds the places the analyst goes to, in this order: *Cases*,
*Watches*, *Alerts* (the case team's alert queue, its rules, held rows and audit — ADR-109, §3.3),
*Ownership* (beneficial ownership and due diligence — ADR-109, §3.3), *History*, *Explore* (where to start in the case's data, ADR-100, §3.1), *Questions* (the case's
questions to the model, ADR-098, §3.1), *Proposed types* (administrators only, ADR-090 C3) and the
*Ingest Studio*; in the Ingest
Studio it holds *Back to the investigation*. Each is an icon button whose accessible name is its label;
*Show names* widens the rail to show the labels and *Hide names* narrows it again. *Alerts* carries the case's open
and claimed alerts as a count (said in its name, "Alerts, 3 open"), and *Help*, above *Show names*,
reopens the **welcome panel** (ADR-115 E6): over the canvas's top left (320px, 280 below 1100; a shadow, no
hairline) it says what the canvas holds, offers the case's three latest history steps to pick up from
(each restored as the History drawer restores one) and the keys worth knowing (`/`, the arrows, Enter, F,
Escape, `?`). It is open until the person closes it once (kept per person in this browser); `?` anywhere
but a text field opens it again (`keyboard/welcome.spec.ts`). *Cases* opens a
drawer with the tree of cases and branches (ADR-084 Amendment 4) and *Browse all cases*. The
**view toolbar** above the canvas holds what belongs to that view alone: the resolution threshold on
the Graph, *Add site* and *Draw boundary* on the Map. The **selection bar** at the foot of the canvas
appears when anything is selected (ADR-097 step 1; `keyboard/selection.spec.ts`), on the inverse
surface (the tooltip's `n11`-on-`surface-app` pairing) so it never reads as part of the right-click
menu, which sits on `surface-raised` (the owner, 9 October 2026). The timeline opens
folded: a 34px row — the chevron, *Timeline*, a small density strip of what the open timeline
holds and its date range in mono; open, its plot is 130px by default (DESIGN.md §5a; ADR-115 E4). Above the bar, the **classification strip** names the highest protective marking among what is
on screen, by the deployment's handling scheme's order, and is never hidden (`role="note"`, "Protective
marking"). Chrome is these three rows — strip, bar, view toolbar — and no more (ADR-097 Amendment 1);
their heights are DESIGN.md v0.3 §5a's (20, 44, 36; ADR-115 decision 9) and checked
(`keyboard/shell.spec.ts`, `design/shellSizes.test.ts`). The right panel is 340px by default and
resizable from 300 to 480; at a viewport of 1200px or wider it docks, open; below, it starts closed
and opens over the canvas (a shadow, no hairline), and the canvas toolbar's *Details* opens and closes
it either way (ADR-115 E4). The status bar (26px) sets its counts as pairs 16px apart, with no
separator, and a tip at the right with *Next tip*, outside the counts' live region.

Four rules govern this layout, and they are what make it an analytical workspace rather than a
set of widgets:

1. **One working set, many views.** Graph, Map and Matrix are three renderings of the same
   graphology instance. Switching view never refetches and never loses selection.
2. **Filters dim, they do not remove.** A filtered node stays in place at 12% channel mix with
   its label dropped. Removing nodes destroys the analyst's spatial memory of the network, which
   is most of what they are actually using to navigate.
3. **Everything cross-filters.** The brushed window's own fill is translucent (a 12% tint of its
   border's token), never an opaque surface — the selected zone is the one whose trend the analyst
   wants to read, so its bars stay visible while everything outside dims (the owner, 9 October
   2026; `Timeline.test.tsx`'s translucent-fill case). A brush on the timeline dims the graph, restricts the map and
   recomputes the histograms. A lasso on the canvas filters the timeline. A histogram bar click
   filters everything. This is the Gotham pattern and it is the core interaction of the product.
   It holds however the analyst signed in: the deployed Glass gets its token after it opens, so
   the brush's dimming is proven to reach the status bar on that path
   (`App.crossfilter.test.tsx`; found 8 October 2026, when it dimmed nothing there).
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
(28px, a hairline below; the row itself is what a pointer drags — no grip glyph, ADR-115 E4): the panel's name at `--fs-12` 600 in secondary text, and a menu
button, *Arrange the {panel}*, whose menu holds *Move up* and *Move down*. The panel's own title is not
drawn a second time inside it. Dragging the header onto another panel's place does the same as the
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
*Properties* (then *Picture*, *Relationships*, *Shares contacts*, *Neighbourhood risk*, *Provenance*,
*Source*, *Judgements*; with no node, *Judgements* open); the Query
builder its *Pattern* with *Preview* and *Run* (then *Add to the pattern*, *Connect* once there are two
nodes, *Save and load*); Metrics its *Ranking* (then *Community detection*, *Filter*). Parts open independently.
A link-menu choice opens its part; opening *Change this link* opens the form. A folded part keeps what
is half-written in it. The three panels are denser than the rest of the Glass: body and controls at
`--fs-12`, titles at `--fs-13`, padding at `--sp-8` and `--sp-4`. Reachable by keyboard
(`keyboard/inspector.spec.ts`, `keyboard/query-builder.spec.ts`, `keyboard/metrics-panel.spec.ts`).

**What the Inspector shows (ADR-097 step 1).** With **one node** selected, its header is the node as
the canvas draws it (shape in its channel's colour, then the type), its name as a literal value in
mono and its own marking as a badge (ADR-115 E4); its parts are *Properties* (open, keys in a 96px
column), *Picture* (only for a type a picture may depict, §3),
*Relationships* (its links in view, by type, most first; then "Drawn in this view. Expand counts the
rest in the store before anything is drawn." and *Expand*, which goes through the canvas's own
preview and cap), *Shares contacts*, *Neighbourhood risk*
(ADR-109 phase E, below), *Provenance* (with the stroke the canvas draws it with), *Source* and
*Judgements*. With **several**, they are shown together, not the first
alone: *Summary* (open: counts by type, and every property they all share with one value), *Selected*
(ADR-093's list: centre on one, take one out) and *Links between them (n)*, by type. With
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
Alerts, Ownership, History and Proposed types are on the rail; the resolution threshold, named **Match strictness** for what
the analyst sets with it (ADR-097 step 3), is on the Graph's view toolbar. Search is at least 280px
wide.

Every menu opens on Enter or Space, closes on Escape (focus returns to its button), on a click
outside it, and when keyboard focus moves outside it, so it never traps a keyboard user.

### 2.1 Investigation selection on load — proposed, not settled spec

**Built (ADR-052 Amendments 5 and 12):** the Glass shows a picker of the cases the account holds a
level on, and the Cases drawer holds "Who can open this case" — the Share panel, where a case's
Author gives an account (named by account id, as the Admin area shows it) Viewer, Editor or Author,
and removes it; anyone else holding `share_case` sees only their own level. The load order below
is what resolves the case on load.

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
`sessionStorage` step. **Once the account is known, the id is checked** against `GET
/v1/investigations/{id}`: refused (403/404), it is dropped and the case picker shows; a failing or
unreachable server keeps it. Until 9 October 2026 it was not checked, and signing in as a second
account in the same tab reopened the first account's case, every panel was refused, and a panel
that took the refusal's body for data blanked the Glass. A panel never takes a refused response's
body for its data.

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
`&view=ingest` for its Ingest Studio tile. The Ingest Studio is a view of the Glass, reached from the
left rail, so the two tiles differ only in this parameter. It works only within a case: with none
open it says so rather than calling routes that belong to one (ADR-099 Amendment 4 decision 5). `from=launcher` tells the Glass that the person has just
signed in there, so it starts its own sign-in without waiting for a click; the identity provider
already knows them, so no password is asked. If that cannot be done (no identity-provider session,
or it cannot be reached) the sign-in screen appears as before, worded for the Ingest Studio when
that was the tile pressed. `view=ingest` opens the Ingest tab after the sign-in, remembered in
`sessionStorage` for ten minutes because the query does not survive the identity provider's round
trip. **This grants nothing:** the Glass still signs in with its own client and the Conduit still
checks every request against the token's roles (ADR-050). A refused sign-in (an `error` parameter
on return) is shown and is never retried automatically. Only the Ingest tab can be requested
(`apps/workspace/src/auth/launcherHandoff.ts`, `App.test.tsx`).

### 2.3 What a case reads (ADR-099)

A case reads only its own datasets, on every read, in the Conduit: search, suggestions, expansion,
the query builder, paths, Explore and the canvas itself, and what belongs to a dataset is offered only
in cases reading it: saved patterns, watches and their alerts, Studio recipes and source files, and
the link types analysts propose (ADR-099 Amendment 3). The one exception is the types of the
OspreyFlow default dataset (`default.yaml` and every promoted type), which every case reads. The Glass
shows and asks; it enforces nothing.

- **A new case** (the case picker and the case switcher) asks *What can this case see?* as a
  first-class choice (ADR-099 Amendment 8): *Start empty — it holds only the data you load into
  it* (the default), or *Read existing data…*, which reveals the unit's datasets as boxes to tick,
  kept in the order ticked, each named by its name alone (names are unique, Amendment 6; a raw id
  in the list reads as noise). Returning to *Start empty* forgets what was ticked. The read-only
  "reads …" summaries keep the dataset id, where comparing records needs it.
- **A new case also offers *Domain models*** (ADR-126): three boxes, labelled as the Studio labels
  the packs. With none ticked, "Bespoke POLE (the core model)" is said beside them. The case is
  created with the list shown.
- **The case picker** says what each case reads beside its level ("reads Enron corpus · author").
- **The Cases drawer** ends with *Data this case reads*: the open case's datasets, to every reader.
  Its Author is offered *Change what this case reads*, a list to tick and *Save*, which will not save
  a case reading nothing; the page reloads after a change, since every read in it has changed.
- **After it, *Domain models*** (ADR-126): the case's packs by their labels, to every reader.
  - **Who may change them.** An Author holding `share_case` is offered *Change domain models*, the
    boxes and *Save*.
  - **After a change** the page reloads, since the Reports figures and the Trends options follow.
- Search, the query builder, paths and the node actions are asked of the case
  (`/v1/investigations/{id}/...`), so the Glass passes the open case to each.

`keyboard/case-datasets.spec.ts` walks both forms by keyboard, including the two domain-model
steps (`choose-a-cases-domain-models-when-creating-it-by-keyboard`,
`change-a-cases-domain-models-by-keyboard`); `CaseDatasets.test.tsx` and `CaseDomains.test.tsx`
the rest.

## 3. The five analytical capabilities

### 3.1 Network analysis

| Requirement | Implementation |
| --- | --- |
| Expand a node's relationships | Context menu on right-click, headed with the node's type and name and closed by a click elsewhere or Escape (a list, so long edge-type names stay readable; the browser's own menu is suppressed); items generated from the ontology's edge types valid for the node's type, each with a live count, or `count unavailable` if the preview failed; actions with no count show none. A double-click on a node (or Enter on a focused one) expands its neighbours across every edge type, except on a Document, which opens to read (ADR-092; its right-click menu still expands it) |
| Search Around | Multi-step, filtered traversal builder — `Person → uses → Endpoint → communicated with (≥5 events, in brush window) → Endpoint → used by → Person`. Preview count before committing to the canvas |
| Pathfinder | Select two nodes, get k-shortest paths; paths render with the on-path node state (2px primary stroke, edges thickened), everything else dims to 32% |
| Find connections | A side panel (ADR-116): From and To by search or from the selected node; the fewest degrees connecting them said in words, routes listed by degree and widened one degree at a time to eight, ten of more said as such; a route put on the canvas marks its nodes with their degree from From |
| Subgraph isolation | Select nodes (by lasso, or by clicking with Shift, Ctrl or Cmd held to add one at a time; a plain click selects one node alone), then *Branch to a new case* on the selection bar, or *Branch selected (n)* in any selected node's right-click menu (ADR-084 Amendment 1, ADR-097 step 1) — and the selection opens as a new case, listed under its parent in the *Cases* drawer (§3.1h, ADR-084), with its own filter state; the parent is untouched. A bounding-box selection has no implementation yet |
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

**How a label and a node are drawn (ADR-097 step 2; DESIGN.md v0.3 §5a).** A label is set at `--fs-11` in the theme's
primary text: in mono (`--mono`) when it is a literal value — the chosen property is one of the type's
identifiers, or with no choice the node is named by its normalised value or its id — and in `--ui`
otherwise (a person's name, a thing's name, a document's title). A label longer than 28 characters keeps its first 19 and last 4, an ellipsis between, so
both ends of an address or an account number stay readable; the full text is in the Inspector. A label
that would run past the canvas's right-hand edge is drawn on the node's left instead, and never before
the left edge. At 100% (a camera ratio of 1) a node is 20 pixels across in an uncrowded view, measured
from the painted pixels (`keyboard/canvas-look.spec.ts`); the far overview keeps nodes small, and
a crowded view still shrinks them as before.

**Zoom, the legend and the grid (ADR-097 step 2; ADR-115 E4).** At the canvas's top right, below the
toolbar, the legend and under it a zoom group named *Zoom*: *Zoom out*, the zoom as a percentage in mono
(100% at the camera's starting scale, following every move), *Zoom in* and *Fit to view*; F with the canvas focused fits too (the whole graph
framed, as an arrangement frames it, inside an 80px margin so the outermost nodes clear the toolbar
above the canvas and the selection bar below it — Sigma's 30px framed them under both, found live 11
October 2026 and checked by eye, since jsdom draws no WebGL). The legend (at the top right, above the zoom group) lists each type in view as the canvas
draws it (shape in its channel's colour), with how many, most first; *Legend* folds it to its title.
**Under the types, the links in view (ADR-117):** each link type with a line in its declared colour
(one of the nine channels, else the ordinary line), its name and how many, most first, and a checkbox
that leaves the type out of the view or brings it back — the "links to include" a prison analyst
filters a network by. Leaving a type out hides its links in this tab only, as hiding one link does:
nothing is recorded, nothing is removed from the working set, and every count stays what it was
(`CanvasLegend.test.tsx`; the walkthrough "the legend leaves a link type out of the view and brings it
back, by keyboard", `legend-leaves-out-a-link-type-by-keyboard`).
**The legend floats** (the owner, 14 October 2026: "the legend is hiding the button behind, can the
legend panel be a floating panel"): its grip, *Move legend*, drags it, or with the grip focused the
arrows move it 16px (64px with Shift) and Home puts it back; it never rises above its dock, so it
cannot cover the toolbar, stays inside the canvas, and where it was put is kept in this browser.
Moved, it is an overlay — a shadow, no hairline. **The corner sits below the toolbar as drawn**: the
toolbar wraps to a second row on a narrow canvas, and the canvas measures it, so neither the legend
nor the zoom group covers that row (`keyboard/keyboard.spec.ts`, at a width where the toolbar wraps). The
graph canvas, and no other surface, has DESIGN.md §9 exception 4's measurement grid: 1px `--border-subtle`
lines mixed to 40% on a 16px lattice (DESIGN.md v0.3), fixed to the screen. *Grid* in the toolbar's Show group switches it off and on
(pressed while it shows); the choice is kept in this browser (owner, 6 October 2026). All of them come after the view's own controls in Tab order.
Reachable by keyboard (`keyboard/keyboard.spec.ts`); the painted grid is read from the pixels
(`keyboard/canvas-look.spec.ts`).

**The canvas toolbar (ADR-097 step 2, design review item 12).** The canvas's own tools are one docked
row along its top edge, *Canvas tools* (36px, `--surface-panel`, a hairline below and no shadow:
DESIGN.md §6), in labelled groups: **Select** (the lasso), **Layout** (the layout, *Bubbles by* for
Clustered bubbles, *Arrange* — a re-run icon (ADR-115 E4) — which arranges again with the layout chosen), **Show** — one segmented control of *Communities* (pressed while on),
*Labels* and *Icons*, followed while Communities is on by what it found and *Collapse all* / *Expand
all* — and, at the right-hand end, **View** (*Hide selected link*, *Show hidden links (n)*, *Show links among all*, *Clear view*,
*Add files*), then the case's last change ("Last change: Expanded HALE, Marcus by one hop, yesterday", from
the history the History drawer lists; hidden below a 1100px window) and *Details* (ADR-115 E4, E6). A menu's panel and *Clear view*'s confirmation are laid over the canvas under their
button, as overlays with a shadow. The toolbar's controls are quiet buttons at `--fs-12`; a pressed or
open one is primary text with a 2px underline. Checked in the browser (`keyboard/canvas-look.spec.ts`:
the groups, one row, no shadow); each control keeps its own keyboard case.

**Moving nodes by hand (owner, 6 October 2026; the spec was silent).** Dragging a node moves it, and moves
the whole selection when the node is in it; the camera does not pan while a node is held, and the click
that ends a drag does not change the selection. Only the main button drags: a right-click opens the menu and moves
nothing, and a drag ends when no button is held any more, wherever it was released. A node is moved with its resolution cluster, which is drawn
as one place. Shift with an arrow key moves the selection 8 pixels on screen, 32 with Alt too (the
keyboard route, rule 13). A node placed by hand stays where it was put when a layout runs for nodes added
later, in every layout; *Arrange* lays everything out afresh and forgets the placements. Positions belong
to the view and are not sent to the server (`keyboard/node-drag.spec.ts`, `keyboard/keyboard.spec.ts`).

**Links among what is on screen (ADR-098 decision 1).** An expansion of at most 100 new nodes into a view
of at most 2,000 also draws the links among its nodes and the rest of the view, so expanding a person shows
who among their correspondents wrote to each other, not only a star; when those links would pass the working
set's cap none of them is drawn and the canvas says so. For larger views, *Show links among these* on the
selection bar (two or more selected) and *Show links among all* in the View group draw them on demand, all
or none, and say how many (`keyboard/selection.spec.ts`, `keyboard/keyboard.spec.ts`). The selection bar's
control reads as a sentence, *Show links* · *− direct +* (ADR-098 Amendment 4; the owner, 14 October 2026:
"more elegant and intuitive"): − and + step **Degrees of separation** from *direct* (the default) to
*within 6*, the reading said as it changes; the bar is one line after the reference — quiet actions with no
box of their own, *Clear* after a hairline — and never wraps. Past direct
the routes between each pair of the selected nodes, at the fewest degrees that join them up to the chosen
one, are drawn with their nodes, and the notice says the links and nodes added, the pairs not connected
within it, and the pairs with more routes than were drawn. Above 8 selected it keeps to direct, and + says why.

**Hovering a link (ADR-115 E5, review item 11).** With the pointer over a link, a tooltip by the pointer
names its type and how many links of that type join the same two entities ("3 links of this type between
these two"), and goes when the pointer leaves (`keyboard/link-hover.spec.ts`). A keyboard user reads the
same from the Inspector with the link selected.

**Questions to the model, in a branch (ADR-098 decision 4).** While the selection holds a Document, the
selection bar offers *Ask the model about these…*: it branches the selection into a new case named
"Questions on <n> documents" and opens that case with its *Questions* panel open (the case address carries
`view=questions`, kept through the sign-in round trip as the Ingest tab is). The panel is also on the left
rail as *Questions*, for any case. It lists the case's questions in order, each with its answer, *Draws on*
buttons for the Documents it cites (each opens the reader), and the model's proposals with *Accept* and
*Reject*; a proposal whose words are not in the Document the model named is left out and counted. The
question box asks on *Ask* or `Ctrl+Enter`. Documents together longer than 80,000 characters are refused
with both figures in words, and the question is kept (`keyboard/questions.spec.ts`,
`keyboard/selection.spec.ts`).

**Where to start in a case's data: Explore (ADR-100).** While the canvas holds nothing, it shows *Where to
start* over the canvas; the same panel opens from the left rail as *Explore* at any time. Its blocks fold
(ADR-100 Amendment 9): *What this case holds* opens first and the rest are headings until opened, one screen
tall; in every block a row's facts are text and the pressable thing is a button. A ranked node's *Add…* asks
how much comes to the canvas: just the entity, its 25 or 50 busiest links (the steps below its degree), or
all of them through the canvas's own expand and its large-expansion question — the budget reads the node's
own busiest links (`node_id` on `/explore/busiest-links`), under the whole-case ranking's access rules. It
shows, for the case's datasets and the analyst's clearance only: *What this case holds* (the count of each entity type and
each link type, types with none left out); *Most connected* (the 10 nodes with the most visible links, saying
"The 10 most connected of N", with *Show n more* until "All N shown"); and *By entity type* (each type and its
count, opening to its 5 most connected and paging the same way); *Busiest links* (the links that stand for
the most records, "alice → bob · Communicated with · 50 emails", picking one puts the pair and their link
on the canvas); and *Busiest days* (the case's days with the most events, picking one sets the
timeline's window to that day and opens the timeline); and *Groups and bridges* (the largest groups, each
"Group of 3,669 · mostly Endpoint · around alice@…", and the nodes whose links reach the most other
groups, each counted against how many there are; a case too large to group says so with both figures); and
*What's new* (the latest loads into the case's datasets, each with its recipe, what it wrote that the analyst
can see and when, "The latest 10 of 14 loads"; and the nodes colleagues confirmed, and marked for suppression
with their reason, the latest first and each counted; a load is named, not picked, since one can hold the whole
case); and *Starter questions* (chains that suit the case's types, "Person → Endpoint → Endpoint, by “Uses”
then “Communicated with”", each run with one action: what it matches and the links among them go on the
canvas, all of it, or nothing with "At least 1,000 match" past the query builder's limit). Every node in it is a button that does what
choosing a search result does: puts it on the canvas, draws outwards from it and selects it. The figures are
the Conduit's (`/explore/counts`, `/explore/most-connected`), kept once counted and counted again after
a change, and the panel says when ("Counted at 09:05 UTC", ADR-100 Amendment 3); they are never
reckoned in the browser
(`keyboard/explore.spec.ts`, `src/explore/ExplorePanel.test.tsx`). A node's
Inspector has *Shares contacts* (ADR-100 Amendment 8): for each link type its type starts, "Who shares two
contacts by “Communicated with”?", then the ten who share most, "bob · shares 446", of how many; a pick puts
the two, what they share and the links among them on the canvas (`keyboard/inspector.spec.ts`).

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

**One entity's own picture (ADR-105).** An entity whose type a picture may depict (`DEPICTS`'s
`to`) has a *Picture* part in the Inspector: its current picture, *Set picture* (a file, its marking
and its legal basis, both required) and *Remove picture*. Unlike the type's picture, it is evidence
held in the case on the server, so every analyst who may see it sees it. The canvas draws, in order,
the entity's own picture, the analyst's picture or drawing for the type, then the ontology's icon.
The pictures of the nodes in view are asked for when the view changes
(`canvas/entityPictures.ts`), fetched with the analyst's token, and drawn small through the same
thumbnail and data-address check as a type's picture. Reachable by keyboard
(`keyboard/inspector.spec.ts`, `set-an-entitys-own-picture-by-keyboard` and
`remove-an-entitys-own-picture-by-keyboard`). Not proved: the entity's picture reaching the canvas's
pixels, as the type's picture is; the precedence is a unit case (`canvas/entityPictures.test.ts`).

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
the menu's next entry, *Put the emails on the canvas* (*Put the messages on the canvas* for phones), puts the
emails inside the timeline's brushed window (all of them when nothing is brushed) on the canvas as
Documents, linked to both addresses, and says how many (ADR-092; split from *Show emails (n)*, which now
only lists them, on the owner's ask of 6 October 2026, since one entry doing both was named for one); past
the working set's cap nothing is added and the message says by how much and to narrow the timeline.
A link whose events carry no text (a PaySim transaction, an HMP incident) keeps the Inspector list
only. A link between two phones (`endpoint_kind` `msisdn`, `imsi` or `handle`) is named for its
**messages** (ADR-094): *Show messages (n)*, "· 3 messages", the Inspector's **Messages** list,
where a message is named by its first words and a call by its length; *Show messages* puts the
messages with text on the canvas as Documents titled by their first words, and says how many events
had none (a link of calls only is said to have none, as a notice). Proved by keyboard in `keyboard/link-menu.spec.ts`.

An opened email offers extraction (ADR-089 step 3) as two equal, always-offered buttons named for
what they do (ADR-098 Amendment 3): *Quick scan* runs the fast recogniser (Stanza, ADR-098
decision 2), whose findings carry no score and say *found by Stanza*; *Deep read (model)* runs the
deployment's extraction model (`models.extraction`, decision 3), whose findings carry a confidence
each and are added to those listed. The email becomes a `Document` node linked to its sender and
recipient by `MENTIONED_IN`, both appear on the canvas at once, and the findings are listed as
suggestions. Nothing a model finds reaches the graph until a person
accepts it (rule 5): *Accept* on one finding writes it as an inferred node with a `MENTIONED_IN` link to the
email, both onto the canvas, where it is confirmed from the Inspector as any inferred node is. *Reject*,
beside it, marks the finding rejected and writes nothing (owner, 6 October 2026), in the Inspector's list
and in the reader alike. Reachable by keyboard
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

**The link's handling is changed there too (ADR-102).** The form offers the classification, handling
code, action code and sanitisation code from the deployment's scheme, never the units. A raise is an
ordinary change. A choice lower in any part says so ("This lowers the link's classification: only an
Author may, and it is recorded") and saves only once *I mean to lower this link's handling* is ticked;
the Conduit refuses an Editor who is not an Author. The history says "Handling: SECRET, C → OFFICIAL, P".
A link written again by a load never lowers its handling (ADR-102 decision 1), so this form is the one way
down (`keyboard/inspector.spec.ts`).

**When no type fits, an Editor defines one there (ADR-090).** The types the form offers are the case's
own (`GET .../link-types`): the ontology's (the default dataset's), and those proposed in any case
reading one of this case's datasets (ADR-099 Amendment 3 decision 2), each proposed one marked
"(proposed)"; one proposed before that amendment and not yet placed keeps ADR-090's rule. **Define a new
type…** asks for a name in sentence case ("Known to"), from which its ID is made (`KNOWN_TO`, which may
be edited), whether it goes either way round, a colour and a thickness (both optional), and why no
type fits; the ends are the link's own. Proposed, it is chosen at once in the form and, being
probabilistic until an administrator decides, its basis is stated, not asked; on the canvas its links
are drawn dotted in its own colour and thickness, named by its label. The Glass reads the case's types
when a case opens and again after a proposal or a decision. A refused name is said in the server's
words. **An `osprey-admin` holder** also has **Proposed types** on the left rail: their own unit's
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

### 3.1h Branch selected, and the case's branches in the Cases drawer (ADR-084, ADR-097)

Selecting nodes shows the **selection bar** (ADR-097 step 1, below), whose **Branch to a new case** sends the nodes to a **new case of their own**, holding those nodes and the links between them, and opens it. The case you branched from is left exactly as it was. A branch is a **copy** made at that moment: later changes to either never touch the other. It reads its parent's datasets (ADR-099 decision 3). A selected Group Node stands for every member of its group, so choosing one chooses them all. What the new case holds is re-checked against the branching analyst's own clearance, as every read is: a node they may not see is not copied, and a request that leaves nothing to copy says only "None of the selected nodes could be branched", whatever the reason.

**Seeing and working the selection (ADR-093, ADR-097).** A selected node is drawn larger with a bold
brass ring (§4's table). While anything is selected, the **selection bar** floats at the bottom centre
of the canvas (an overlay: a shadow, no hairline): "n selected", the only live count of the selection
in the page, then *Expand* (each selected node in turn, each through its own preview and the working
set's cap), *Branch to a new case*, *Remove from view* and *Clear* (with its *Esc* key cap); Escape
clears, on the bar or on the canvas itself. *Expand* is the bar's one primary action, in brass, and the bar's
count the page's only one — the Inspector's several-node view repeats it nowhere (ADR-115 E4). The canvas
shows its own focus ring (2px brass, inset) and its accessible description says what is selected
("Selection of 2. Arrow keys move between nodes, Escape clears."). It replaces the
corner chip and the toolbar's *Remove selected* and *Branch selected*. A branch is named "Branch of
<case> (n nodes)", or "Branch of <case>" for the whole view; never a selection count with a middle dot. When more than one node is selected, the Inspector lists them
by name under "Selected (n)": choosing a name centres the canvas on that node and leaves the
selection as it was, and × takes it out. Proved by keyboard in `keyboard/selection.spec.ts`
(registry `SELECTION_ACTIONS`); the ring by painted pixels in `keyboard/selection-look.spec.ts`.

The selection is built with the lasso, or by clicking nodes with Shift, Ctrl or Cmd held (each adds the node, or takes it out again). *Branch to a new case* is on the selection bar and, for any node that is in the selection, *Branch selected (n)* is an entry in that node's own right-click menu (ADR-084 Amendment 1); a node outside the selection does not offer it. Both reach the same route; `keyboard/keyboard.spec.ts` proves each by keyboard.

Each branch is a case saved for the analyst who made it (they are its Author, and it is visible to nobody else until they share it). It starts with the resolution threshold, layout and timeline brush of its own, not shared with the case it came from. The events behind the links it copied (the timeline's counts, *Show emails*, an email to extract from) are read from the case they were loaded into, for the links the branch holds, wherever the analyst can see that case; nothing is copied (ADR-084 Amendment 2).

The cases and their branches are one tree (ADR-084 Amendment 4), shown alike in the top bar's case
menu and the **Cases** drawer on the left rail: each original case once, its branches indented beneath
it, a branch named for what it holds and when it was made ("2 nodes · 14 Oct 16:40") until renamed; the
case on screen is marked "you are here", and on a branch the menu's button reads *case › ⑂ branch*. A
branch's ⋯ offers **Open**, **Rename** (its Author) and **Delete** (its Author, or an administrator of
the unit) in place; Delete asks once — "It leaves every list for everyone; the case it came from is
untouched" — and is the same soft remove as any case. Deleting the branch on screen returns to the case
it came from (`keyboard/case-tree.spec.ts`).

Opening another case or branch from the drawer reloads the page, as every case switch does (§1): the working set, timeline and delta stream are each built once per case. The expansions and filters of a case are kept on the server, so they are still there; where nodes sit on screen and what was selected are not. Having several canvases live in one page, so that switching is instant and keeps the layout, is a later step (ADR-084).

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

The panel opens on **Ranking**, with **Community detection** (named so since ADR-097 step 3, apart from
the canvas's *Communities* view) and **Filter** folded; parts open independently, more than one at a
time, and a folded part keeps what it holds, so nothing is fetched again on opening it (ADR-096
decisions 0 and 4, replacing ADR-070's one-at-a-time strip).

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
filtered afterward, and the Glass is never shown an unfiltered count. **Patterns are saved and
versioned:** the Query builder's *Save this pattern* saves it (each save of the same pattern a new
version) and *Load a saved pattern* lists the analyst's own. A pattern is private to its owner and
belongs to the dataset of the case it was saved in, so it is listed and loaded only in cases reading
that dataset (ADR-099 Amendment 3). Sharing a pattern is not built.

**Hotlists and watchlists.** A list of identifiers with an owner and a review date. Any ingest
that touches a listed identifier raises an alert. The CoLP journey turns on exactly this — a SIM
seized in a warrant matches a number already logged, and an officer is notified. Alerts carry
the matched identifier, the triggering document, and a one-click jump into a pre-populated
investigation.

**Saved-pattern monitors.** A saved visual query run on a schedule against new data. Matches
raise alerts with the same shape as hotlist alerts. This is the CoLP deck's "automatic daily
searches" requirement.

**A watch belongs to a dataset (ADR-099 Amendments 3 and 4).** A hotlist belongs to the dataset of
the case it was made in, a monitor to its saved pattern's; each raises alerts only on that dataset's
data, and the *Watches* panel lists only those of the open case's datasets. A match in another
dataset raises nothing at all. Opening an alert makes a case that reads the alert's dataset.

Every alert names the rule that fired and shows the evidence. Borrowing from the way fraud
decisioning products present their scores: an alert that cannot explain itself is an alert the
analyst will learn to dismiss.

**Typology rules and the *Alerts* place (ADR-109).** A case's typology rules (structuring, rapid
movement, circular flow — each a closed set of parameters, never an expression) judge its loads,
before commit or after as each rule declares, and raise alerts to **the case team's queue**: the
*Alerts* place on the left rail, after *Watches*. It opens on the queue (open and claimed by
default; closed and all by choice), each alert named by its typology and its finding in words, the
entities named as the reader sees them — an alert any part of which the reader cannot see is not
shown or counted. Opening one shows **what fired it**: the finding, when the rule ran (as the data
loaded, before commit, or after), the span when it has one, and a table of the transactions it cites
(when, from, to, amount) — or, for an alert that cites no transactions (a KYC alert), a list of the
parties it concerns, each named with its type (an empty transactions table once stood there; found
live, 11 October 2026). An alert with no node on the graph says so: what it concerns is held under
markings no single marking covers. Where the alert stands is one sentence — "Open", "Claimed by you",
"Closed as a true positive: <reason>". An Editor claims it, releases it,
puts it **on the canvas** (its node, its entities and the links it cites, all or none; the view
switches to the graph with those nodes selected; the alert's node is labelled by what its rule
found, "KYC screening alert", never by its id — rule 7) and closes it as a true or false positive with a
required reason; a true positive confirms the alert's node (rule 5) and, for a screening alert,
the match it found, so due diligence then says "confirmed" rather than "possibly" (ADR-109
Amendment 7). A Viewer reads only. Its
other tabs: **Rules** (every rule, what it looks for in words, where it runs; an Author deploys —
typology, parameters, before or after commit, a time budget for before — and retires), **Held
rows** (Editor and above: rows a failing pre-commit rule held, grouped by load, with the rule and
why; an Author who also holds the studio role Loader releases a load's rows, which load and are
judged again but never held again, or an Author rejects them with a reason — `09_INGEST_STUDIO.md`
§6) and **Audit** (an Author, or the
unit's administrator: the rule audit, fifty entries at a time, the total said). Every action has
its case in `keyboard/alerts.spec.ts`, under its own registry `ALERTS_ACTIONS` (rule 13).

**Ultimate beneficial ownership: the *Ownership* place (ADR-109 phase C).** After *Alerts* on the
left rail. An organisation or account is found by name (the case's own suggest), and traced: a line
naming the beneficial owners at the threshold (25% unless changed; a person holding control is one
whatever the share; a person whose share is partly unknown is "possibly more"), a warning for each
circle of cross-holdings ("traced once, not round and round"), and a table of every party with a
chain to the entity — its type, its cumulative share ("at least" when part of it is unknown), its
notes, and its chains, each in words, owner first, with every link's percentage ("share not
stated", "controls") and the chain's product. *Show the structure on the canvas* puts the parties and
links there (Editor), and the graph opens with them selected. Nothing it shows is written to the
graph. Every action has its case in `keyboard/ownership.spec.ts`, registry `OWNERSHIP_ACTIONS`.

**Due diligence (ADR-109 phase F).** The same place finds a person too, and for a person or an
organisation shows its KYC status and baseline risk above the ownership trace: verified or
unverified, the risk band and score, each factor in words with its weight, and each verifying
document with its state — all computed by the Conduit as the reader sees the graph, at that moment.
The *Alerts* place's Rules tab deploys the KYC rules (screening — with *Screen beneficial owners
too* —, shared contact details, verifying documents) as it deploys the typologies.

**The no-code typology builder (ADR-109 phase D).** A typology is drawn where patterns are already
drawn — the Query builder (§3.3) — and saved there; in the *Alerts* place's Rules tab an Author picks
*Drawn pattern*, chooses one of their saved patterns and the largest match to alert on, and deploys
it. It always runs after each load commits (said in the form, with no choice offered). Deploying has
its own keyboard case (`deploy-a-drawn-pattern-rule-by-keyboard`).

**Neighbourhood risk (ADR-109 phase E).** The Inspector's *Neighbourhood risk* part, for the
selected entity, asks on request (*Score this neighbourhood*) and shows the score in words — alerts
within two hops, halved per hop, from the last ninety days, in what the analyst can see — and each
contributing entity with its distance, its alerts' count and what it adds, its alerts' summaries
listed one to a line beneath it (three alerts' words joined into one sentence could not be read). Nothing is
stored or drawn on the node: the score is a read, and another analyst may read another. Its keyboard
case is in `keyboard/inspector.spec.ts` (`score-a-neighbourhoods-risk-by-keyboard`).

**The Reports view (ADR-111).** A third entry in the top bar's view switch — *Graph · Map ·
Reports* — for people who read rather than investigate (a case Viewer and above). It draws the case's
figures as the Conduit counts them for this reader (`GET …/reports`): the alerts of the period
("3 alerts in the last 12 weeks"), alerts raised each week by typology (stacked bars in the channel
tokens, with a key), open alerts by age (under a day, 1 to 7 days, 7 to 30, over 30), outcomes by
typology (open, claimed, true, false), and — only when the server sends them, to Editors and above
— held rows. What follows depends on the case's domain packs (ADR-126):
- **A case with the AML and fraud pack alone** shows the customers holding a verifying document by
  KYC status and risk band, and no POLE summary.
- **Any other case** shows a *POLE summary*: one line per class (Person, Object, Location, Event,
  Organisation) with its types beneath, an "Other (not in this ontology)" line when the case holds a
  type the ontology no longer knows, and its links. Its footnote reads "Records before resolution,
  counted at {time}; not for the period."
- **A mixed case** (for example AML and fraud with Crime) shows both.

A line says the figures are counted for the reader. *Period* chooses the last 4, 12, 26 or 52 weeks and is asked of
the server; *Download the figures (CSV)* fetches the dashboards' feed, each read of which is in the
export ledger. A report past its bound says so in words with its option ("Choose a shorter period"),
never a partial chart. Every action has its case in `keyboard/reports.spec.ts` (`REPORTS_ACTIONS`);
the view switch itself, never proved by keyboard before, in `keyboard/shell.spec.ts`
(`views-chosen-by-keyboard`).

**The Glass follows the person's rights (ADR-112).** It reads `GET /v1/me/rights` at sign-in and
leaves out what it would only be refused — never in place of the Conduit's check
(`rights/visibility.ts`): the rail shows *Watches* for keep_watches, *Alerts* for read_alert_queue,
*Ownership* for trace_ownership, *History* and *Explore* for investigate, *Questions* for ask_model,
*Proposed types* for manage_ontology, *Ingest Studio* for edit_pipelines (an analyst adds files from
the canvas), *Dashboards* for read_reports, *Admin* for any administration right; the view switch offers Graph and Map for
investigate and Reports for read_reports, and a person who may not investigate (a Reports Viewer)
lands on Reports; the Reports view's download is offered only to holders of read_report_feed.

**Superset dashboards inside the Glass (ADR-111 Amendment 3).** The Reports view has two tabs,
*Figures* (the case's own counts, above) and *Dashboards*; the rail's *Dashboards* place shows the
same thing full width. Both list only the boards the Conduit says this person may open
(`GET /v1/reports/dashboards`) — those whose every figure they could count themselves — and draw the
chosen one through Superset's embedded SDK (`@superset-ui/embedded-sdk` 0.4.0) in a frame, with a
five-minute guest token the Conduit issues and the SDK asks for again before it lapses. Superset's
menus never appear, nor its own title or each chart's menu, and the board is drawn in
Superset's theme generated from `tokens.css`, in the Glass's current mode and following a switch
(ADR-111 Amendment 4); a refusal is said in words; with none to open, the panel says why one would
appear (`reports/EmbeddedDashboards.tsx`, `reports/ReportsPlace.tsx`; `keyboard/reports.spec.ts`).

**Trends, report packs and their distribution (ADR-113, Amendments 1 to 3).** The Reports view's
tabs are *Figures*, then — each only with its right (`rights/visibility.ts`) — *Trends*
(run_analysis), *Packs* (record_assessment), *Published* (read_reports), then *Dashboards*.
*Trends* builds a trend from `GET …/trends/options` only, which offers the core types and those of
the case's own domain packs (ADR-126):
- **Outside types.** A saved trend that uses a type outside them is marked "Uses link types outside
  this case's domain models", and still runs.
- **The domain sentence.** Unless the case holds all three packs, the form says which domain models
  the case has and that an Author can change them in the Cases drawer, beside "Data this case
  reads".

The form has event types as checkboxes, *Count* or
*Sum* of a number property every chosen type declares, week or month, weeks back, a series by event
type or a category, up to five filters from the declared values — with nothing typed as a formula;
*Preview* draws a bar per period, stacked by series with a key naming every series, the sentence in
words (the events counted, and those with no value left out of a sum) and the server's marking; past
a bound it says the three choices in words. A saved trend is chosen from the list, deleted, or added
to a pack. *Packs* lists the case's packs and creates one; the chosen pack shows its marking, its
versions in words (withdrawn ones with who and why, live ones with *Withdraw version n* and a
reason), "n items in this pack are withheld from you" when any are — never which — and its items in
order, each under a banner with its own marking, with *Move up*, *Move down*, *Refresh* (trend
snapshots only) and *Remove*; *Add an item* adds a saved trend, an assessment or a note with its
required marking; *Publish*, refused in words while an item is withheld from the publisher; *Show
history* shows the earlier snapshots. *Published* lists each pack's newest live publication and
shows it read-only — the Reports Viewer's view of packs. *Export PDF* (export) asks the Conduit for
the approved manifest, asks for a justification and originator reference when an item needs its
originator consulted, and prints the manifest from a hidden frame: a cover with the mark, then a
page per item under a top and bottom banner of that item's own marking (`reports/packExport.ts`,
styled with the light-theme ramp restated, every string escaped); the PDF is saved from the
browser's print dialogue. Whoever published, withdrew or exported is shown by name, the id only when the server had none
(ADR-106; Am. 3); the printed cover carries the mark's banner top and bottom, and a trend's periods
are said and printed as days, never timestamps; every period the trend's window touches is drawn
(Monday weeks or calendar months, UTC), an empty one as an empty bar and a "No events" row in the
PDF, never closed up (Am. 3). Entity items are drawn when present; adding
one from the canvas is not yet built. Keyboard cases: `keyboard/trends.spec.ts` (`TRENDS_ACTIONS`) and `keyboard/packs.spec.ts`
(`PACKS_ACTIONS`).

**The welcome page (ADR-115, E2).** Signed out, the Glass shows the welcome page of the design
handoff: the deployment's marking, a 48px header (the mesh mark, *OspreyFlow*, About, the theme), the
hero (what the product is, its four capabilities, a picture of a synthetic case drawn as the canvas
draws), the sign-in card, About (switchable off in `welcome.about`) and a footer naming the build
and only the documents the deployment links (`welcome.*`). The card never takes a password: its
button starts the code flow; with `governance.organisation_sign_in` set, *Continue with organisation
sign-in* goes straight to that brokered provider (`kc_idp_hint`) and *Sign in with an OspreyFlow
account* to Keycloak's form, which the OspreyFlow login theme draws. A hand-off from the Studio or
Admin titles the card for it; a refused sign-in says why in the card.

**Home (ADR-114 Amendment 5 point 9; ADR-115 decision 7, E3).** With no case open, every signed-in
person lands on Home (`design/handoff/OspreyFlow Home.dc.html`): a greeting naming the account, its
clearance and roles; the three places — *Glass*, *Ingest Studio*, *Admin console* — each with a
picture, its figures and an *Open* button with its key (G, I, A, page-wide, never while typing); a
place the person cannot use is dimmed and says "You need the {role} role for this. Ask an
administrator to add it." Only the first usable place's button is brass. *Needs your attention* lists
open and own-claimed alerts, rows still held and failing dashboard pulls, newest first, only for
usable places; *Recent cases* the person's cases with their level and what each holds as they see
it; *Ways of working* four habits. Every figure comes from the route its place already has, case by
case, counted as the reader — Home adds no read path; a case that refuses (403) is left out, one that
fails is said. *The Glass* goes to *Choose a case*, *Ingest Studio* to *Choose the case to load into*,
*Admin console* to the Admin area with no case; the mark returns to Home from anywhere.

**The Admin area (ADR-110 Amendment 1, ADR-112).** The deployment's administration inside the
running system, behind the same sign-in — *Admin* on the rail, or Start's *Admin* tile with no case
open — with a tab per right: *People and
roles* (each person's four roles as checkboxes, saved whole, other grants kept and shown; since ADR-114
Amendment 5, each person's state — disabled, or invited and yet to set a password — with *Access*
(clearance, unit and handling codes, edited in place), *Disable* (only after *Confirm disable*) or
*Enable*, and *Reset sign-in*; and *Invite a person*, whose answer is either "an email went to …" or a
one-time code shown once with what to do with it), *Dashboards*
(register a dashboard identity — its secret shown once — and remove one; its account id is what a
case's Author grants Viewer to), *System* (each component asked as the tab opens, with *Ask again*),
*Demo packs* (ADR-114 Amendment 5: each pack, its licence and credit, "Loaded, in …" only for a case
the administrator can open, and its `ospreyflow demo add` command with *Copy* — the page runs nothing).
Every action has its case in `keyboard/admin.spec.ts` (`ADMIN_ACTIONS`).

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
  for a reason the analyst cannot see. The strip returns the moment the case gains events. A case
  that only reads a dataset whose events another case holds says which, instead of that its data
  carries no dates: "The events of the datasets it reads are in …", naming only cases the reader can
  open (ADR-099 Amendment 9); the Trends tab carries the same note.
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
own detail message in place of a blank canvas when it 404s. When nothing in the view has a map position
(a case whose locations are on a site plan, not the map), the map opens on the basemap's own
centre and zoom, read from its PMTiles header, and says "Nothing in this view has a map position";
the graph layer is not bound, since with no extent it fitted the camera to an undefined box and
the map drew black (8 October 2026; `map/mapStart.ts`). Place labels need glyph files, which
`scripts/build_local_basemap.py` does not build yet; MapLibre fails a whole vector tile whose label
layer cannot have its glyphs, so without them the map drew nothing at all. The Glass asks for the
labels' first glyph range before the map mounts (`glyphsServed`, an HTML answer counting as none,
since nginx answers an unknown path with the Glass's own page) and leaves the label layer out when
they are missing: the basemap then draws unlabelled. **The glyph files** are installed into the
tiles folder's `fonts/` by `python -m scripts.fetch_basemap_glyphs --tiles-root <tiles>` (the
OpenMapTiles fonts release, pinned by SHA-256; only the fonts the style names); the renderer mounts
that folder read-only into the workspace, whose nginx serves `/fonts/` from it with a real 404 for
a missing range (until 9 October 2026 none existed and every map drew unlabelled).

The bundled basemap and its overlays (the heat layer, a trail, a boundary) take their colours from
the themed palette (ADR-070) and are drawn again when the theme changes: land the raised surface,
water the sequential ramp's second step, lines the strong border, labels the primary text. Until
9 October 2026 they used the dark theme's constants in either theme, with land and sea barely
apart, and the map read as a black rectangle in the light theme and in exported screenshots.

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

**Selected and on-path, combined — resolved here rather than left as a disclosed gap.** The code
that first implemented the two states differentiated a select-and-on-path node from a selected-only
one by stroke hue alone — a colour-only distinction, WCAG 1.4.1, for that one combination. Since
ADR-093 a selected node is drawn 1.6 times its size with its own brass ring and a surface-coloured
gap inside it (the table above), and on-path keeps the interaction ring and thickened incident
edges, so each state carries its own non-colour cue and the fix asks nothing new of the palette: **the two cues are independent and both apply when both
states hold.** A selected node on the active path shows its larger size, ring and gap *and* thickened incident
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
so only for one loaded before then, cut at 4,000 characters. An email offers *Quick scan* (since ADR-098 the fast recogniser, Stanza: people, organisations,
places, emails and phone numbers in about a second, each finding saying *found by Stanza*) and *Deep
read (model)* (the language model, slower and deeper, its findings added to the list, each with its
confidence) as equal buttons with a caption under each saying that much (ADR-098 Amendment 3), and
each finding's *Accept* and *Reject*, as the Inspector's email
view does, and the text is read again after an acceptance so the new entity is marked. A finding not
yet accepted is marked in the text where it sits, dashed and unclickable, from its own locator and
only where the words hash to its excerpt hash (ADR-098 Amendment 3); accepting it turns the marking
into the accepted entity's. Highlights fill at 18% of the type's channel (raised from the hull
convention's 8% — the owner, 9 October 2026: the types were too hard to tell apart — text colour
untouched), and a legend under the text names each highlighted type in its colour and says that
dashed means found, not yet accepted (`HighlightLegend`). Focus starts
on *Close*; Close or Escape returns to the canvas with nothing moved behind it. The text comes from
`GET .../documents/{id}/reader`. Tests: `src/reader/DocumentReader.test.tsx` and
`keyboard/reader.spec.ts` (Enter opens it, Escape closes it, Extract, Accept and Reject by keyboard). **Marking an
entity by hand (ADR-098 decision 5):** under the text, *Mark an entity* takes *Words to mark* (filled by
selecting words in the text, or typed, when their first place is used), a type (*Person*, *Organisation*,
*Location*, *Endpoint*) and *Mark*: the words become an asserted node of the analyst's, linked to the
Document and drawn on the canvas; words not in the text are refused before anything is sent, and the
server refuses words not at the place given (`keyboard/reader.spec.ts`, `keyboard/reader-select.spec.ts`). A Document written from held content (ADR-094) shows in the reader as what it is: an image as a
picture, a video as a player, both fetched with the analyst's token from `GET .../documents/{id}/file`;
*Quick scan* describes and reads an image, or transcribes a video, then extracts from that
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
chart destined for an intelligence product should default to light. The theme item in the account menu
(a button of its own only where there is no account menu, §2.0) chooses between them per browser
(ADR-070, ADR-097 step 3); canvases draw from a hex palette that a test keeps
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
A `Drawer` keeps its title and scrolls its body, so content taller than the window is never cut off
(8 October 2026: the Explore panel's later sections could not be reached). `keyboard/explore.spec.ts`
holds this, with its harness inside the `Drawer` the Glass uses.
Radii: 0 for canvas and cells, 2px controls, 4px panels, 6px overlays, 999px status chips.

## 9. Assessment production

The HMP report is the model this platform exists to produce: a set of judgements, each resting on
named evidence, plus explicit gaps and assumptions (`01_DOMAIN_MODEL.md` §5). "Judgements" is a
section of the Inspector's accordion (§2; ADR-096 decision 1 replaced the tabs), open by default
when no node is selected; this section is the first place that names what it contains.

### 9.1 The Judgements section

A `Table` (§8; headless, per §1's TanStack Table choice) listing every judgement in the current
investigation: statement (truncated), probability band, evidence count, author. Selecting a row
opens a `Drawer` (§8) holding the full authoring surface below. Gaps and assumptions get their own
`Tabs` (§8) panes within the same Drawer, not separate Inspector sections — all three are one
assessment surface, and splitting them across the Inspector would scatter a single analytical object
across three places.

**Judgement authoring.** Statement (`Input`, multi-line); probability band via `Select`, populated
from the active deployment's yardstick file (§9.3); an evidence picker drawing from the current
canvas selection or `Combobox` search, split into `supporting`/`contradicting`
(`01_DOMAIN_MODEL.md` §5's own field names). An evidence option names its node as the canvas does
(its type, then the canvas label: "Person: OKAFOR, Callum", a document by its title), and so does each
item an export sends to the gate (§10.1); neither keeps a labeller of its own. **A judgement cannot be saved with zero supporting
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
- Selecting a node lists, in the Judgements section, every judgement resting on it —
  `01_DOMAIN_MODEL.md` §5's own "selecting a node lists the judgements that rest on it," given a
  concrete surface for the first time. On the canvas, a small brass count beside a node says how many
  judgements rest on it, drawn only from the judgements the principal can already list (ADR-070).
- **A judgement is hidden from the Judgements section in full, not shown with a citation marked
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
corrected or retracted) shows a status chip on its own row in the Judgements section (the `999px`
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
POST /v1/investigations/{id}/nodes/{node_id}/suppression-mark     (Editor; ADR-099 Amendment 1)
DELETE /v1/investigations/{id}/nodes/{node_id}/suppression-mark
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
  extended here to the report as a whole). The report is titled by the case's name, and cites each
  node of evidence as the canvas names it (§9.2), its id kept only as a data attribute; a cited
  node not on the canvas is cited by its id. An author or a gap's raiser is still shown by
  principal id: nothing in the build holds a principal's display name (found 9 October 2026; it
  needs a decision on whether the name is kept at write time or looked up). Chosen over a PDF pipeline deliberately: this build
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
