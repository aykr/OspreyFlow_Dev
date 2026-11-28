# GG3a, round 5: the one open case (the conductor, 28 November 2026)

The source is the verifier's record for tip `eaba2c838d` (`verify-eaba2c838d6bf1d5e7728eef52e77c5d781d017a.json`, one pass, one finding, a gap in a test). It is the only open case. The owner's refreeze of 28 November (your brief, "The owner's refreeze") is done at `eaba2c838d` and is not reopened. **This round is the one row below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | **The rest of `nameOf`'s chain is tested** (`apps/pages/server/views/searchWords.ts:285`: `name`, `title`, `value_normalised`, then `...IDENTIFYING` in `labelChoices.ts`'s order, then "No name"; scenario SP). In `search.test.ts`, add an SP1 case, or an SP17 plant, with two records: one with only `value_normalised`, and one with only one identifying property, for example `imei`. Assert each by its expected row header. Then **plant at the real call site** (rule 15): take `value_normalised` out of the loop at `:285`, and separately the `...IDENTIFYING` spread, and show each new case red. Also add a plant to `test_govuk_search_scenario.py`'s `react_problems`, or a new check there, that fails when `nameOf` stops using `IDENTIFYING`. Today it compares only the constant's text (about lines 455 to 466). | Both new cases are red under each plant and green without it, and the scenario check is red when `nameOf` drops the list. Give the commands and failing lines in your report. Your frozen checks are green. |

Then the verifier checks the round again, as usual. If it finds anything beyond this row, the slice goes to the owner.
