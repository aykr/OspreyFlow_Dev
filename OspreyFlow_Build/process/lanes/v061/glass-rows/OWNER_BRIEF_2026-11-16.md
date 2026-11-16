# The Glass: fewer rows above the canvas, and a toolbar that can be hidden

From the owner, 16 November 2026. On the GOV.UK demo the rows above the graph take more than a
third of the window height, and analysts lose drawing space. I have agreed a design with my adviser.
The sketch `glass_rows_simulation.html` comes with this note: it shows each look in three states
(today, proposed with the toolbar shown, proposed with the toolbar hidden), with and without a
saved view open. It shows layout and wording only. Its heights, fonts and colours are approximate
and are not a specification: the product's own tokens and components decide those.

## When

**First item of v0.6.1. Not v0.6.0.** The v0.6.0 list is closed and its candidate is made. This must
not cause a new candidate, CI run or package test for v0.6.0, and nothing from it merges before
v0.6.0 is released. Add it to the v0.6.1 list in `v060/RULINGS.md` and give me an estimate from the
owning lane before building.

## What exists today (checked on main at 5af0e24, 16 Nov; check again before building)

| Row | Where |
|---|---|
| Case line: "You are in the Glass · Case … · Saved views (n) · reads …" | `apps/workspace/src/shell/ContextBanner.tsx`, rendered in `App.tsx` (about line 1995) |
| Match strictness slider, its own row | `apps/workspace/src/resolution/ThresholdControl.tsx` |
| "You are looking at the whole case." its own row; with a saved view open, the banner with *Back to the whole case* | ViewLensBanner.tsx in apps/workspace/src/views (removed by this item, 16 Nov) (`WholeCaseStrip`, `ViewLensBanner`; `App.tsx` about line 2240) |
| Graph toolbar: Layout, Entity type, Show, Clear the graph, Add files, Last change, Details | the graph view's toolbar |

Look at what is there before redesigning anything. If the code differs from this table, tell me
before you build.

## The three changes

### A. Match strictness moves into the graph toolbar

- The strictness row goes. Strictness becomes a compact control in the toolbar, after the Layout
  and Entity type pickers: its name and current setting ("Match strictness: Balanced"), which opens
  to the same slider when pressed.
- Same behaviour, same settings, same announcement to screen readers as today
  ("Match strictness: Balanced — n merged, n split, n affected"). Nothing about resolution changes.

### B. The "whole case" row goes; its state moves to the case line

- With no saved view open, the case line ends "· Whole case". The separate row saying "You are
  looking at the whole case." is removed.
- With a saved view open, the case line ends "· Saved view: ‹name› · Back to the whole case", with
  *Back to the whole case* as the same action as today.
- Everything else the saved-view banner carries today must still be reachable and must not be
  lost: that the view is shared, the count of items that could not be shown (a count only, never
  which or why), where it was opened from with its own way back ("From alert ‹title› · Back to
  the alert"), and *Notes from the drawing (n)* for a merged drawing. Propose where each goes on
  the case line, or behind one control on it, and show me before building.
- "reads ‹dataset›" gives way first when the line is short of room; on a wide window both stay.
- **This changes a recorded decision.** ADR-145 Amendment 17 keeps the strip always present so the
  canvas does not jump when a saved view opens. The new design keeps that property, because the
  state lives on a line that is always there, but the decision's words change. Draft the
  amendment (and any change to ADR-144 Amendment 2's banner wording) and bring it to me. I rule on
  it; do not treat this note as the amendment.

### C. The toolbar can be hidden

- A labelled button at the right end of the graph toolbar: **Hide toolbar**. Pressing it hides the
  whole toolbar row and slims the case line to one short line: "Case ‹switcher› · Saved views (n) ·
  ‹state›", with a labelled button **Show toolbar** at its right end, in the same place.
- The state on the slim line is B's: "Whole case", or "Saved view: ‹name› · Back to the whole
  case". *Back to the whole case* is on screen in every state.
- A plain show and hide. No open-on-click-then-close behaviour as in Word's ribbon.
- Remembered per analyst, so the Glass opens as they left it. Use whatever the Glass already uses
  to remember an analyst's layout choices; tell me which.
- A keyboard shortcut as well as the button; propose one that does not collide with the existing
  ones and list it in the "?" help.
- A label, never an icon alone: a new analyst who hides the toolbar must be able to find it again.
- Hidden means out of the tab order and out of the accessibility tree, not merely invisible.
  Focus goes to **Show toolbar** when the toolbar is hidden, and back to **Hide toolbar** when it
  is shown. The button states its state (`aria-expanded`, and `aria-controls` to the toolbar).
- Does it apply to Map and Drawing board? My intent is the same control wherever a view has a
  toolbar row above its canvas, one remembered setting for all. Tell me what each view has today
  and what you propose.

## What does not change

- The GOV.UK header, the demonstration banner, the marking line and the top bar (search, the view
  switch, More, Export) stay exactly as they are and are always shown.
- The case switcher and Saved views (n) stay on the case line in every state.
- No action is removed. Everything on the toolbar today is still there when it is shown.
- The word "view" stays reserved for saved views.

## Both looks, and the usual bar

- Standard look (dark and light) and GOV.UK look, in the same change. The GOV.UK look uses GOV.UK
  Frontend's own components and passes the accessibility checks; the every-harness and keyboard
  suites pass in both.
- **Contrast.** The Hide toolbar and Show toolbar buttons, and the strictness control, meet the
  contrast floor in all three themes. In my adviser's first sketch the Show toolbar label was
  unreadable in the light theme; that was the sketch's fault, but prove it is not so in the
  product (the contrast probe on those controls in each theme).
- **Narrow windows.** At 1024 wide the toolbar must stay one row with strictness in it. If it
  cannot, say what you would move (for example Last change, or strictness under More) and ask me.
- **No jump.** Opening or closing a saved view moves the canvas by nothing. Showing or hiding the
  toolbar moves it once, by the toolbar's height, and the graph keeps its centre and zoom.
- Tests red first, as usual: the two rows gone; the state on the case line in both cases; *Back to
  the whole case* present and working with the toolbar hidden; the remembered setting; focus and
  tab order; the three themes.

## What I want back, before any building

1. The lane and its estimate.
2. Anything in the code that differs from the table above.
3. Your proposal for the saved-view banner's other contents (B), the shortcut and the remembering
   (C), and Map and Drawing board (C).
4. The draft ADR amendment for my ruling.
5. The measured gain: the canvas height in each look at 1440 × 900 today, with the toolbar shown,
   and with it hidden.
