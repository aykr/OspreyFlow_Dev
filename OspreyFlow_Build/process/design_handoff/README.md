# Handoff: OspreyFlow sign-in page and analyst workspace

## Overview
This package covers two screens for OspreyFlow, a network analysis platform for fraud, anti-money-laundering (AML) and organised-crime investigation:

1. **Welcome and sign-in.** The public landing page. Sign-in is visible straight away, with sections below describing crime analysis and AML.
2. **Workspace.** The first screen after sign-in. It's a restyled graph workspace that applies `Workspace Design Review.md`, with a dismissible welcome panel, tips and keyboard shortcuts.

`DESIGN.md` (v0.3) is the binding design contract. If this README, the review or a prototype disagrees with it, `DESIGN.md` wins. Region sizes, breakpoints, control heights and node sizes are in its §5a. Put it at the root of the repository. Every colour, font, size, spacing step and radius used must appear in it. If a value isn't there, ask before inventing one.

## About the design files
The `.dc.html` files are **design references built in HTML**: prototypes that show the intended look and behaviour. They are not production code. Recreate them in the target codebase's own stack and component patterns. Open either file in a browser to see it: `support.js` is the small runtime the files need, and `image-slot.js` provides the image placeholders.

The prototypes use inline styles and CSS custom properties for theming. In the real build, map those to the codebase's token layer, using the names in `DESIGN.md`.

## Fidelity
**High fidelity.** Colours, type, spacing, radii, states and copy are final. Match them exactly. The graph data, counts and timestamps are illustrative.

---

## Screen 1: welcome and sign-in (`OspreyFlow Welcome.dc.html`)

### Layout (top to bottom)
1. **Protective marking strip.** Height 20px, full width. Background `--surface-raised`, 1px `--border-subtle` bottom border. Text is centred, 11px, weight 600, letter-spacing 0.02em. The marking is configurable as `OFFICIAL`, `OFFICIAL-SENSITIVE` or none. When it's set to none, the strip isn't rendered at all.
2. **Header.** Padding 12px vertical and `clamp(20px, 4vw, 48px)` horizontal, with a bottom hairline.
   - Left: the mesh mark at 28px, then the wordmark at 17px (**Osprey** in 700, **Flow** in 400).
   - Right: an "About" anchor link, then a secondary "Light theme / Dark theme" toggle button.
3. **Hero.** Max-width 1320px. A wrapping flex row with a 32px gap.
   - **Left column:** `flex: 1 1 420px`, holding the following:
     - **H1.** "Crime analysis on one graph", 30/36, weight 700, letter-spacing −0.015em.
     - **Lead paragraph.** 15/23, `--text-secondary`.
     - **Capability list.** A 4-up `dl`: Network analysis, Geospatial, Timeline trends, Reporting. Each item has a 2px `--border` top rule, a 14px stroke icon with its title at 13px weight 700, and a 12/17 description.
     - **Product figure.** Radius 4, 1px `--border-subtle` border, containing:
       - **Header row.** "Operation Ledger" plus a mono "synthetic" tag on the left, and entity/link counts in mono 11px on the right.
       - **Graph canvas.** SVG with viewBox 680×400 on a 16px measurement grid, drawn in `--border-subtle` at 40%. Nodes use the category colour channels plus shapes (see `DESIGN.md` §3.4). Edge stroke encodes provenance: solid, dashed `4 3`, or dotted `1 3`. One path is drawn in `--text-primary` at 2px. The selected node has a 2px `--brass` ring. One cluster is dimmed to 32% toward the panel colour. Labels are HTML spans laid over the SVG, positioned in percentages, with a solid `--surface-app` background. Each label's anchor side is set explicitly so labels never collide at a 420px canvas width.
       - **Timeline strip.** 28 bars on the `--seq-2` / `--seq-4` ramp. The selected window shows in `--seq-4` with a 1px `--border-strong` brush outline.
       - **Side column.** `flex: 1 1 200px`. It holds a map inset (120px tall, cropped) and a report-pack tile containing a sparkline, an assessment and a withheld-item line. Below about 800px the side column wraps under the graph, and its two tiles then sit side by side.
       - **Caption row.** Entity-type legend on the left, provenance stroke legend on the right.
   - **Right column (sign-in):** `flex: 0 1 360px`, min-width 300px, `position: sticky; top: 24px`. The card has `--surface-panel` background, a 1px `--border-subtle` border, radius 4 and padding 24.
4. **About section** (`#about`). It can be switched off for internal-only deployments.
   - **H2.** "Two kinds of work, one graph".
   - **Crime analysis.** H3, then three articles in an `auto-fit, minmax(300px, 1fr)` grid. Each article has a 16:10 image slot with a 1px border and radius 4, an H4 at 16/22 weight 600, and body text at 13/19.
   - **Anti-money-laundering.** H3, then a four-stage lifecycle `ol` (Prevent, Detect, Investigate, Report) with 2px top rules, then three more articles.
   - **"Seeing is not doing".** A two-column block: heading on the left, a `dl` of four safeguards on the right.
5. **Footer.** Solid mark at 16px, the version in mono, and links: Account help, Accessibility statement, Privacy notice, Service status.

### Sign-in card states
- **Sign in (default).**
  - H2 "Sign in" at 19/26, weight 700.
  - **Primary button:** "Continue with organisation sign-in". 36px tall, full width, `--brass` fill, `--brass-ink` text at 13px weight 700, radius 2. Hover `--brass-hover`, active `--brass-press`. On click, the label changes to "Opening your organisation's sign-in page…" and the button is disabled.
  - Helper text: "Your password is entered only on your organisation's sign-in page."
  - Divider: "or use an OspreyFlow account".
  - **Email or username field.** Text input, `autocomplete="username"`, mono 13px, 32px tall, `--surface-sunken` background, 1px `--border`. On focus, the border is `--brass` with a 1px brass ring.
  - **Password field.** Has a "Show / Hide" toggle inside the field on the right, plus a "Forgot password?" text button on the label row.
  - **Secondary submit:** "Sign in with email". 34px tall, `--surface-raised` background, 1px `--border`.
  - Footnote about invitations, with a link to account help.
- **Reset your password.** Email or username field, a primary "Send reset link" button, and a "Back to sign in" text button.
- **Check your email.** A confirmation that doesn't say whether the account exists, an expiry of 30 minutes, and a secondary "Back to sign in" button.

### Validation (on submit, never on keystroke)
- **Empty identifier:** "Enter your email address or username."
- **Contains `@` but isn't a valid email:** "Enter an email address in the format name@organisation.gov.uk, or use your username."
- **Username that doesn't match `^[A-Za-z0-9._-]{2,64}$`:** "Usernames use letters, numbers, dots, hyphens and underscores, with no spaces."
- **Empty password:** "Enter your password."
- **Wrong credentials** (shown in a status box with an `--error` border): "That email or username and password do not match an OspreyFlow account. Check for typos, or reset your password. Five failed attempts lock the account for 15 minutes."
- **Field errors:** the field border turns `--error`, the error text shows at 12px `--error`, and the field gets `aria-invalid` and `aria-describedby`.

---

## Screen 2: home after sign-in (`OspreyFlow Home.dc.html`)
The launcher users land on after signing in. Max-width 1240px.

- **Greeting.** Includes identity, clearance and roles in mono. On the right: last sign-in time and IP, with a "Report it" link.
- **Three app panels** (`auto-fit, minmax(300px, 1fr)`, gap 16): Glass, Ingest Studio and Admin console. Each panel has:
  - A 132px preview strip on `--surface-app`. Glass shows a mini graph with a path and the brass selection ring. Ingest Studio shows the Source to Load pipeline, with a `--warning` border on the held stage. Admin console shows a service list with glyph and text status, never colour alone.
  - A title (19/26, weight 700), its audience, a description, and two status lines, each with a ✓, △ or ! glyph.
  - An "Open …" button with its key hint (G, I or A; the keys work page-wide). Only the first permitted app gets the brass fill. The others are secondary.
  - **Role gating:** if the user lacks the role, the panel drops to 72% opacity and the button is replaced by "You need the {role} role for this. Ask an administrator to add it."
- **Left column.**
  - "Needs your attention": rows with glyph, title, one-line detail, app tag and time in mono. Rows are filtered by the user's roles.
  - "Recent cases": a table with columns Case (plus its kind), Your level (Author, Editor or Viewer), Entities (mono, right-aligned) and Opened.
- **Right column.**
  - "Ways of working": a tip viewer with previous/next buttons and an "n of 4" counter. Each tip has its own small picture (timeline dim, provenance strokes, counted-before-drawn, branch) and an app tag. It uses `aria-live="polite"`.
  - "New in 2.6": a changelog, followed by a line on what's coming next.
- **State:** `theme`, `tip`. Roles come from the session. The prototype exposes a `roles` prop: All roles, Analyst only, Data engineer, Administrator.
- **Header-row rule:** counters and links in header rows are `flex: none; white-space: nowrap`.

## Screen 3: workspace (`OspreyFlow Workspace.dc.html`)
The full-viewport shell. Its minimum height is 680px.

| Region | Size | Contents |
|---|---|---|
| Marking strip | 20px | As on screen 1 |
| Top bar | 44px, `--surface-panel`. Below a 1100px viewport the username text and the toolbar's "Last change" note are hidden, leaving only the avatar. | Solid mark at 20px and "Osprey" (14px, 700). Case switcher (min 220px), showing "Enron corpus" plus a mono `local` badge. Search (flex 260px, max 480px), with a `/` key hint. View tabs: Graph, Map, Timeline, Reports. Export menu. Theme icon button. User menu. |
| Left rail | 48px | 36px icon buttons with tooltips: Cases (current), Alerts (with a count badge), Ownership, History, Watches, Proposed types, Ingest Studio. A help button at the bottom reopens the welcome panel. |
| Canvas toolbar | 36px | **Layout:** "Organic" select plus a re-run icon button. A hairline separator. **Show:** a toggle group for Labels and Communities. On the right: "Last change" text. |
| Canvas | flex | 16px measurement grid. The graph sits in an aspect-locked box (1000:560) inside a wrapper with 160px horizontal padding, so labels placed outward from their nodes never leave the canvas. Overlays: welcome panel (top-left; 320px, or 280px below a 1100px viewport), legend (top-right), vertical zoom group (right, under the legend), selection bar (bottom-centre). |
| Timeline | 34px collapsed | Chevron toggle, then a mini density strip on `--seq-2` and the date range in mono. Expanding it adds 96px bars on `--seq-4`, integer y ticks, month labels and a Density/Cyclical switch. |
| Right panel | 340px by default, resizable from 300 to 480px | Tabs: Inspector, Query, Case (36px), plus a close button. Content scrolls. At a viewport of 1200px or wider it docks with a hairline left border and is open by default. Below 1200px it opens as an overlay on the canvas (overlay shadow, no border) and starts closed. The "Details" toggle in the canvas toolbar opens and closes it. |
| Status bar | 26px | Mono 11px counts with 16px gaps. On the right: "Tip", the tip text and a "Next tip" button. |

### Rules carried over from the design review
- **Brass is only used for:** the primary action in the selection bar ("Expand N"), focus rings, and the selected-node ring. Active tabs and views use a `--text-primary` label, weight 700 and a 2px inset bottom rule. They never use brass.
- **One selection surface.** The floating selection bar contains "1 selected", **Expand N** (brass), "Branch to new workspace", "Remove from view" and "Clear" with an Esc hint. It's shown only when something is selected.
- **Canvas nodes and edges.**
  - Person: circle in `--ch-indigo`, r 7. Email: diamond in `--ch-violet`, r 6. The hub email is r 8. Every node has an invisible 24×24 hit area (`DESIGN.md` §5a).
  - Edges have arrowheads and stop 2px short of the target node.
  - Edges touching the selection are drawn in `--text-primary` at 1.75px.
  - Inferred edges are dashed `4 3`.
- **Labels.** Mono 11px. Identifiers longer than 28 characters are middle-truncated (19 characters, an ellipsis, then the last 4). Each label is placed outward from its node based on the node's angle, and never crosses into the other community.
- **Communities toggle.** Draws dashed `--border-strong` boxes (radius 6), each with a caption such as "Community 1, 13 entities".
- **Welcome panel.**
  - 320px wide, `--surface-raised`, radius 6, overlay shadow and no border. It's closable and reopens with `?` or the help rail button.
  - Contents: a summary, "Pick up where you left off" (three history rows, each clickable to restore that state), and "Keys worth knowing" (six shortcuts shown as key caps).
- **Inspector.**
  - **Nothing selected:** an empty state that offers click, arrow keys or `/`.
  - **Something selected:**
    - Type chip with its shape and colour, and the marking badge.
    - The ID in mono at 13px, weight 600, and the display name.
    - Attributes, in a 96px key column with mono values.
    - Relationships: count, then an "Expand" secondary button, captioned "Counted in the store before anything is drawn."
    - Provenance: stroke sample, source description and source-record paths in mono.
- **Query tab.** Borderless accordion rows (36px, left chevron) for Ranking, Community detection and Filter, each with a description and a secondary action.
- **Case tab.** "What this case holds", with bars on `--seq-4`. "Most connected in this view" is a ranked list; clicking a row selects that node.

### Keyboard
- `/` focuses search, from anywhere except inside an input.
- `Esc` clears the selection, or blurs an input if one is focused.
- `?` opens the welcome panel.
- With the canvas focused (`tabIndex=0`, a 2px inset brass ring on focus), the arrow keys move between nodes and `Enter` opens the Inspector. The canvas `aria-label` announces the current selection.

---

## State
- **Welcome:**
  - `view`: Graph, Map, Timeline or Reports
  - `theme`: dark or light. The default comes from deployment config.
  - Sign-in `view`: signin, forgot or sent
  - Form fields: `email`, `password`, `pwShown`
  - `errs`, `busy`, `ssoBusy`, `msg`
- **Workspace:**
  - `view` (Graph, Map, Timeline or Reports), `theme`
  - `tab`: inspector, query or case
  - `sel`: the ID of the selected node, or null
  - `labels`, `communities`: canvas toggles
  - `tlOpen`: whether the timeline is expanded
  - `welcome`: whether the welcome panel is open. Persist this per user, so dismissing it sticks.
  - `tip`: the current tip index
  - `q`: which Query accordions are open
- **Data needed:** case summary counts, the current view's entities and links, history entries, per-entity relationship counts (counted server-side before drawing) and source records.

## Motion
There's no motion beyond state changes. Hover and focus transitions use `--dur-fast` (90ms). Graph re-layout follows `DESIGN.md` §7. With `prefers-reduced-motion`, all durations are 0.

## Design tokens
All tokens are in `DESIGN.md`: the neutral ramp, brass, semantic colours, the nine categorical channels, the sequential and diverging ramps, type scale, spacing, radii, borders and elevation. Dark is the default theme. Light is a separately tuned ramp, under `[data-theme="light"]` in the prototypes.

- **Fonts:** Atkinson Hyperlegible Next for the interface, IBM Plex Mono for every identifier, timestamp, count and key cap.
- **Overlay shadows:** dark `0 8px 24px -8px rgba(0,0,0,.7)`, light `0 6px 20px -6px rgba(25,27,28,.18)`.

## Assets
- `assets/screen-*.jpg`: screenshots of the current build, taken from the OspreyFlow product overview and AML decks. They're placeholders. Replace them with fresh captures once the workspace matches this design, because they still show the old styling.
- **Logo:** the mesh-wing mark and its solid cut are inline SVG in both files. The paths are in `DESIGN.md` §1.
- **Icons:** 16-unit stroke icons, inline (1.3–1.5 stroke, round joins). Use the codebase's icon set if it has close equivalents.

## Files
- `OspreyFlow Welcome.dc.html`: the welcome and sign-in prototype
- `OspreyFlow Home.dc.html`: the home page after sign-in, with the app launcher
- `OspreyFlow Workspace.dc.html`: the post-sign-in workspace prototype
- `DESIGN.md`: the design contract (put this at the repo root)
- `Workspace Design Review.md`: the issues these designs fix, with acceptance checks
- `support.js`, `image-slot.js`: runtime needed to open the prototypes
- `assets/`: the screenshots used in the welcome page

## Suggested brief for Claude Code
> Implement the two screens in this folder in our codebase. Treat `DESIGN.md` as binding: use only its tokens, and stop and ask if a value is missing. Build the sign-in page first, including validation and all three card states. Then refactor the workspace shell to match `OspreyFlow Workspace.dc.html` and the acceptance checks in `Workspace Design Review.md`. Make sure every interactive element has a visible brass focus ring and that the canvas can be operated by keyboard. After each PR, run `npx impeccable detect src/` and report any finding that isn't covered by `DESIGN.md` §9.
