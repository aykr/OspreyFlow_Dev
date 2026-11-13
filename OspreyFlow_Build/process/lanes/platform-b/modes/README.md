# platform-b, step modes (13 November 2026)

ADR-145 Amendment 13 (the toggle reads *Graph · Drawing board*, each mode's one-line note) and ADR-144
Amendment 3 (*Views ▾* by the graph), at the owner's rulings of 13 November, on the orchestrator's
reservations. Offline only; nothing on the server.

- `red-first.raw.txt`: every new or changed test shown red with a plant in the shape the code really takes,
  each restored by `git checkout` afterwards (rule 15).
- `action-registry.diff`: `keyboard/actionRegistry.ts` (shared, so not committed): VIEW_ACTIONS gains
  `open-a-view-from-views-by-the-graph-by-keyboard`; SHELL_ACTIONS' `banner-sections-by-keyboard` comment.
- `every-harness.diff`: `a11y/every-harness.spec.ts` and `a11y/contrastFindings.json` (shared): the
  Views menu's three states scanned; Amendment 8's target-size entry for *Boards (coming)* taken out (no
  longer reported); the open *More views* menu's covered nodes listed (dark, light: the note's separator;
  GOV.UK: *Drawing board* and a separator).

The GOV.UK context row's heights (places harness, the demonstration's banner):

| Width | GOV.UK | OspreyFlow |
| --- | --- | --- |
| 1440 | 32 px, the note in the row (was 32) | 41 px (was 41) |
| 1024 | 66 px, the note and the cross-link on a line under the row (was 32) | 81 px, the cross-link under the row (was 41) |
