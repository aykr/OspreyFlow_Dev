# RM1a, round 8 (the last): the shared lists after taking main in (the conductor, 27 November 2026, 03:58 UTC)

From the verifier's record at `fd7ff44`. There are four faults, all from round 7's merge of main: the tree now has seven
pages, but four GOV.UK scenario tests still say six. None of those files is in your frozen checks, so your green did not
run them; the merge's full gate will. **This round is the four rows below and nothing else.** It is round 8 of 8; the
owner's word allows it because these findings come from taking main in.

| # | Do | Done when |
| --- | --- | --- |
| 1 | `tests/glass_trees/test_govuk_boards_scenario.py:382`: the `expected` route list lacks `/alert-queue`, and `inputs()` reads the real `routes.yaml`, which now has seven routes. Make the list `routes.yaml`'s seven, in its order. | The file is green on your tip. |
| 2 | `tests/glass_trees/test_govuk_admin_people_scenario.py`: the message at about line 283 now says "seven pages", but the PLANTS at about lines 516-527 still expect "six pages". Make the plants expect the message's words. | The file is green, and each changed plant is still red when its fault is planted. |
| 3 | `tests/glass_trees/test_govuk_cases_scenario.py`: the same, for the message at about line 331 and the plants at about lines 561-562. | The same. |
| 4 | `tests/glass_trees/test_govuk_help_scenario.py`: the same, for the message at about line 280 and the plant at about line 415. | The same. |

**Before you finish, run every `tests/glass_trees/test_govuk_*_scenario.py` file on your tip**, not only these four, and
name each file and its result in your report. Any other route-count or page-list line that main's merge left stale is
fixed the same way. Change nothing outside these test files. Your frozen checks stay green.
