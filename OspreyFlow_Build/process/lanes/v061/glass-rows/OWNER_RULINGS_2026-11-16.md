# The Glass rows (v0.6.1's first item): the owner's rulings, 16 November 2026

On case's PROPOSAL.md (3d93df5, merged bda4af1):

1. **Below 1180 px the visible labels shorten** to "Strictness: Balanced ▾" and "Hide", the full accessible names kept;
   the toolbar stays one row at every width.
2. **The saved view on the case line: the Details design as proposed.** "Saved view: ‹name› [Shared] · Details ▾ ·
   Back to the whole case"; Details opens over the canvas and holds the not-shown count (a count only), where it was
   opened from with its way back, Notes from the drawing (n), and "Nothing in a saved view changes the case";
   "← Back to the alert" also stays on the line.
3. **The shortcut is Alt+Shift+T**, listed in "?"; **the setting is remembered per signed-in analyst in the browser**
   (`ospreyflow.glass.toolbar.<username>`, as the Studio remembers its mode).
4. **Map has the same control and setting; Drawing board does not.**
5. **ADR-145 Amendment 19 is accepted as drafted** (amending Amendment 17's always-present strip and Amendment 15's case
   line, with ADR-144 Amendment 2's banner words), written when building starts.

Building starts after v0.6.0 is released, on the case lane; about 26 h (B first, then A and C together). Nothing merges
before the release.

The owner, 16 Nov ~08:00Z: **build now, in parallel with the last stages of v0.6.0; merge only after the release.**

6. **Below 1180 the visible "Layout" and "Show" captions are dropped** (the groups keep their names for screen readers), with the shorter words of ruling 1; the toolbar fits one row at 1024 in both looks (the owner, 16 Nov ~08:15Z).
7. **Compact words follow the toolbar's own width** (under ~1132 px, measured), not the window's; with a side panel docked on a small window (below ~900 px of toolbar) it wraps to two rows as today, hiding no action.
8. **The build is split** (the orchestrator, on case's recommendation, the owner having asked for it if viable): case builds B and owns ContextBanner.tsx (adding `slim` and `end` props first); case-b builds A and C, based on that props commit; B merges before A+C.
9. **The Ingest Studio link stays on the slim line**, in its short words (the owner, 16 Nov ~08:40Z): no action disappears when the toolbar is hidden.
10. **The case line fits 1024 by two more fold steps before any wrap** (the owner, 16 Nov ~09:20Z): the case switcher ellipsises (whole name in its title and accessible name, floor 8em), then "You are in the Glass" goes out of sight (still the region's name); Saved views (n), Back to the whole case, Details and the tag never fold. No jump at 1024, 1280 and 1440.
11. **The compact line is at 1220 px of toolbar** (case-b, measured in the product's fonts; ruling 7's ~1132 was an estimate); below 1220 the short words fit one row down to 912 px.
12. **The hide-toolbar shortcut changes from Alt+Shift+T** (the owner, 16 Nov ~09:40Z): Chrome on Windows and Linux binds Shift+Alt+T to focus its toolbar; a free key, checked against the major browsers and screen readers, is proposed by case-b before building.
13. **The shortcut is T on the focused graph canvas** (the orchestrator, under the owner's standing word for its recommendation, 16 Nov ~10:05Z; case-b's survey): no modifier combination is free across Chrome, Edge, Firefox, Safari, NVDA, JAWS and VoiceOver; T only while the canvas has focus, like F, L and G (WCAG 2.1.4). The Map: buttons only; T on the map is listed for v0.6.1.
14. **The slim line is never taller than the full one** (the orchestrator, under the owner's standing word, 16 Nov ~10:30Z): slim's last fold step shows the Studio cross-link as "Studio ↗" (its accessible name kept; amends ruling 9 to "its shortest words"); Show toolbar reads "Show" below 1220 like Hide; the standard look's wrapped case-line controls take 24 px. T leaves focus on the canvas; only the buttons move it.
