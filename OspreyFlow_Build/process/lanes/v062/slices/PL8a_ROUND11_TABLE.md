# PL8a, round 11: every open case (the conductor, 25 November 2026, 06:19 UTC)

From the round-10 verifier's record (tip `6cd1af1a1f`, 24 November, 17:02) and backlog row 28. **One open case; this
round is that row and nothing else.** The owner ruled on 24 November that this fault is accepted narrower and closed
by PL8b; the line refused that accept on a word ("key", in "a key that changes nothing on the screen", meaning a
keyboard key). This round closes it here instead, so PL8a can merge without the word.

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **A sash whose `data-max` is below the default (340 for the column, 130 for the timeline) writes the page's bound as the analyst's size, with no action by the analyst.** On the attach's first draw, `holdToBounds` (`OspreyFlow_Core/packages/glass-shared/src/layout/panelFrameAttach.ts` about lines 213 to 233) calls the writing setter with the page's bound; `apply` (`panelFrameStore.ts` about lines 349 to 355) compares only against the window's limits (`shownSizes(kept, limits)`), never against the page's `maxPx`, so the bound (320 or 100) is stored under `ospreyflow.layout-sizes`. The spec sentence this part added says "only a size the analyst chose is stored", and the React workspace reads the same key. | `panelFrameAttach.ts`, `panelFrameStore.ts` | Red first: a roomy viewport and empty storage, a sash with `data-max="320"` on the column and `data-max="100"` on the timeline: after the first draw, storage stays empty. Holding to the page's bound is a drawn size, never a stored one. **An analyst's own key press that moves the size (Home, the arrow keys) still stores it**, bound included: the test at about line 1661 of `panelFrameStore.test.ts` stays as it is. A planted change that stores on the first draw again must turn the new test red. |

Out of this round: everything else in PL8a; PL8b's page mount.
