# OspreyFlow workspace: design review (light theme)

Reviewed against `DESIGN.md` v0.2. Where this review and v0.3 differ, v0.3 wins: it records the sizes the prototypes settled on, using the localhost:8080 screenshot (Enron case, 3 nodes selected).
Issues are listed in priority order. Each one gives the problem, the change to make, and how to check it's done. Tokens refer to `DESIGN.md`.

---

## Summary

The screen has about 40 controls at the same visual weight, in five horizontal bands. There's no primary action and no clear grouping. The same idea appears in several places: selection shows up three times with three different counts, and communities shows up twice. Brass marks "current" in six places, so it no longer reads as "act here". The canvas is the reason the product exists, but it gets about 45% of the height, while a single-bar timeline gets about 35%.

Most of the fixes below remove or regroup controls. Only a few add anything.

---

## P0: structure

### 1. Collapse five horizontal bands into three regions
**Problem.** The screen stacks a global bar, a case tab bar, a canvas toolbar, the canvas and a timeline. Every band has its own buttons, so the analyst scans five rows to find one control.
**Change.** Use a fixed shell:
- **Top bar, 44px.** Product mark (solid cut), case switcher, global search, view switch, then user and classification on the right.
- **Left rail, 48px, icon-only.** Investigations, branches, history, watches, proposed types, ingest.
- **Main area.** A canvas toolbar (32px, docked to the top edge of the canvas), the canvas, then a timeline (collapsed to 32px by default and resizable).
- **Right panel, 340px by default, resizable from 300 to 480px.** Inspector and query builder as tabs, not stacked sections.

**Done when.** No more than 3 rows of chrome sit above the canvas at 1440×900, and the canvas gets at least 60% of the viewport height with the timeline collapsed.

### 2. One selection model, shown once
**Problem.** The tab bar says "2 selected". The canvas toolbar says "Remove selected (1)" and "Branch selected (1)". The bottom-left pill says "1 selected / Clear". There are three surfaces showing two different counts.
**Change.** Use one floating selection bar, bottom-centre of the canvas, shown only when the selection is non-empty. It reads `3 selected` followed by `Expand`, `Branch to new workspace`, `Remove from view` and `Clear` (Esc). Delete the other two surfaces. The count comes from one source of truth.
**Done when.** A search for "selected" in the rendered DOM finds exactly one live counter.

### 3. Fix the case tab bar
**Problem.** The same case name appears twice, once plain and once as "· 2 selected". It reads as two cases. The middle dot also breaks the brief's "no meta strings joined with middle dots" rule.
**Change.** Show one tab per open workspace: `Enron corpus` plus a mono badge for scope, e.g. `local`. Branches become child tabs, indented under their parent, or an entry in the left rail. Don't put selection state in tab labels.

### 4. The inspector is empty while nodes are selected
**Problem.** Three nodes are selected and the Inspector shows nothing.
**Change.**
- **One node selected:** show the entity panel. That's the type chip (channel colour plus shape), the label in mono, attributes, relationships, provenance and source records.
- **Several nodes selected:** show a comparison summary, with counts by type, shared attributes, and the edges between the selected nodes.
- **Nothing selected:** show an empty state with one action: "Select a node or press `/` to search."

---

## P1: hierarchy and colour

### 5. Brass is overused
**Problem.** Brass currently marks the product name, Ingest Studio, the active view (Graph), the active case tab, the active timeline mode (Density), the slider thumb and the timeline bars. Under `DESIGN.md` §3.2, brass means a primary action, focus or selection. Nothing else.
**Change.**
- Active tab, view and mode: `--text-primary` on `--surface-raised` with a 2px `--text-primary` underline. No brass.
- Timeline bars: `--seq` ramp step 4. They're data, so they use a data ramp.
- Slider thumb: `--text-secondary`. It turns brass only while focused.
- Brass stays on the single primary action in view (e.g. `Run query`), on focus rings, and on the selected-node stroke.

**Done when.** No more than one brass-filled element is on screen when nothing is focused.

### 6. Off-palette colours
**Problem.** The timeline range brush is light blue (around `#c8d4f0`), which isn't in `DESIGN.md`. A detector will report it as drift.
**Change.** Brush track `--surface-raised`, selected window `--surface-hover`, handles `--border-strong`.

### 7. Every control is a bordered box
**Problem.** Toolbar buttons, toggles, accordions and selects all use the same 1px box. Nothing tells a toggle from an action or a menu. "Communities", "Labels" and "Icons" also float on a soft shadow, which breaks the hairline-or-shadow rule.
**Change.** Use three button tiers:
- **Primary:** brass fill. At most one per region.
- **Secondary:** `--border` hairline.
- **Quiet:** no border, `--surface-hover` on hover. Use this for most toolbar actions.

Toggles (Labels, Icons, Communities) become a segmented control with a visible on/off state. Remove all shadows from docked controls.

### 8. Region headings are inconsistent
**Problem.** "Inspector" and "Query builder" are 16px bold in a padded header. "Timeline" is 13px regular. Section headers have drag handles (⠿) and ▲▼ reorder arrows, which put power-user layout controls at the same weight as content.
**Change.** All region headers are `--fs-12` 600 `--text-secondary`, in a 28px header row with a hairline below. Reordering moves into a header context menu, or uses drag on the header with keyboard support (Alt+↑/↓). Remove the arrows.

---

## P1: canvas

### 9. Nodes are smaller than their labels
**Problem.** Nodes render at about 10px, with labels about twice their height. The email-hash label runs 560px and crosses into the right panel. Type is unreadable at this scale.
**Change.**
- Nodes are 14px across at 100% zoom (person radius 7, see `DESIGN.md` §5a), with the shape from the channel table (§3.4) and an invisible 24×24 hit area.
- Labels are `--fs-12`. Identifiers (emails, hashes) are set in mono, because they are literal values.
- Labels truncate at 24 characters with a middle ellipsis: `email:enron-ev-6be2…90c7`. The full value shows on hover and in the inspector.
- Labels never cross the canvas boundary.

### 10. The canvas has no navigation
**Problem.** There's no zoom control, no fit, no legend, no minimap and no measurement grid. The three nodes sit in the middle of a large empty field.
**Change.**
- Bottom-right cluster: zoom out, a zoom % readout (mono), zoom in, and Fit (F). Each is 28px, with keyboard shortcuts shown in the tooltips.
- Top-right of the canvas: a collapsible legend listing only the entity types present, each as shape plus colour plus name.
- Turn on the measurement grid (§9 exception 4): a 16px lattice in `--border-subtle` mixed to 40% (`DESIGN.md` §9).
- After any layout change, auto-fit with 48px padding.

### 11. Edges carry no information
**Problem.** Edges are uniform grey lines, with no direction, no provenance and no weight.
**Change.**
- Arrowheads for directed relations, e.g. email sent → received.
- Stroke style for provenance (§3.8): solid, dashed, dotted.
- Width from the edge-weight sequential scale, 1–3px.
- Hovering an edge shows its type and count in a tooltip.

### 12. The canvas toolbar mixes three jobs
**Problem.** One row holds an unlabelled checkbox, the layout select, "Arrange again", display toggles and destructive selection actions.
**Change.** Split the toolbar into labelled groups, separated by hairlines.
- **Left group, Layout:** a select showing `Organic`, plus a re-run icon button.
- **Middle group, Show:** Labels, Icons and Communities as a segmented toggle.
- **Selection actions:** move to the selection bar (item 2).
- **Unlabelled checkbox:** remove it, or label it. If it means "select all", use Ctrl+A and a menu item.

---

## P2: timeline, query builder, top bar

### 13. The timeline uses too much space for too little data
**Problem.** It takes about 35% of the height for one bar covering one day. The y-axis shows decimals (0.2, 0.4) for event counts.
**Change.**
- Collapse the timeline to a 32px strip by default, with a resize handle.
- Use integer y-ticks only, set in mono.
- When there's only one bucket, switch the scale to hours.
- Put the mode switch (Density, Cyclical) in the header row as a segmented control. "Set exact dates" and "Overlay another case" move to an overflow menu.

### 14. Query builder has empty tabs and heavy accordions
**Problem.** Two empty tab outlines render above Ranking, Communities and Filter. The accordions use a full-strength border and a right-pointing triangle. Communities also duplicates the canvas toggle.
**Change.**
- Remove the empty tabs.
- Accordion rows: no border, a hairline divider, a chevron on the left, `--fs-13` 600.
- Rename the analytic to "Community detection" so it isn't confused with the display toggle "Show communities".

### 15. Top bar truncation and ambiguity
**Problem.**
- "Case: Enron corpus (real dat" and "Search entitie:" are both cut off.
- "Glass | Ingest Studio" doesn't match the OspreyFlow identity.
- "Balanced" next to an unlabelled slider has no stated meaning.
- "Dark" with a moon icon is unclear: is it the current state or the action?
- "Export ⚙" mixes an action with settings.

**Change.**
- Case switcher: min-width 240px, with the full name in a tooltip. Drop the "Case:" prefix.
- Search: min-width 280px, placeholder "Search entities", `/` shortcut shown.
- Replace "Glass" with the OspreyFlow solid mark plus "Osprey". Ingest Studio moves to the left rail.
- Slider: label what it controls. If it trades precision against recall, say "Match strictness" and show the value.
- Theme: move it into the user menu as "Theme: Light / Dark / System".
- Export: a single menu button.

### 16. The classification marking is buried
**Problem.** "OFFICIAL" sits inside the user chip. In a UK government context, the protective marking has to be prominent and persistent.
**Change.** Add a dedicated full-width strip, 20px, above the top bar. It shows the marking text centred in `--fs-11` 600 on `--surface-raised`, with its own hairline. Keep it neutral. Don't use colour coding unless departmental policy requires it, and then only as a documented exception in `DESIGN.md`.

---

## P2: accessibility checks to run

- Visible brass focus ring on every control, including canvas nodes. Tab through the canvas and confirm that arrow keys traverse edges (§8).
- In the current screenshot the status bar ("3 nodes 3 edges …") has no separators between counts. Give each count a gap of `--sp-16`, or show them as pairs: `3 nodes`, `3 edges`.
- Hit targets of at least 24×24px (WCAG 2.2, 2.5.8). The ▲▼ arrows and the × on the case tab are currently below this.
- `prefers-reduced-motion`: layout changes must jump straight to the final positions, and the "show previous positions" control must appear.

---

## Brief for Claude Code

> Refactor the workspace shell to `DESIGN.md` v0.2. Implement items 1–5 first, as one PR: shell regions, a single selection bar, cleaned-up tab bar, inspector states, and brass limited to primary action, focus and selection only. Then do 9–12 (canvas) as a second PR, and 13–16 as a third. Use only tokens from `DESIGN.md`. If a value isn't there, stop and ask rather than inventing one. After each PR, run `npx impeccable detect src/` and report any findings that aren't covered by `DESIGN.md` §9.
