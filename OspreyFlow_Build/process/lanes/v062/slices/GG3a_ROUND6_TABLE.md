# GG3a, round 6: take main in after GG3b, and move Scenario SP (the conductor, 28 November 2026)

The owner's word of 28 November, about 10:45 UTC (rule 5, no round spent). GG3b's merge put its Scenario DR after Scenario AQ in `spec/08_ACCEPTANCE_SCENARIOS.md`, where yours sat too. **This round is the one row below and nothing else.** Round 5's open case is done and verified at `3d5dfd734e`.

| # | Do | Done when |
| --- | --- | --- |
| 1 | **Take main in.** Then **move your whole Scenario SP section so that it sits directly after Scenario BD and before Scenario AQ** (about line 1015 on main), not at the end of the file. Change no word of it, and no other line of `spec/08`; keep main's other sections exactly as main has them. GA1a moves its Scenario AC to a different place (after Scenario TS), so the two of you touch different lines and merge together. | Main is an ancestor of your tip; `git diff main -- OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md` shows only your section added, after BD; your scenario file and frozen checks are green. |

Then the verifier checks the round again, as usual.
