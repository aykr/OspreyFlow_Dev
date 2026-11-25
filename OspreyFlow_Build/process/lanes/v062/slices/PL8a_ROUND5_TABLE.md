# PL8a: every open case before round 5 (24 November 2026, 08:45 UTC; the conductor, from the four verifier records)

**The owner's rule (21 November 2026): no round from 5 on starts without a table of every open case.** Two cases are open (A and B); **every case raised in rounds 1 to 4 is closed** (the limits are held by one writer for every size, and the table-driven test walks every entry point: round 4). Round 5 closes A and B and **adds nothing else.**

| # | Case | Raised in | Kind | Status at `d313f66de2` |
| --- | --- | --- | --- | --- |
| 1 | The panel frame's upper limits are held only through the markup's `data-max`; no limit when none is given. | Round 1 | Fault in behaviour | **Closed** (rounds 2 and 4). |
| 2 | The round-2 cases repaired the fault they were meant to catch (`getState()` enforced before each assertion). | Round 2 | Gap in a test | **Closed** (round 3). |
| 3 | The Home key skipped the live limits; the third round of one kind of fault. | Round 3 | Fault in behaviour | **Closed** (round 4: one writer, a table over every entry point). |
| **A** | **The attach draws `aria-valuenow` and `aria-valuemin` on every sash but never `aria-valuemax`, and cannot: the store keeps the live upper limit to itself** (`panelFrameAttach.ts` about lines 129 to 143; `PanelFrameState` carries no limit). A page's keyboard sash then describes a range that does not contain its value (WAI-ARIA: a focusable `separator` with no `aria-valuemax` implies 100). The workspace sets all three from the live limit (`apps/workspace/src/layout/Sash.tsx` about lines 77 to 79). | Round 4 | Fault in behaviour | **OPEN: fix this round.** Put the live upper limit in the store's state (read through the one limit function), draw `aria-valuemax` from it on every sash, and redraw it when the window changes. **A test asserts `aria-valuemax` for the column and the timeline under each of the three viewports of round 4's table, and the value never differs from the limit the writer applies** (red first: remove the draw). |
| **B** | **The new spec table's scripts-off cells for the timeline promise a state that cannot exist with no script:** "its plot shown at the height kept or 130px" (`spec/02_GLASS_FRONTEND.md` about line 395; line 401 is ambiguous in the same way). The kept height lives only in `localStorage` (about line 375: never sent to the server), which nothing reads with no script. The column's row handles it correctly ("Open at 340px"). | Round 4 | Fault in the spec text | **OPEN: fix this round.** Say "130px" (the default) in both timeline rows, as the column does; **and read every other scripts-off cell of the table for the same promise** (a cell that says "kept" with no script) **and say in the report which you changed.** `test_panel_frame_spec_table.py` holds the wording (extend it: no scripts-off cell names a kept size). |

## What you do in round 5

1. Close **A and B**, red first. **Nothing else:** no new action, no page, no other file.
2. Re-run your slice's checks, the scan-map check and `make -C OspreyFlow_Build design-check` by hand.
3. **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**
