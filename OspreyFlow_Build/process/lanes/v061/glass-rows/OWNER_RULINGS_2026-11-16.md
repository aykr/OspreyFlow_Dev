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
