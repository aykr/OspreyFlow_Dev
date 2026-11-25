# PL8a, round 13: the structural fix again (the conductor, 25 November 2026; written 07:46 UTC for round 12, which the line never showed its builder: `round_table` returned round 10's; renamed for round 13 on the owner's word)

Rounds 9, 10 and 11 each found the same fault on a new path: a size the analyst never chose (the window's limit or the
page's `data-max` bound) written to `ospreyflow.layout-sizes`, which the React workspace also reads. Round 11's
verifier found it on **Home from a kept size** (`apply`, about lines 389 to 395: a `"default"` request is clamped, and
the skip-write guard holds only when the kept size is already the default, so 300, 320 or 105 is written). The owner
chose a structural fix (D225 item 3) over another case-by-case round. **This round is the three rows below and nothing
else.** Round 12 did row 1 only (Home stores the default, as its commit `1e63833` says; the line had shown it round 10's
table). Round 12's verifier found the fit-on-read, window-resize and draw paths still writing clamped sizes, and no test
crossing every action, bound and starting state: **rows 2 and 3 are this round's work.** Row 1 stays as round 12 left it
(Home stores the default) unless row 2's one rule needs it otherwise; say which in your report.

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **Home writes a clamped number.** | `panelFrameStore.ts` (`apply`) | **Home forgets the stored size for that panel** (removes its entry, so the default applies wherever the page is opened, clamped only when drawn), never writing any number. Red first: a kept size of 360, Home on a page with `data-max="320"`: the entry is gone, not 320; the same for the timeline. |
| 2 | **One rule for every write.** | `panelFrameStore.ts`, `panelFrameAttach.ts` | **A size is written only when it is the size the analyst's own action asked for** (a drag to a width, a key that moves by a step, a typed size), never a value produced by clamping to the window's limit or a page's bound. A clamp changes what is drawn, never what is stored. The one place that writes says so in its own words. |
| 3 | **A test over every path, so a fourth cannot be missed.** | a new test beside `panelFrameStore.test.ts` | For **each of the ten panel actions** × **each bound** (none; the window's limit; a page's `data-max` below the default) × **each starting state** (nothing stored; a size stored above the bound; a size stored below it): after the action, storage holds either nothing or exactly the size that action asked for, and never a bound. Show it red against today's code (it must catch Home from a kept size, and the first draw), and with row 2's rule removed. The existing test at about line 1661 (an analyst's own key press stores its size, bound included when the analyst asked for it) stays as it is. |

Out of this round: the page mount (PL8b), any other panel behaviour.
