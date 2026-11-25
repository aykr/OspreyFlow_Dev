# Slice SE7c · SE7 · A case's gaps and assumptions never name to a reader a linked item they may not see, and a save never stores a link its saver cannot confirm (a security part; the owner, 25 November 2026)

- **Build id:** SE7 (rule 3: no count, placeholder or id reveals an item the reader may not see)
- **Dial setting:** balanced · **Rounds limit:** 8 · **After:** nothing
- **Never accepted narrower. Judged by the verifier, the server and the full gate** (the owner's word).
- **Round 1 merges the local branch `away/access-fix`** (the owner's word extends D247's exception to it, 25 November
  2026). Its reports: `process/lanes/v062/away/ACCESS_ASSESSMENTS_REPORT.md` (the finding, proven red) and
  `ACCESS_FIX_REPORT.md` (the fix, red to green, the plants), on that branch: read both whole.

## What (the finding, proven on the away round)

`GET .../gaps` sent a SECRET node's id to an OFFICIAL reader; `GET .../assumptions` sent a reader the id of a judgement
`GET .../judgements` hides from them (ADR-046); neither save checked its links, unlike a judgement's citations. The fix
(`services/api/assessments.py`, `app.py`; `spec/03` lines 631 to 634): a linked entity or judgement the reader may not
see is left out entirely, through the graph adapter's own answer under the reader's principal (rule 3), as
`list_visible_judgements` does; the saves refuse a link the saver cannot confirm, with one 422 `unverifiable_link` that
names only the ids sent and treats an absent id and a hidden one alike.

## Round 1

1. **Merge `away/access-fix`** into your branch (both sides where main has moved).
2. Run the frozen checks; show every case of its report's table green here, and its four planted faults red with the
   fault and green without.
3. **The one changed control** (`test_the_real_list_queries_are_the_ones_the_pool_models`, whose old assertion recorded
   the fault itself): say in your report exactly what it asserts now and why the old assertion could not stand.
4. **Every read path gets an access-control test (rule 4):** confirm the four routes each have one, and that nothing
   else reads the two tables (the report says only these four routes do: check it with a grep, and say so).

## Open for the owner (do not decide them)

The report asks two things, carried to the owner's report: the error's name `unverifiable_link` and its `link_ids` field
(modelled on `unverifiable_citation` and `citation_ids`); and the Glass's wording for a refused gap or assumption save
(today the generic "failed: 422"), which would be a Glass part. **Build as the away branch has it unless the owner rules
otherwise before the merge.**

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_assessment_links_access.py` (from the away branch): red on main (the finding),
green after round 1's merge.

## Checks

The acceptance; `test_doc_citations_check.py`;
`ruff check .`. `test_assessments.py` and `test_assessment_routes.py` need a live database: the merge's full gate runs them.
