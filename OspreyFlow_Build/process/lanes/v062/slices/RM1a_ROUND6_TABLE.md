# RM1a, round 6: the row's route stays empty until the whole function has its page (the conductor, 26 November 2026, 14:35 UTC)

From the round-5 verifier's record (tip `be512dc3c6`): one fault. Round 5's plain-name guard and the test Conduit stand.
**This round is the row below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | **`FUNCTIONS.yaml` about line 329:** the `alerts-rules-watches` row (the whole function "Alerts, rules, watches, connection strength") gets `route: "/alert-queue"`, but this slice builds only the read-only queue. `tree_parity.py` `_row_has_page` (about 122-125) counts a row with a route in `routes.yaml` as covered, so the GOV.UK tree reads this function as done early (the header, lines 19-20: `route` is "EMPTY until the function has its GOV.UK page"). **Do as main's siblings do:** keep the row's `route: ""` with a comment saying the function is not complete (AD3a's `admin` row about 332-339, GR4a's `reports-trends-shown-together` about 304-310), add the row to `help.test.ts`'s `INCOMPLETE_ROWS`, and keep `/alert-queue` in `routes.yaml` and the page list as the page it is. Correct every test that pinned the wrong state. | `govuk_tree_state()` does not count `alerts-rules-watches` as covered (a test says so, red with the route put back); `help.test.ts` green with the row in `INCOMPLETE_ROWS`; `/alert-queue` still served; your frozen checks green. |
