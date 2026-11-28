# Slice GR4c · GR4 · The pack-trends scenario finds the add-item route by its text, not by a line number

- **Build id:** GR4 (the board page's scenario; slice id GR4c).
- **Kind:** test-only. The owner's ruling of 28 November 2026, about 06:05 UTC (RULINGS.md, item 3). **Cut now and merged first:** SE9h, SE9j and SE9k merge after it.
- **After:** nothing.
- **Status of this brief:** written by the conductor on the owner's word. The cause is known. Do not rerun anything on the server.

## Why

`OspreyFlow_Build/tests/glass_trees/test_govuk_pack_trends_scenario.py`'s `citation_diff_problems` (about line 265) reads each `` `file.py:N` `` that the owner's citation correction (`OspreyFlow_Build/process/lanes/v062/away/GR4a_ADR152_DECISION10_CITATION.diff`) adds. It then checks that line N of the file holds `CITED_LINES[file]` (about line 69).
- For `services/api/app.py` that is `'/packs/{pack_id}/items"'`, cited at `app.py:19905`.
- **Any part that adds a line above the route turns the test red, though nothing it cites has changed.** SE9h adds 44 lines, SE9j 92 and SE9k 10: each is red on the merge with main (the server's runs 06d5250c636de44c and 43705953c02d229d, and the Mac). SE9f already lost a round to the same drift.

## What

1. **The correction cites the route by its text.**
   - Change the diff's added lines so that `services/api/app.py` is cited with no line number, by the route it means: for example `` `services/api/app.py` (the `POST …/packs/{pack_id}/items` route) ``.
   - Keep the rest of the correction's words as they are.
   - Leave `packages/schemas/packs.py:128` as it is.
   - The diff is the owner's to apply; you change only the diff file, never `spec/06_DECISIONS.md`.
2. **The check finds a text citation in its file.**
   - A cited file with no line number must contain `CITED_LINES[file]` somewhere: one occurrence is enough, and none is red.
   - A cited file with a line number keeps today's line check.
   - The other checks stay as they are:
     - a file in `CITED_LINES` that the correction no longer cites stays red;
     - a cited file that the check does not know stays red.
3. **Red first (rule 15), at the real shape.** Add a case that takes main's real inputs and inserts lines above the add-item route in `app.py`'s text, the shape SE9j's merge produces. It asserts no problem is found.
   - The case is red on main, failing for the line number reason; give its failing line in your report.
   - It is green after your change.
4. **The planted faults stay meaningful.** Today's "a cited route line that drifted" case (about line 566) no longer applies to `app.py`. Change it so each red case fails for its own reason, and give each case's red reason in your report:
   - a citation whose route text is not in `app.py` is red;
   - a drifted line number on `packs.py` is red;
   - past the end of the file is red;
   - a file no longer cited is red.
5. **Not in scope:** product code, any other scenario file, `spec/`, the slice line, the CI workflow.

Binding: process/CLAUDE.md rules 12 and 15; British English.

## Acceptance test

`OspreyFlow_Build/tests/glass_trees/test_govuk_pack_trends_scenario.py`, with the new case red on main.

## Checks

- The scenario file and the glass-trees tests that read the same lists: `test_functions_yaml.py`, `test_doc_citations_check.py`.
- Ruff.

**Before your final report, run by hand the cheap checks the conductor will run again before the merge.**
