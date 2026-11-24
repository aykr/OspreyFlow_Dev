# Slice RM1a · RM1 · The alert queue as a GOV.UK page (read-only)

- **Build id:** RM1 (alerts, rules and watches as pages; **the owner's ruling of 24 November 2026: "RM1 is alerts, rules and watches"**). ADR-152 decisions 1, 4, 5, 6, 7, 12; invariants I1, I2, I5, I7, I9, I10, I15 (`OspreyFlow_Build/spec/06_DECISIONS.md`; read the numbers in the file).
- **Dial setting:** balanced. **Rounds limit:** the dial's (8).
- **After: GR2a merged** (the GOV.UK tree, its switch, the gates' reach and the keyboard folder per tree). **Do not start before GR2a has merged.**
- **The owner's rulings of 24 November 2026 (in chat):** "a GOV.UK page may exist before its Default twin"; "keyboard tests in a folder per tree"; "a missing scenario is the first item of the part's brief"; no-oracle (CLAUDE.md rule 7) for what a reader may not see.
- **Every finding that names an access rule, a key, a credential or a security rule is the owner's.** An alert queue shows what a person may see of other people's cases: **be exact about what the Conduit filters and show nothing it did not send.**

## What exists (the scout's findings of 23 November; re-read each)

The function row `alerts-rules-watches` in `OspreyFlow_Core/apps/pages/FUNCTIONS.yaml` (about lines 298 to 304: slice R7, scenarios B12, B13, B14 and B20, route empty, "planned"). The React originals: `OspreyFlow_Core/apps/workspace/src/alerts/`, `watches/`, `strength/`. The Conduit: the alert queue's route and its store (`OspreyFlow_Core/services/api/alerts.py`, `AlertStore.list_queue`; `queue_scope` applies the reader's reach; find the route in `OspreyFlow_Core/services/api/app.py`, **the scout did not search for it**); `GET /v1/investigations/{id}/drawn-watches` (about line 5337). Read `OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md` for B12 to B14 and B20.

## What (in this order; each red first, planted faults at the shape the code really sees: rule 15)

1. **The scenario first (decision 12).** B12, B13, B14 and B20 exist: read them and pick the one the queue page proves (say which); if none states what a read-only queue page shows, write one into `spec/08` and name it in the row.
2. **The page (GOV.UK tree):** the alert queue **read-only** for one case or for the reader's queue (as the route offers; say which), server-rendered, scripts off: a table (caption, `th scope`: the alert, its kind, its state, when, the case) of the alerts the Conduit sends, with the empty and error cases in words. **No close, no assign, no rule or watch editing** (later slices). Route path follows decision 7. Words in `server/views/`, British English.
3. **Access control (rules 3, 4, 7: a fault here is stopped and reported).** The page reads only through the forwarder with the signed-in person's token; **filters nothing after retrieval; shows no count the Conduit did not send; an alert the reader may not see is not named or counted anywhere on the page**; a refusal shown in the same words as a missing page. Tests with the right and without it, against a fixture Conduit that models the real route's refusals.
4. **Rule 13:** no action beyond links; one keyboard case (tab order) in the GOV.UK tree's folder.
5. **Report:** the route used and its shape; the refusal words; what is left of `alerts-rules-watches` for later slices.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/alert-queue.test.ts` (new, vitest, red first) and `OspreyFlow_Build/tests/glass_trees/test_govuk_alert_queue_scenario.py` (new, pure, red first). **Say which folders the Python test walks** (a scan-map row is written from that; a builder cannot add it).

## Checks (pure; store ports pinned to 9)

The two new tests; the existing `apps/pages` vitest files; `tests/glass_trees/test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`; the words tests; `tests/test_doc_citations_check.py`; `npm run lint`, `npm run typecheck`, `node scripts/no_react_check.mjs`, `npm test --workspace apps/pages`; `ruff check .`; **`make -C OspreyFlow_Build design-check`** (the owner's rule D225 of 24 November 2026). **No `tests/test_layout.py`.** Before your final report run by hand what the conductor runs again: ruff and eslint on every file changed and the scan-map check for each new test.

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else. If your part needs another part's change that has not merged, stop and tell the conductor.

## Out of scope

Rules and watches pages, closing or assigning an alert (later slices); the alert monitoring figures (GR3a); any Conduit change; `apps/workspace`; the protected files. **A finding that names an access rule, a key, a credential or a security rule is stopped and reported, never accepted narrower.**
