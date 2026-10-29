# OspreyFlow — DESIGN.md

The contract. Every font, colour, size, spacing step and radius used in the product appears here.
Anything on a screen that is not in this file is drift.

Version 0.3.1 (13 October 2026, the owner's ruling): the chart palette (§3.4a) and the Inspector's
key column (§5a) recorded as built, so nothing on a screen is outside this file.
Version 0.3. Layout dimensions added (§5a), and dash and grid values settled against the prototypes.
Version 0.2: the OspreyFlow identity. Brand motifs reworked; UI mechanics, palettes, type split and
accessibility rules carried over from 0.1 unchanged.

---

## 1. Direction in one paragraph

The chrome is a grey instrument housing; the graph is the only place colour means anything. One
warm brass accent is reserved for actions, focus and the logo, and is permanently excluded from the
data palette. The identity is monochrome and spends no colour at all: nine mutually distinguishable
entity channels, verified under protanopia and deuteranopia, remain the property of the data layer.
Dark theme is the working default; light theme is a separately tuned ramp, not an inversion, for
report screenshots and print.

One mark, two cuts, no secondary. The separate Mantis and Nexus marks are retired and must not
appear on any surface.

**The mark — swept wing, triangulated.** A wing in a dive on a 48 unit grid: leading edge (4,6) →
wrist (25,11) → tip (45,26); trailing edge (9,42) → (25.5,30) → tip. Span 41, root chord 36, with a
kink at the wrist. Meshed as a tapering triangle strip — 3 chordwise divisions at the root chord, 2
at the wrist, converging to 1 face at the tip, six faces total — each face inset 1.1 units from its
centroid so the gaps are uniform. The wing is the osprey: a strike committed from height and
corrected on the way down. The triangulation is the partitioned property graph underneath, and it is
structural rather than pattern — the facets are why the silhouette has any internal form.

**Mesh cut** above 20px. **Solid cut** at 20px and below: same outline (`M4 6L25 11L45 26L25.5 30L9
42Z`), facets dropped, wrist kink kept — this is the favicon, tab icon, taskbar and tool-switcher
mark. The cut is selected by rendered size, never by context or by eye.

Clear space on all four sides is the root chord ÷ 3, 12 grid units, measured from the ink box.
Minimum size 16px for the mark, 96px wide for the lockup.

**Prohibited:** rotating or mirroring the wing (flipped it reads as a takeoff); colouring facets
individually, which borrows the channel palette; the mesh cut below 20px; outlining rather than
filling the solid cut; adding a body, head, talons or eye; enclosing the mark in a circle or tile;
shipping mark and wordmark as one locked group.

The mark is not a node-and-edge constellation, a web, a hexagon, an eye, a globe with arcs or a
swoosh. No bird is drawn — only the wing, and only as a meshed surface.

---

## 2. Typography

| Role | Family | Source | Why |
|---|---|---|---|
| UI | **Atkinson Hyperlegible Next** | Google Fonts, wght 200–800 | Letterform disambiguation is its design purpose: `1 l I`, `0 O`, `rn/m` are drawn to be told apart. Analysts read identifiers all day. Not Inter, and not a fashion pick. |
| Mono | **IBM Plex Mono** | Google Fonts, wght 400/500/600 | Wide aperture, clearly differentiated `0/O` and `1/l`, holds up at 11px. Carries all tabular figures. |

Rules:

- Mono is **semantic**, not decorative. It means "literal value, safe to copy": ids, hashes,
  timestamps, amounts, query syntax, raw field values.
- **All tabular figures come from the mono family.** Numeric table columns are mono; numerals inside
  running UI text use Atkinson with `font-variant-numeric: tabular-nums`.
- Sentence case everywhere. No tracked-out all-caps labels.
- Weights in use: 400, 600, 700. Nothing else.

### Type scale (base 13px)

| Token | Size / line-height | Use |
|---|---|---|
| `--fs-11` | 11 / 14 | dense table meta, axis ticks, provenance chips |
| `--fs-12` | 12 / 16 | secondary labels, table headers |
| `--fs-13` | 13 / 18 | **UI base** — controls, rows, body |
| `--fs-14` | 14 / 20 | panel body copy, emphasised rows |
| `--fs-16` | 16 / 22 | panel titles |
| `--fs-19` | 19 / 26 | section headings |
| `--fs-23` | 23 / 30 | screen titles |
| `--fs-30` | 30 / 36 | document/brand headings |
| `--fs-40` | 40 / 46 | brand surfaces only, not product UI |

Mono sizes: 11, 12, 13 with `letter-spacing: -0.005em`.

### Wordmark

Closed compound, internal capital. The halves are separated by **weight only** — `Osprey` at 700,
`Flow` at 400, same size, same colour, no extra letterspacing, no divider, no colour split. Nothing
is added to the lockup that would have to be redrawn for one-colour print.

- Full: **OspreyFlow**
- Product-chrome short form: **Osprey** (weight 700)
- Cramped/square placements: **OSF** — IBM Plex Mono 600, `letter-spacing: 0.04em`
- Lockup gap: mark width ÷ 3, with cap height aligned to the wrist kink

---

## 3. Colour

### 3.1 Neutral ramp (the chrome)

Twelve steps, `oklch` hue 215 at chroma 0.004–0.006 — a bias small enough to read as grey, large
enough not to read as dead. Role names map to the same index in both themes; the two ramps have
different internal spacing (light is denser at the pale end), so light theme is a tuned variant
rather than an inversion.

| Role | Dark | Light |
|---|---|---|
| `--surface-sunken` / n0 | `#090d0e` | `#ffffff` |
| `--surface-app` / n1 | `#101314` | `#f7fbfc` |
| `--surface-panel` / n2 | `#161a1b` | `#f1f4f5` |
| `--surface-raised` / n3 | `#202425` | `#e8eced` |
| `--surface-hover` / n4 | `#2b2f30` | `#dde0e1` |
| `--border-subtle` / n5 | `#3a3e3f` | `#ced2d2` |
| `--border` / n6 | `#4d5051` | `#bbbebf` |
| `--border-strong` / n7 | `#66696a` | `#a2a5a6` |
| `--text-disabled` / n8 | `#848788` | `#a2a5a6` |
| `--text-tertiary` / n9 | `#a2a5a6` | `#66696a` |
| `--text-secondary` / n10 | `#c1c5c6` | `#4b4e4e` |
| `--text-primary` / n11 | `#e8eced` | `#191b1c` |

### 3.2 Brand accent — exactly one

| Token | Dark | Light |
|---|---|---|
| `--brass` | `#c08a34` | `#8a6318` |
| `--brass-hover` | `#d49c44` | `#6f4e10` |
| `--brass-press` | `#a97427` | `#573c08` |
| `--brass-ink` (text on brass fill) | `#141517` | `#ffffff` |

Used for: primary action, focus ring, current-selection stroke on the canvas, the logo. Nothing
else. The hue band `oklch h 60–105` is **permanently excluded from the data palette**.

### 3.3 Semantic

| Token | Dark | Light |
|---|---|---|
| `--error` | `#e2695f` | `#a82f22` |
| `--warning` | `#d9a63f` | `#8f6410` |
| `--success` | `#6bab7e` | `#2f6c4a` |

No info colour: informational messages use neutral surfaces. Semantic colour appears **only in
chrome**, never as a node or edge encoding, and never without an icon and a text label.

### 3.4 Data palette — categorical, 9 channels

Named channels, not numbered, so an assignment can be talked about. Channel-to-entity-type mapping
is per investigation; the default for financial-crime work is in brackets.

| Channel | Dark | Light | Default entity type |
|---|---|---|---|
| `ochre` | `#b34917` | `#83330d` | Address |
| `rose` | `#b74b5e` | `#7e032c` | Identifier (email/phone) |
| `plum` | `#916384` | `#632a55` | Device |
| `violet` | `#8364a6` | `#562182` | Jurisdiction / registry |
| `indigo` | `#677bd6` | `#5367cb` | Person |
| `azure` | `#61b1e6` | `#3682b2` | Company |
| `cyan` | `#35b9c0` | `#2b9095` | Bank account |
| `jade` | `#72b99a` | `#2f8364` | Crypto wallet |
| `moss` | `#90b667` | `#6c8c4a` | Payment card |

**Verified, not assumed.** Pairwise CIELAB ΔE across all 36 pairs, computed under Viénot–Brettel
dichromat simulation:

| Vision | Dark min ΔE | Light min ΔE |
|---|---|---|
| Normal | 20.2 | 22.1 |
| Protanopia | 20.1 | 22.1 |
| Deuteranopia | 20.2 | 22.3 |
| Tritanopia | **4.4** | 7.8 |

Tritanopia is not solvable with nine hues and is recorded as a known limit, not a pass. Mitigation
is structural and applies to all users: **hue is never the only encoding** — every channel is paired
with a node shape and, above 40% zoom, a label. Six shapes (circle, square, rounded square, diamond,
triangle, ring) cross with the nine channels.

Minimum contrast of every channel against its own theme's panel surface: 3.1:1 dark, 3.3:1 light.

### 3.4a Chart palette — one set for both themes

The nine channels moved into the lightness band that reads on both panels, for dashboards and charts
(ADR-111 Amendment 4, the owner's values of 12 October 2026). A chart keeps its series colours in
either mode, so each value is the same in both themes. Each holds at least 3.1:1 against the dark
and the light panel, keeps its channel's hue within a few degrees, and separates further than either
per-theme set under normal and simulated deutan, protan and tritan vision. Brass is not among them.

| Token | Dark | Light |
|---|---|---|
| `--chart-ochre` | `#ac4a06` | `#ac4a06` |
| `--chart-rose` | `#ba3457` | `#ba3457` |
| `--chart-plum` | `#b16ca6` | `#b16ca6` |
| `--chart-violet` | `#804dc3` | `#804dc3` |
| `--chart-indigo` | `#6574eb` | `#6574eb` |
| `--chart-azure` | `#2290c8` | `#2290c8` |
| `--chart-cyan` | `#0a7376` | `#0a7376` |
| `--chart-jade` | `#369974` | `#369974` |
| `--chart-moss` | `#629136` | `#629136` |

### 3.5 Sequential ramp — magnitude (centrality, volume, weight)

Single family, hue 200, six steps, monotonic in lightness so it survives greyscale printing.

- Dark: `#0a3537` `#1d575a` `#2d787c` `#3b999e` `#4abbc1` `#5de1e8`
- Light: `#cfebec` `#a0ced0` `#6eaeb2` `#358f94` `#007177` `#00535b`

It shares a hue family with the `cyan` channel deliberately: sequential encoding is applied to size
and edge weight layers, never to node fill on the same canvas as categorical fill.

### 3.6 Diverging ramp — signed measures (change vs baseline)

Warm/cool axis (hue 42 ↔ 240) through a neutral mid — the one axis dichromats retain.

- Dark: `#b54e21` `#bf775b` `#c49e8f` `#828788` `#8cadc4` `#4e94c3` `#0079b8`
- Light: `#a24112` `#b97155` `#caa090` `#d5d8d9` `#8cb0ca` `#478ebc` `#006aaa`

### 3.7 Graph states

| State | Treatment |
|---|---|
| default | channel fill, 1px `--border-subtle` stroke |
| hovered | stroke → `--text-primary`, 1.5px |
| selected | stroke → `--brass`, 2px, plus 1px surface-coloured gap ring |
| path-highlighted | stroke → `--text-primary` 2px; edges on path 2px, others unchanged |
| dimmed | `color-mix(in oklab, <channel> 32%, var(--surface-panel))` — hue preserved, contrast reduced, label kept |
| filtered-out | `color-mix(... 12%, panel)`, no label, not hit-testable |

No glow, halo, pulse or bloom in any state.

### 3.8 Provenance — stroke, not hue

So it composes with all nine channels.

| Provenance | Stroke |
|---|---|
| asserted (in source record) | solid 1px |
| inferred (model-derived) | dashed 1px, `4 3` |
| unresolved / single-source | dotted 1px, `1 3` |

Inferred edges also carry a confidence value in the detail panel. No red, no warning colour:
inference is normal, not an alarm.

---

## 4. Spacing

Base unit 2px, compact by intent. `--sp-2 4 6 8 12 16 20 24 32 40 56` (px). Nothing outside this
set. Spacing varies by grouping: 4/6 inside a control, 8/12 between related controls, 20/24 between
groups, 32/40 between regions.

Minimum internal padding on any control with text: 6px horizontal, 3px vertical.

## 5. Radii

`--r-0: 0` (canvas, table cells, full-height panels) · `--r-1: 2px` (inputs, buttons, chips) ·
`--r-2: 4px` (panels, menus, popovers) · `--r-3: 6px` (modals, drawers) · `--r-pill: 999px`
(status chips only). No other radius.

## 5a. Layout dimensions

These are fixed sizes for the shell, overlays and canvas. They count as part of the contract in the same way as the spacing and radius scales: a size that isn't listed here is drift.

### Shell regions

| Region | Size |
|---|---|
| Protective marking strip | 20px high |
| Top bar (workspace) | 44px high on one line; whole items wrap to a second line when they do not fit (ADR-115 Amendment 3) |
| Top bar (welcome, home) | 48px high |
| Left rail | 48px wide, with 36×36 buttons |
| Canvas toolbar | 36px high |
| Right panel | 340px wide by default. Resizable from 300 to 480px. Its tab row is 36px high |
| Timeline (collapsed) | 34px high |
| Timeline (expanded) | 34px header plus a 96px plot |
| Status bar | 26px high |
| Inspector key column | 96px wide (a property's name beside its value) |

### Breakpoints

These are viewport widths.

- At 1200px and above, the right panel is docked with a hairline. Below 1200px it becomes an overlay with a shadow, no hairline, and starts closed.
- Below 1100px, the username text and the toolbar's "Last change" note are hidden, and the welcome panel narrows to 280px.

### Overlays and cards

| Element | Width |
|---|---|
| Welcome panel | 320px (280px below 1100) |
| Sign-in card | 360px flex basis, 300px minimum |
| Overlay right panel | 340px |

The welcome panel's maximum height leaves a 72px strip clear for the selection bar.

### Control heights

24, 26, 28, 30, 32, 34 and 36px only.

- 24 for a toggle inside a toolbar.
- 26 for a toolbar control.
- 28 for buttons in the selection bar and zoom group.
- 30 for top-bar controls.
- 32 for a text input.
- 34 for a secondary full-width button.
- 36 for a primary full-width button.

### Canvas

| Element | Size |
|---|---|
| Person node | radius 7, 14px across |
| Email or document node | radius 6, 14.4px across |
| Hub node | radius 8 |
| Selection ring | radius 13, 2px brass |

- **Hit area.** Every node also has an invisible 24×24 hit area, to meet WCAG 2.2 SC 2.5.8, and the canvas can also be operated fully by keyboard.
- **Labels.** Mono 11px. Identifiers longer than 28 characters are truncated in the middle: the first 19 characters, an ellipsis, then the last 4.
- **Label clearance.** The graph wrapper has 160px of horizontal padding.
- **Dashes.** Inferred links use `4 3` and unresolved links use `1 3`. These patterns apply to edges and to the legend.

## 6. Borders and elevation

- Hairline is 1px, `--border-subtle` for structure, `--border` for interactive edges.
- **A surface gets a hairline or a shadow, never both.** Docked panels: hairline. Overlays: shadow.
- Dark overlay shadow: `0 8px 24px -8px rgba(0,0,0,0.7)`.
- Light overlay shadow: `0 6px 20px -6px rgba(25,27,28,0.18)`.
- No gradients anywhere in chrome. No decorative fills.

## 7. Motion

| Token | Value | Use |
|---|---|---|
| `--dur-fast` | 90ms | control state change |
| `--dur-base` | 140ms | menu, tooltip, toast |
| `--dur-panel` | 180ms | drawer/panel open |
| `--dur-graph` | 420ms | graph re-layout |
| `--ease` | `cubic-bezier(.2,0,.3,1)` | everything except graph |
| `--ease-graph` | `cubic-bezier(.25,.1,.25,1)` | node position interpolation |

Nodes interpolate position on re-layout; they never fade out and in, so the analyst can follow them.
No entrance animation on any static content. Under `prefers-reduced-motion: reduce` all durations
go to 0 and graph re-layout is replaced by an instant move plus a persistent "layout changed —
show previous positions" control.

## 8. Accessibility floor

WCAG 2.2 AA, hard. Body text ≥ 4.5:1, headline-scale ≥ 3:1, non-text UI ≥ 3:1, both themes.
Focus ring: 2px `--brass` at 2px offset on every interactive element, including canvas nodes.
The graph canvas is fully keyboard-operable: arrow keys traverse edges from the focused node, tab
moves between regions, `[`/`]` cycle sibling edges, `Enter` opens the entity panel.

---

## 9. Documented exceptions

Intentional breaks of common detector rules. Anything not listed here is a genuine finding.

1. **Body text at 13px.** Density across two or three monitors is the product's job. Checked in
   Atkinson Hyperlegible Next specifically, which was designed for small-size legibility; secondary
   text stays at 12px minimum and never below 4.5:1.
2. **Compact padding.** 4–12px inside controls, against consumer-web norms. Floor: no text within
   3px of its container edge.
3. **Monospace for small labels and values.** A semantic distinction ("literal value, safe to
   copy"), not styling.
4. **Grid background on the graph canvas only.** A measurement grid: 1px lines in `--border-subtle` mixed to 40% toward
   transparent, on a 16px lattice. No other surface gets a grid.
5. **Dense repeated rows in result tables.** Tabular data is repetitive; that is the point.
6. **Tritanopia ΔE below threshold** in the 9-channel categorical palette — recorded in 3.4 with
   its structural mitigation rather than waved away.

## 10. Pre-flight self-audit — foundations round

Pass unless stated.

**Palette** — chrome near-achromatic, pass. One accent, excluded from the data palette, pass. No
gradient washes, no neon-on-dark, no glow, pass. No cream/terracotta, pass. Data palette verified by
computation under protanopia/deuteranopia/tritanopia, pass with the tritanopia limit above.

**Type** — not Inter, pass. Hierarchy steps 11/12/13/14/16/19/23/30/40, pass. No all-caps eyebrows,
pass. No italic serif display, pass. Sentence case, pass.

**Layout** — no repeated identical cards, pass. No nested cards, pass. Hairline-or-shadow rule, pass.
No status stripes, no icon tiles above headings, pass. No 01/02/03 markers, pass.

**Motion** — no pulsing dots, marquees or bounce, pass. No section entrance animation, pass.
`prefers-reduced-motion` respected, pass. Graph transition preserves position continuity, specified;
to be demonstrated in the components round.

**Copy** — no em-dash register in product copy, pass. No "not X but Y", pass. No growth-SaaS claims,
pass. Error and empty-state copy specified in the components round.

**System** — DESIGN.md exists and covers every value in use, pass. Both themes AA, pass. Focus state
on every interactive element, pass. Keyboard operation of the canvas specified in 8, implementation
due in the components round.

**Section 12 test** — the choices that would *not* be made for a generic data platform: the
achromatic chrome with a single warm brass accent rather than a blue one; brass hue permanently
excluded from data; the type pick justified by letterform disambiguation rather than neutrality;
tabular figures delegated to the mono family; light theme ramp tuned separately; a mesh motif spent
on the mark's internal construction rather than drawn as a node-and-edge constellation, and a
size-switched two-cut mark instead of one logo stretched across every size.

**Carried over unchanged from 0.1** — the neutral ramp, the brass accent and its exclusion from
data, the nine categorical channels with their shape pairings, provenance encoded by stroke style
only, the sequential and diverging ramps, both theme ramps, the type split and scale, spacing,
radii, motion and the accessibility floor. The rebrand touched the identity, not the mechanics.
