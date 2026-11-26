# Slice GG3a · GG3 · The case's search panel on the GOV.UK tree, read-only and scripts off, laid out as PL8's scripts-off frame (the owner, 26 November 2026)

- **Build id:** GG3 (the `search` row of `apps/pages/FUNCTIONS.yaml`, about line 221)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GR1a. **It starts after GR1a merges, by the
  owner's exception** (26 November, about 10:35 UTC, `RULINGS.md`: "Early starts: … GG3a after GR1a"), not after GG2b
  and PL8's mount: this is question 2's (b).
- **The owner's rulings:** the draft `slices/drafts_2026-11-25/GG3a.md`, every proposal (a) except question 2 (the
  exception above), with the 26th's correction. Read the draft whole.

## The rulings, as built

1. **Q1 (a):** the case's search panel, read-only, scripts off: a `GET` form (the words, the group and the filters the
   route offers) whose server half calls `POST /v1/investigations/{id}/search` once (about `app.py:6685`), and the results
   as a table in the route's order, a page at a time (`page`, `more`). Laid out as PL8's scripts-off frame (the panel
   open in its normal state, no controls: the owner's PL8 ruling 3), with the `data-action` and `data-id` hooks PL8's
   attach function reads. Adding a result to the working set is GG2b's.
2. **The 26th's correction:** PL8a merged (`1d16bb2`), and `packages/glass-shared/src/layout/panelFrameStore.ts` is on
   main. Read it for the hook names; mount no frame (PL8b, not drafted, does that).
3. **The address is GR1a's query form, `/cases/search?case=…`,** as GR1a merges it (the draft's `/cases/{case_id}/search`
   needs GR1c, not ruled). If GR1a merges with another form, follow GR1a's and say so.
4. **Q3 (a) to Q8 (a):** a `GET` page turned into one `POST` with the person's token (no anti-forgery token for a `GET`);
   a `limited` result said in words with `limited_reason` above the table, "about N" when `counts_exact` is false (rule
   2); one `POST` per search pinned (one audit row); exactly the route's `results` and `nodes`, no internal id outside a
   link's own path; scenario SP written first; the strict reader and the field census over `SearchPageResponse`, the
   fixture refusing as the route does (422 over the limit; 404, or 403 for a level too low).
5. **Before relying on them, say what calls `/v1/search` and `/v1/suggest`** (`apps/workspace/src/search/GlobalSearch.tsx`
   about line 67): the draft found no Conduit route at those paths. Report it; change nothing in the workspace.

## The table of cases

The draft's table, cases 1 to 14, each red first at the real call site (rule 15).

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/search.test.ts` and `OspreyFlow_Build/tests/glass_trees/test_govuk_search_scenario.py`
(both new; red on main, green after).

## Checks (pure; store ports pinned to 9)

`npm test --workspace apps/pages`; `npm run lint`; `npm run typecheck`; `node scripts/no_react_check.mjs`; the GOV.UK
scenario tests (search, cases, help, admin people), `test_functions_yaml.py`, `test_tree_parity.py`,
`test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`, `test_ui_words_check.py`,
`test_copy_says_no_client.py`, `tests/harness/test_pages_setting.py`; `ruff check .`. (`test_doc_citations_check.py` is
left out while main is red on it; the merge's full gate runs `citation-check`.)

## Out of scope

Adding to the working set (GG2b); the inspector, the timeline and documents (later GG3 slices); suggestions as you type;
the frame's controls and their keyboard cases (PL8's mount slice); any graph drawing; any Conduit change;
`apps/workspace`.
