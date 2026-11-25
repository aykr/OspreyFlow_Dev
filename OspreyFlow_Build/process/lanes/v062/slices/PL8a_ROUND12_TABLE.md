# PL8a, round 12: a structural fix (the conductor, 25 November 2026, 07:46 UTC; the owner's option (a))

Rounds 9, 10 and 11 each found the same fault on a new path: a size the analyst never chose (the window's limit or the
page's `data-max` bound) written to `ospreyflow.layout-sizes`, which the React workspace also reads. Round 11's
verifier found it on **Home from a kept size** (`apply`, about lines 389 to 395: a `"default"` request is clamped, and
the skip-write guard holds only when the kept size is already the default, so 300, 320 or 105 is written). The owner
chose a structural fix (D225 item 3) over another case-by-case round. **This round is the three rows below and nothing
else; it is the last round.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **Home writes a clamped number.** | `panelFrameStore.ts` (`apply`) | **Home forgets the stored size for that panel** (removes its entry, so the default applies wherever the page is opened, clamped only when drawn), never writing any number. Red first: a kept size of 360, Home on a page with `data-max="320"`: the entry is gone, not 320; the same for the timeline. |
| 2 | **One rule for every write.** | `panelFrameStore.ts`, `panelFrameAttach.ts` | **A size is written only when it is the size the analyst's own action asked for** (a drag to a width, a key that moves by a step, a typed size), never a value produced by clamping to the window's limit or a page's bound. A clamp changes what is drawn, never what is stored. The one place that writes says so in its own words. |
| 3 | **A test over every path, so a fourth cannot be missed.** | a new test beside `panelFrameStore.test.ts` | For **each of the ten panel actions** × **each bound** (none; the window's limit; a page's `data-max` below the default) × **each starting state** (nothing stored; a size stored above the bound; a size stored below it): after the action, storage holds either nothing or exactly the size that action asked for, and never a bound. Show it red against today's code (it must catch Home from a kept size, and the first draw), and with row 2's rule removed. The existing test at about line 1661 (an analyst's own key press stores its size, bound included when the analyst asked for it) stays as it is. |

Out of this round: the page mount (PL8b), any other panel behaviour.
