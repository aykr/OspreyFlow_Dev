# Slice AD3a · AD3 · The Admin People list as a GOV.UK page (read-only)

- **Build id:** AD3 (Admin as pages; **the owner's ruling of 24 November 2026: "AD3 is Admin"**). ADR-152 decisions 1, 4 ("for the GOV.UK theme, every function is built this way, Admin included"), 5, 6, 7, 12; invariants I1, I2, I5, I7, I9, I10, I15 (`OspreyFlow_Build/spec/06_DECISIONS.md`; read the numbers in the file).
- **Dial setting:** balanced. **Rounds limit:** the dial's (8).
- **After: GR2a merged** (the GOV.UK tree, its switch, the gates' reach and the keyboard folder per tree). **Do not start before GR2a has merged.**
- **The owner's rulings of 24 November 2026 (in chat):** "a GOV.UK page may exist before its Default twin"; "keyboard tests in a folder per tree"; "a missing scenario is the first item of the part's brief"; "**a non-viewer gets 404, the same as a missing thing**" (the owner ruled it for the report route; the same no-oracle rule applies here by CLAUDE.md rule 7: say what the People route answers).
- **Every finding that names an access rule, a key, a credential or a security rule is the owner's.** This part reads who may sign in: **be exact about rights.**

## What exists (the scout's findings of 23 November; re-read each)

The function rows `admin` and `needs-you` in `OspreyFlow_Core/apps/pages/FUNCTIONS.yaml` (about lines 306 to 320: slice R7, scenario empty, route empty, "planned"; `admin` is "every section of `W/admin/sections.json`, 2 still coming"). The React original: `OspreyFlow_Core/apps/workspace/src/admin/sections/People.tsx` and `OspreyFlow_Core/packages/glass-shared/src/admin/api.ts` (`peopleRows`, about line 237). The Conduit routes (`OspreyFlow_Core/services/api/app.py`): `/v1/admin/people` (about line 17209), `/v1/admin/people/rows`, `/v1/admin/roles` (about 17309), each behind `require_right(Right.MANAGE_PEOPLE)`. The pages server's `/v1` forwarder (`OspreyFlow_Core/apps/pages/server/v1.ts`, `forward.ts`) carries the person's token and nothing else.

## What (in this order; each red first, planted faults at the shape the code really sees: rule 15)

1. **The scenario first (decision 12).** `admin` has none: write the People list's scenario into `spec/08` (what the page shows, who may see it, that it works with scripts off); put its id in the `admin` row (slice AD3a) **only for this page**; leave the row's other sections as they are, and make `test_functions_yaml.py` pass with the row's route still empty where the GOV.UK page is not complete.
2. **The page (GOV.UK tree):** the People list, **read-only**, server-rendered, scripts off: a table (caption, `th scope`: the person's name, roles, state: read the rows route's shape) of the people the Conduit sends, with the empty and error cases in words. **No invite form, no edit, no write** (those are later slices). Route path follows decision 7. Words in `server/views/`, British English.
3. **Access control (rules 3, 4, 7: a fault here is stopped and reported).** The page reads only through the forwarder with the signed-in person's token; **it filters nothing after retrieval** (decision 5); **a person without `MANAGE_PEOPLE` gets the Conduit's refusal shown in words, the same words as for a page that does not exist** (no oracle); **no count of people the reader may not see**. Tests with the right and without it, against a fixture Conduit that models the real route's refusals (read the route's refusal shape).
4. **Rule 13:** the page adds no action beyond links; one keyboard case (tab order) in the GOV.UK tree's folder.
5. **Report:** the route path; the refusal words; what is left of `admin` and `needs-you` for later slices.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/admin-people.test.ts` (new, vitest, red first) and `OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py` (new, pure, red first). **Say which folders the Python test walks** (a scan-map row is written from that; a builder cannot add it).

## Checks (pure; store ports pinned to 9)

The two new tests; the existing `apps/pages` vitest files; `tests/glass_trees/test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`; the words tests; `tests/test_doc_citations_check.py`; `npm run lint`, `npm run typecheck`, `node scripts/no_react_check.mjs`, `npm test --workspace apps/pages`; `ruff check .`; **`make -C OspreyFlow_Build design-check`** (the owner's rule D225 of 24 November 2026). **No `tests/test_layout.py`.** Before your final report run by hand what the conductor runs again: ruff and eslint on every file changed and the scan-map check for each new test.

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else. If your part needs another part's change that has not merged, stop and tell the conductor.

## Out of scope

The invite form and every write (a later slice); any other Admin section; any Conduit change; `apps/workspace`; the protected files. **A finding that names an access rule, a key, a credential or a security rule is stopped and reported, never accepted narrower.**
