# The Glass: fewer rows above the canvas — the case lane's proposal, before building

The case lane, 16 November 2026, on main `0b1631b`. It answers `OWNER_BRIEF_2026-11-16.md`'s "What I want back, before
any building". Nothing here is built. Nothing merges before v0.6.0 is released.

## 1. The lane and its estimate

**The case lane.** It built the case line's saved-view words and the strip (ADR-145 Amendment 17).

| Part | Hours | What it holds |
| --- | --- | --- |
| A. Strictness in the toolbar | 5 | `ResolutionThresholdControl` as a compact disclosure (its name and setting on a button, the same slider under it); the Graph's own row removed; the same announcement; the 1024 px decision below |
| B. The strip goes; its state on the case line | 9 | `ContextBanner` takes the saved view's state and its other contents (proposal 3a); `WholeCaseStrip` and `ViewLensBanner` retired; focus on opening moves from the strip to the case line; the fold order ("reads …" gives way first); `App.views`, `views`, `rules-place`, `view-over-cap` and every-harness cases rewritten; spec 02 §2.0 and the user guide's words |
| C. A toolbar that can be hidden | 8 | *Hide toolbar* and *Show toolbar*; the slim case line; out of the tab order and the accessibility tree (`hidden`, not opacity); focus moves; the setting remembered; the shortcut in "?"; the Map's row too (proposal 3d); the canvas keeping its centre and zoom when it resizes |
| Shared: tests red first, plants, contrast probes, three looks | 4 | Every claim in the brief's "usual bar" has a case shown red first, and a plant for each |
| **Total** | **26** | About three and a half lane days. A and C share the toolbar, so build them together after B |

The estimate assumes the owner accepts the 1024 px answer in 3e. If strictness must stay in the row at 1024 with
every label at full length, add about 3 hours for a measured overflow menu.

## 2. Where the code differs from the brief's table (checked on main `0b1631b`)

1. **Strictness is not a row of its own.** It sits in `App.tsx`'s view toolbar (`role="toolbar"`, named *Graph view*,
   `.view-toolbar`, height `--h-canvas-toolbar` 36 px), about line 2051. On the Map the same row holds **Add site** and
   **Draw boundary** instead. Removing strictness from it leaves an empty row on the Graph, so A removes the whole row
   on the Graph.
2. **The graph toolbar is a different element.** It is `GlassCanvas`'s own `role="toolbar"` named *Canvas tools*
   (`.canvas-toolbar`), drawn **over the top of the canvas** (`position: absolute`), not as a row above it. Hiding it
   gives the drawing area its height, but the canvas element itself does not grow. Its groups are Select (lasso),
   Layout, Show (Communities, Grid, Previous positions, Labels ▾, Icons ▾, the communities status), and View (Clear the
   graph, Add files, Links among all, the link hide and show), then *Last change* (not drawn below 1100 px) and Details.
   **There is no "Entity type" picker**: entity types appear only inside *Labels* and *Icons*.
3. **The case line already names the open saved view**, after the case's switcher: "› Saved view: ‹name›" (Amendment 17
   decision 2). It also carries the cross-link **Open this case's data in the Ingest Studio ↗** (short form *Open in
   the Ingest Studio ↗*), which the brief's table leaves out. The proposals below keep it.
4. **The banner holds two things the brief does not list.** The **Shared/Private** tag (not only "shared"), and the
   sentence **Nothing in a saved view changes the case.** Notes from the drawing open a list *under* the banner's
   line, up to 240 px tall.
5. **The origin is worded differently.** The code says **"Opened from an alert"** with **← Back to the alert**, with
   no title. ADR-145 Amendment 4 (around line 27527) and ADR-144's later text say "From alert ‹title› · ← Back to the
   alert". B should take the alert's title if the opener passes it (`lensFromAlert` has the id; the title is at
   hand where the alert opens the view).
6. **Amendment 17 does not say "no jump", and today the canvas does jump.** Its words are only that the strip says
   *You are looking at the whole case.*; the reason (never a surprise) is in a code comment. Measured:
   - the strip is 31 px with the whole case and 37 px with a saved view, so the canvas moves **6 px** when one opens;
   - at 1024 px in the standard look, the case line wraps to two lines when a saved view's name joins it (41 → 73
     px), so the canvas moves **38 px**.
   B removes both moves. The tests in 3f hold it to zero.
7. **The strip pushes the canvas past the window.** The strip sits in the same box as the canvas, and the canvas is
   sized to the box. So the canvas runs **31 px (37 with a saved view) below the bottom of the window**: the page
   measures 931 or 937 px tall at 900. That much of the canvas, and its bottom-right zoom, are never on screen
   today. B fixes it by removing the strip.
8. **The announcement is a toast, not the control.** "Match strictness: Balanced — n merged, n split, n affected" is
   App's `Toast`, fed by `onChangeSummary`. A keeps that path unchanged. The control also shows **Custom (0.nn)** for a
   threshold none of the three stops name; the compact button must show that too.

## 3. Proposals

### 3a. The saved-view banner's other contents (B)

The case line with a saved view open reads:

> You are in the Glass · Case ‹switcher› · Saved views (7) · **Saved view: Vance network** · **Shared** ·
> **Details ▾** · **Back to the whole case** · reads ‹dataset›

- **Saved view: ‹name›** replaces today's "› Saved view: ‹name›", and moves after *Saved views (n)*, as the brief's
  sketch draws it. The name is ellipsised at fold step 2, with its whole words in `title`, as today.
- **Shared** or **Private** stays visible as a tag right after the name: the standard tag, or `govuk-tag` under
  GOV.UK. It is one word, and a reader must not lose sight that what they see is shared.
- **Details ▾** is one disclosure button (`aria-expanded`, `aria-controls`). It opens a panel hanging from the case
  line, drawn **over** the canvas so it moves nothing, closed by Esc and by pressing it again. It holds:
  - **n items could not be shown** (the count alone, `missingNote`'s words), when there are any;
  - **Nothing in a saved view changes the case.**;
  - **From alert ‹title›** with **← Back to the alert**, when it was opened from one;
  - **Notes from the drawing (n)**, as today's toggle and list, for a merged drawing.

  When the view came from an alert, the line also shows **← Back to the alert** itself, before *Back to the whole
  case*. A way back is never more than one press away.
- **Back to the whole case** is the same action as today, a link's look (GOV.UK's back link under GOV.UK). It is drawn
  last of the state so that "reads …" is the only thing after it.
- **Focus on opening.** Amendment 17 decision 3 moves focus to the strip. Proposed: focus moves to **Saved view:
  ‹name›**, a programmatically focusable span (`tabIndex=-1`) whose name is the whole state, "Saved view: Vance
  network, shared". The next Tab is *Details*, then *Back to the whole case*. Back still returns focus to *Saved views*.
- **Fold order.** A short line gives way in this order: (1) the cross-link's short words; (2) "reads …" ellipsised,
  then dropped (its words stay in `title` and in the Details panel); (3) the saved view's name ellipsised; (4) whole
  items wrap. *Back to the whole case* and *Saved views (n)* never fold away.
- **With no saved view**, the line ends **· Whole case** (plain text, not a control).

### 3b. The shortcut (C)

**Alt+Shift+T** (Option+Shift+T on a Mac), outside text fields, listed in "?" as "Alt+Shift+T — Hide or show the
toolbar". It is matched on `event.code === "KeyT"` so the Mac's Option character does not matter.

- **No collision.** Today's keys are "/" and "?" (global); F, L, G, \\, the arrows, Enter, Esc, Delete and Backspace on
  the canvas; Shift+F10 and ContextMenu; and Home and End in lists. None uses Alt. No major browser or screen reader
  binds Alt+Shift+T. Ctrl+Shift+T reopens a closed tab, so it is avoided.
- **Why not a bare letter.** WCAG 2.1.4 (Character Key Shortcuts) would require a way to turn it off or remap it.
  A modifier keeps it off a screen reader's single-key navigation.

### 3c. Remembering the setting (C)

The Glass remembers layout choices in the browser's `localStorage`:

| Choice | Key |
| --- | --- |
| Panel sizes | `ospreyflow.layout-sizes` |
| Side-panel order | `ospreyflow.side-panel-order` |
| Folded panels | `ospreyflow.side-panels-folded` |
| The canvas grid | `ospreyflow.canvas-grid` |

These keys are not per person. The Studio's mode is the one per-person choice: `ospreyflow.studio.mode.<username>`
(ADR-140 decision 3).

Proposed: **`ospreyflow.glass.toolbar.<username>`** in `localStorage`, `"hidden"` or absent, read before the first
draw so the Glass opens as left. This is per analyst on a browser, as the Studio's mode is. It follows nobody to
another machine, and no server-side preference store exists today. If the owner wants it to follow the analyst
across machines, that is a Conduit setting, and a separate decision.

### 3d. Map and Drawing board (C)

- **Map.** The view toolbar row (36 px) holds **Add site** and **Draw boundary**. MapLibre's own controls and the
  basemap switch are overlays on the map, not a row. Proposed: **the same control and the same remembered setting.**
  Hiding removes that row and slims the case line as on the Graph. *Hide toolbar* sits at the row's right end, and
  *Show toolbar* in the same place on the slim line.
- **Drawing board.** It has no toolbar row above a canvas. `BoardEditor`'s head is the board's heading, its
  *Shared with the case* or *Only you* tag, a *Read only* tag, and the board's actions. That is the board's title
  bar, and it is the only place a reader sees whose board it is. Proposed: **not hidden.** The setting does not
  apply there, and the case line is drawn in full on the Drawing board whatever the setting. Say if you want the
  board's actions to fold too.
- **Matrix and the others** have no toolbar row above a canvas. Nothing changes there.

### 3e. 1024 px wide: the toolbar does not stay one row (asks the owner)

These figures are measured on the real `GlassCanvas` toolbar. The compact strictness button is a stand-in, labelled
"Match strictness: Balanced ▾"; *Hide toolbar ▴* is too.

| Width | Today | With strictness | With strictness and *Hide toolbar* |
| --- | --- | --- | --- |
| 1024, standard | fits | 23 px short | 130 px short |
| 1024, GOV.UK | fits | fits | 80 px short |
| 1100 | fits | fits | 54 px short (standard), 4 px short (GOV.UK) |
| 1180 and wider | fits | fits | fits |

*Last change* is already not drawn below 1100 px, so it frees nothing at 1024. **Choose one:**

1. **(Recommended)** Below 1180 px, strictness's button shows its setting alone, "Strictness: Balanced ▾". Its
   accessible name stays "Match strictness: Balanced", and the full words are in its `title`. *Hide toolbar* becomes
   *Hide* with the same accessible name, "Hide toolbar". Estimated to fit with about 20 px to spare. To be measured
   before building.
2. Strictness moves under **Show ▾**'s menu below 1180 px.
3. Let the toolbar wrap to two rows below 1180 px. This loses the gain at 1024 (measured: 69 px, not 37 px).

### 3f. Tests, red first

Each case below is shown red first, and each has a plant in its real call-site shape (rule 15).

- **The two rows gone.** No `.view-toolbar` on the Graph and no strip region.
- **The state on the case line.** "Whole case", or "Saved view: ‹name›" with *Back to the whole case*.
- **Back with the toolbar hidden.** *Back to the whole case* is present and works with the toolbar hidden.
- **The setting.** It is remembered across a reload.
- **Focus.** Focus moves to *Show toolbar* and back, and the hidden toolbar is out of the tab order and the
  accessibility tree.
- **No jump.** The canvas's top is equal to the pixel when a saved view opens and closes, at 1440 and at 1024.
- **One move.** Showing or hiding the toolbar moves the canvas once, by the toolbar's height, with the graph's centre
  and zoom kept.
- **Contrast.** The probe runs on the three new controls in dark, light and GOV.UK.
- **Suites.** every-harness and keyboard pass in both looks.

## 4. Draft amendments, for the owner's ruling (not applied)

### ADR-145, Amendment 19 (draft) — the saved view's state on the case line; a toolbar that can be hidden

The owner, 16 November 2026: on the GOV.UK demo the rows above the graph took more than a third of the window.
Amends Amendment 17 decisions 2 and 3, and Amendment 15's case line.

1. **No strip.** The strip under the case line, with *You are looking at the whole case.* and the saved view's banner,
   is withdrawn. What is open is said on the case line, which is always drawn. So opening or closing a saved view
   moves the canvas by nothing. This property is now stated, and held by a test of the canvas's top to the pixel.
2. **The case line's state.** With no saved view open, the line ends **· Whole case**. With one open, it reads
   **Saved view: ‹name›** with its **Shared** or **Private** tag, **Details ▾**, and **Back to the whole case** (a
   link's look; GOV.UK's back link under GOV.UK).
   - *Details* holds the count of what could not be shown (a count, never which or why), **Nothing in a saved view
     changes the case.**, where it was opened from with its own way back, and *Notes from the drawing (n)* for a
     merged drawing.
   - A view opened from an alert also shows **← Back to the alert** on the line.
3. **Focus.** Opening a saved view moves focus to the line's **Saved view: ‹name›**, named with its tag. The next Tab
   is *Details*, then *Back to the whole case*, which returns focus to *Saved views*.
4. **The line folds** in this order: the cross-link's short words; then "reads …" (to its `title`); then the saved
   view's name ellipsised; then whole items wrap. *Saved views (n)* and *Back to the whole case* never fold.
5. **Match strictness** is a compact control in the Graph's toolbar, after Layout: its name and setting on a button
   that opens the same three-stop slider. The same announcement. The Graph's separate row is withdrawn.
6. **A toolbar that can be hidden.**
   - **Hide toolbar**, at the right end of the Graph's and the Map's toolbar, hides that toolbar.
   - The case line becomes one slim line: "Case ‹switcher› · Saved views (n) · ‹state› · **Show toolbar**".
   - The hidden toolbar is out of the tab order and the accessibility tree. The button states `aria-expanded` and
     `aria-controls`. Focus moves to *Show toolbar* on hiding and to *Hide toolbar* on showing.
   - Shortcut **Alt+Shift+T**, listed in "?".
   - Remembered per analyst in this browser (`ospreyflow.glass.toolbar.<username>`). One setting for the Graph and
     the Map. The Drawing board's head is not hidden.

**Tests.** The cases in the proposal's 3f. The red record is
`process/lanes/case/gates/glass-rows-reds.<head>.log`.

### ADR-144, Amendment 2 decision 4 (draft words)

Replace "A banner names the view and its *Private* or *Shared* tag, counts what it could not show without saying
which or why, and offers *Back to the case*." with:

> The case line names the view and its *Private* or *Shared* tag and offers *Back to the whole case*. Its *Details*
> counts what it could not show, without saying which or why (ADR-145 Amendment 19).

The decision's substance (a read-only lens) is unchanged.

## 5. The measured gain, 1440 × 900

**The drawing area** is the part of the canvas on screen below the graph toolbar: from the toolbar's bottom edge to
the bottom of the window.

**How "today" was measured.** On a harness built from the real components in App's own nesting: the brand frame with
the GOV.UK header and the demonstration banner, `ClassificationStrip`, `TopBar`, `ContextBanner` with the case's
dataset and *Saved views (7)*, App's view toolbar with the real `ResolutionThresholdControl`, `WholeCaseStrip` or
`ViewLensBanner`, the left rail, and the real `GlassCanvas`. It was measured in Chromium, after the fonts were loaded.

**How "proposed" was estimated.** It is the same harness with the two rows removed, which is how B and A remove them.
With the toolbar shown, a stand-in compact strictness button and *Hide toolbar* are in the real toolbar, and it
measured one row of 37 px. With the toolbar hidden, the toolbar is removed and the case line is kept at today's
height. That is an estimate: the slim line is no taller than today's line.

**What the figures do not include.** Any row App draws under the canvas, such as the timeline when it is open. That
row is the same in every state, so the gains hold.

| Look | Rows above the drawing area today | Today: drawing area (saved view open) | Proposed, toolbar shown | Proposed, toolbar hidden |
| --- | --- | --- | --- | --- |
| Standard, dark | marking 20, top bar 44, case line 41, strictness 36, strip 31 (37), canvas toolbar 37 | **691 px** (685) | **758 px**, +67 (+73) | **795 px**, +104 (+110) |
| Standard, light | the same | **691 px** (685) | **758 px**, +67 (+73) | **795 px**, +104 (+110) |
| GOV.UK | header and banner 56, marking 20, top bar 44, case line 28, strictness 36, strip 31 (37), canvas toolbar 37 | **648 px** (642) | **715 px**, +67 (+73) | **752 px**, +104 (+110) |

- In the GOV.UK look today, the rows above the drawing area take 252 of 900 px (28 %). With the toolbar hidden they
  take 148 px (16 %).
- Today the canvas element is 759 px (standard) or 716 px (GOV.UK), but 31 px of it (37 with a saved view) is below
  the window (item 2.7). That is why the drawing area today is smaller than the box.

The scratch harness and the measuring spec are kept outside the repository. They are not committed. Every figure
above can be regenerated from them.
