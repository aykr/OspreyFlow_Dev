# Slice GG3b · GG3 · One document of a case in the reader, read-only, on the GOV.UK tree (round 1 merges `away/GG3b`; the owner, 26 November 2026)

- **Build id:** GG3 (the document reader)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GR1a (the away branch is built on `away/GR1a`'s tip, `005dcbfca`; it starts after GR1a by the owner's exception)
- **The owner's rulings** (26 November, about 10:35 UTC, `RULINGS.md`): every proposal (a) of
  `slices/drafts_2026-11-26/GG3b.md`; **question 6 (a): a content type a browser would run as a page is a STOP (security),
  reported, never worked around**; 6b (a), the `nosniff` test. The away round came in on the owner's word of about 13:40
  UTC: "bring into the line like GR1a, round 1 merges the branch". "Who made it" is left out for 0.7.0.

## Round 1 (D247; the conductor, 26 November 2026): merge `away/GG3b` first

**Your first step: merge the local branch `away/GG3b` into your branch.** It carries `away/GR1a`'s commits beneath its
own; GR1a merges to main first, so the merge brings only GG3b's. Keep both sides where main has moved (take every page's
entry in `build.mjs`, `routes.yaml`, `pageList.ts`, `FUNCTIONS.yaml`, `glassShared.d.ts` and the route-list pins; drop
none). Its report, `process/lanes/v062/away/GG3b_AWAY_REPORT.md` on that branch, is the record: read it whole. **Every
figure in it was taken on the server under its namespace.**

Then:

1. **The security stop did not arise on the away round** (no file type a browser runs as a page reaches this page: its
   section "The security stop: did not arise"). **Re-read that section's reasoning against main as it is now.** If any
   writer, media map or route now lets such a type through, STOP and say so at the top of your report.
2. **Show the report's table green here:** `document.test.ts`, `test_govuk_document_scenario.py`, the keyboard and
   scripts-off specs (`keyboard/document.spec.ts`, `scripts-off/document.spec.ts`, by `npm run test:keyboard:govuk
   --workspace apps/pages`), and the route-list pins. Run three of its planted faults again at the real call site
   (rule 15), one of them the `nosniff` header's; restore each from a saved copy, never by `git checkout`.
3. **The owner's answers (26 November 2026, 12:15 UTC; `RULINGS.md`):**
   - **Q1 (the email's graph ids, rule 3): a separate Conduit security part, SE9d** (the route withholds `sender_id`,
     `recipient_id` and `edge_id` from a reader who may not see them). **Change nothing in the route here.** The page
     already draws none of them (DR3 draws the sent time only): **keep it so; a test that fails if the page draws
     `sender_id`, `recipient_id` or `edge_id` must exist, or write it, red first.**
   - **Q8 (i): a PDF is served as a download, never shown in the page.** `document_file_route`
     (`OspreyFlow_Core/services/api/app.py` about lines 7938 to 7959) answers `Response(content=data,
     media_type=content_type)` for every type; the media store maps `.pdf` to `application/pdf`
     (`packages/adapters/media_objectstore/__init__.py`, `EXTENSIONS` about line 23, `content_type_of` about line 53).
     **Make the route answer `application/pdf` with `Content-Disposition: attachment`** (a file name of the route's own,
     never one a loader supplied; say which), and the page draw no PDF inline (no `img`, `iframe`, `object` or `embed`
     for it; at most a link to the download). The page service's forwarder already copies `Content-Disposition` back
     (`apps/pages/server/forward.ts:89`); pin that for this route. **Red first (rule 15):** a route test and a page test,
     each failing with the header removed (or the PDF drawn inline) at the real call site, green after.
   - **Q8 (ii): a separate security part, SE9e** (a recipe binds `object_ref` on a Document only to a file of the same
     dataset). Change nothing for it here.
   - **Q8 (iii): the PID pack's picture references do not match the store's shape** (404): backlog row 46. Change
     nothing for it here.
   - **Q2** (the file through the front door, an ADR-152 decision 7 matter) is still the owner's: change nothing for it.
   - The rest (Q3 to Q7, Q9) are built in their conservative reading (everything else (a)): leave them as built and list
     them at the top of your report.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/document.test.ts` and `OspreyFlow_Build/tests/glass_trees/test_govuk_document_scenario.py`
(both new on the away branch; neither is on main, so both are red on main and green after round 1's merge).

## Checks (pure; store ports pinned to 9)

As GR1a's, with the document scenario: `npm test --workspace apps/pages`; `npm run lint`; `npm run typecheck`;
`node scripts/no_react_check.mjs`; the GOV.UK scenario tests (document, cases, help, admin people),
`test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`,
`tests/harness/test_pages_setting.py`; `ruff check .`.

## Out of scope

Any Conduit change but Q8 (i)'s header on `document_file_route` (Q1 is SE9d's, Q8 (ii) SE9e's, question 3 a later part);
the front door (question 2); a list of
a case's documents; uploads.
