# Slice GG4a · GG4 · A case's drawing boards and one board's items and links as tables, read-only, with no source column until GG4b (round 1 merges `away/GG4a`; the owner, 25 and 26 November 2026)

- **Build id:** GG4 (the drawing-boards row of `apps/pages/FUNCTIONS.yaml`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GR1a (the away branch carries GR1a's whole branch: GR1a merges first)
- **The owner's rulings:** 25 November (every proposal (a) of `slices/drafts_2026-11-25/GG4a.md` but question 2, where he gave the exception (b): GG4a starts before GG3) and 26 November, about 10:35 UTC (`RULINGS.md`): **question 1, the rule-3 stop: GG4a drops its source column until GG4b** (GG4b is the security part that withholds a drawn item's source document on every read path); question 0, **the Matrix is GG2d's**; question 2 "who made it" left out for 0.7.0 (names later through `display_names`, a backlog part); questions 3, 5, 6 and 7 (a). Question 4 (the board's `ceiling`) is GG4b's.

## Round 1 (D247; the conductor, 26 November 2026): merge `away/GG4a`, then drop the source column

**Your first step: merge the local branch `away/GG4a` into your branch** (the owner fetched it to the Mac; D247's exception
for away rounds). Keep both sides where main has moved. **It is built on `away/GR1a`'s tip `005dcbf`**: once GR1a is on
main, the merge brings only GG4a's own commits and its two changes to GR1a's files (the slash refusal in `cases.ts` and
its fixture; the boards link in `cases.njk`, with CS12, CK2 and Scenario CS's stop lists). If GR1a is not on main when you
start, stop and say so. Its report, `process/lanes/v062/away/GG4a_AWAY_REPORT.md` on that branch, is the record: read it
whole. **Every figure in it was taken on the server under its namespace.** The same list conflicts as GR1a's apply
(`build.mjs`'s entries, `routes.yaml`, `pageList.ts`, `FUNCTIONS.yaml`, the route-list pins, `spec/08`'s order): take
every page's entry; drop none.

Then **drop the source column** (the owner's ruling on question 1, (c)). On the away branch a drawn item's source is
shown in two places, and the round removes both:

1. **The drawn items' table:** `server/views/boardsWords.ts`'s `drawnColumns` ends in "Source note", and `noNote` ("No
   note given") is said where an item has no note. The away report names the leak that remains: a drawn item needs a
   note or a document (`DrawnAssertion._has_a_source`, `packages/schemas/boards.py` about lines 55 to 59), so "No note
   given" tells the reader a document is there. **The column goes, with `noNote`: Item, Type, Marking, Grading.**
2. **The links table:** `linkColumns` ends in "Source note", and a loaded link says `loadedSource` ("A dataset this case
   reads") in it. **The column goes: Link, Type, From, To, Drawn or loaded, Marking, Grading.** "Drawn or loaded" stays.
3. **The reader and the census:** the strict reader still refuses a drawn item with neither a note nor a document (a
   checked field: the body is not the model's), but draws neither. In the census (`boardsWords.ts` about line 96),
   `DrawnAssertion.source_note` moves from **drawn** to **checked** (or **left out**: say which and why), and
   `test_govuk_boards_scenario.py` follows.
4. **Scenario BD** (`spec/08`): BD3's and BD4's column lists and sentences lose the source; the "Left out, by field name"
   sentence names `source_note` and `source_document` as left out **until GG4b**, saying why in one clause. BD11's "a
   drawn item with no source" stays (a checked rule).
5. **A test that the board page sends no source (rule 12),** in `boards.test.ts`: over a board with an item drawn from a
   note alone, one from a document alone and one from both (and a drawn link carrying each), the page's whole HTML holds
   **none** of the notes' texts, no document id, and none of "No note given", "Source" or "A dataset this case reads" in
   the drawn or links tables. **Red first, at the real call site (rule 15):** restore the "Source note" column in the real
   `boardsWords.ts` and the test fails naming the note; restore only `noNote` and it fails naming those words. Restore
   from a saved copy, never by `git checkout`.
6. **The rest stays as built:** question 3 (`start` left out), 5 ("Drawing boards in this case"), 6 (409 with the options
   as sentences), 7 (the query-form address under GR1a's). Write the backlog row's words for question 2 in your report,
   as GR1a's (one row covers both); the conductor adds it.

Then show the report's table green here (`boards.test.ts`, `cases.test.ts`, `test_govuk_boards_scenario.py`,
`test_govuk_cases_scenario.py`, the GOV.UK keyboard and scripts-off specs) and run three of its plants again at the real
call site: the board read twice (BD9), a slash in `board` passed on (BD5), the withdrawn count said to every reader (BD6).

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/boards.test.ts` and `OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py`
(both from the away branch; neither is on main, so both are red on main; green after round 1, the no-source case included).

## Checks (pure; store ports pinned to 9)

As GR1a's, with the boards files: `npm test --workspace apps/pages`; `npm run lint`; `npm run typecheck`;
`node scripts/no_react_check.mjs`; the GOV.UK scenario tests (boards, cases, help, admin people), `test_functions_yaml.py`,
`test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`,
`test_ui_words_check.py`, `test_copy_says_no_client.py`, `tests/harness/test_pages_setting.py`; `ruff check .`.
(`test_doc_citations_check.py` is left out while main is red on it; the merge's full gate runs `citation-check`.)

## Out of scope

Any Conduit change (GG4b withholds the document and the ceiling); the source column's return (after GG4b, a page part:
the conductor cuts it); writes (GG4c, GG4d); the picture (GG4e); the Matrix (GG2d); a shared module for the repeated
`ask`/`refused`/`notFound` helpers (named in the away report).
