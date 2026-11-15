# v0.6.0 #4, Ask & Chat as a page: ready to merge (15 November 2026)

Branch `lane/case-b-v060-fullpage`, worktree `~/dev/osprey-wt/case-b`, rebased on main 70e0ff8. Playwright slot
`OSPREY_PORTS_SLOT=3`; offline pytest on ports 59991–59994 with `OSPREY_LANE` unset.

**Uncommitted, deliberately:** `keyboard/actionRegistry.ts`, as `registry-v060-fullpage.patch` (four ids:
`ask-and-chat-page-by-keyboard`; `close-the-questions-drawer-by-keyboard` renamed `back-from-ask-and-chat-by-keyboard`;
`select-a-graph-fact-from-the-ask-page-by-keyboard`; `show-all-from-the-ask-page-by-keyboard`). The orchestrator applies
it at the merge; each id has its `registerCovered`.

## The gates (`gates-acd7d4a.txt`, `plants-acd7d4a.txt`; the earlier round's at 8cc287d)

- Red on main (4 checks) and 33 plants, each red for its own named case, unplanted green.
- vitest 3626/3626; the keyboard suite with the patch 1082 passed and 5 skipped; every-harness 1152 passed;
  typecheck, lint and ruff clean; the two guide tests 13 passed.
- Not run here: `make -k ci`, `make test` (Docker is down on this machine; the step changes no route, store or
  schema; its Python is the two guide tests, run above). No live run: nothing on the Conduit changed.

## Lane reviews

- Review 2's items 1–4 done: Show all on graph through the page's hook (App and the harness); the stacking case in
  `search-results.spec.ts`, three looks; `containInnerScroll.ts` as admin has it; pid-capture's Back scoped; the
  cross-link, Escape and hand-off cases; `top-bar-harness`'s `opensPage`; the guide row; spec 02 §2.0d.
- Review 3: App's Show all held part by part (Graph current, the read by id and its body, a saved view closed first),
  each by a plant in App's shape; the cap's refusal now says *Save as a view* is "under the answer in Ask & Chat",
  since it is said over the graph after the page has gone (spec 02 §Show all, the guide, its test); Show all reached
  by Tab on the page; pid-capture's Back pressed only when the page is there. Found on the way: the guide test
  `test_user_guide_ask_items.py` read `const showAnswerOnGraph = async`, which item 1 removed; it follows the code now.

## The orchestrator's fix round (15 November 2026), and case's review of 052e265

- Either page opened while a document is read shows at once, the reader closed, focus on its heading (`stopReading`,
  handed to both hooks by App and the harness); jsdom and keyboard cases.
- Help's panel takes focus as it is asked for and only then (`App.tsx`'s `WelcomeFocusedOnce`; `welcome/` untouched);
  and one panel is mounted while a document is read over either page, never two (case's n1).
- `containInnerScroll.ts`'s comment says Ask & Chat is a page (on the orchestrator's word; admin to be told).
- The page title on `var(--lh-19)` (case's n3); no gate checks line-height tokens, so no test holds it.
- The CARRIES rows (the shared frame; Show all's canvas half) are the orchestrator's, on main.

## For the orchestrator at the merge

- **Outside the map, to ratify:** `OspreyFlow_Core/docs/user-guide.md` (§6's words and the 1.72 row: docs' file);
  `keyboard/top-bar-harness.tsx`, `search-results-harness.tsx` and `search-results.spec.ts` (at review 2's direction);
  `OspreyFlow_Build/tests/test_user_guide_ask_items.py` (case-b's #5, the cap's words and the `async`).
- **Rebase:** ADR_RESERVATIONS.md met ADR-114 Amendment 48 and ADR-148 Amendment 20 at the same place; both rows kept
  with Amendment 18's.
- **Carried:** in CARRIES.md (the orchestrator's rows).
