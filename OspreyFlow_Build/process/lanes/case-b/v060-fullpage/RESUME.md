# v0.6.0 #4, Ask & Chat as a page: where it stands (paused 15 November 2026, 12:05Z, for the accounts switch)

Branch `lane/case-b-v060-fullpage`, worktree `~/dev/osprey-wt/case-b`, rebased on main 079ec60 (#3 and #5 in). Head
ba15aff. Playwright slot `OSPREY_PORTS_SLOT=3`. Offline pytest on ports 59991–59994 with `OSPREY_LANE` unset.

**Uncommitted, deliberately:** `keyboard/actionRegistry.ts`, with `registry-v060-fullpage.patch` applied (three ids:
`ask-and-chat-page-by-keyboard`; `close-the-questions-drawer-by-keyboard` renamed `back-from-ask-and-chat-by-keyboard`;
`select-a-graph-fact-from-the-ask-page-by-keyboard`). Never commit it; regenerate the patch with `git diff` after any
registry change.

## Done

- `questions/AskPage.tsx`, `askPage.css` and `useAskPage.ts` (one hook, used by App, `places-harness`,
  `questions-harness` and `harness.tsx?questions=page`). App wired; the drawer is gone. The orchestrator approved
  `LeftRail.tsx`'s `opensPage` and `focusRailOpener`, and nothing else in that file.
- ADR-145 Amendment 18 (reserved, written), spec 02 §2.0d and the rail paragraph, user guide §6 *A page of its own*,
  the rail row and version row 1.72, and the guide test. A friction fragment.
- The gates at ba15aff, all green (`gates-ba15aff.txt`): vitest 3616/3616; the whole keyboard suite with the patch,
  1075 passed and 5 skipped; every-harness 1152 passed; tsc and eslint clean.
- Lane review 1: all ten items fixed. Lane review 2 (at ba15aff): its items are below.

## Left to do (lane review 2), in this order

1. **Show all on graph on the hook.** App.tsx `showAnswerOnGraph` repeats `leavePages()` and the canvas focus by hand.
   Route it through `ask.showOnGraph(() => void showAnswerOnCanvas(...))`, keeping `closeLens` and `setView("graph")`
   first. Wire `onShowAll` into `harness.tsx`'s `AskPageOverCanvas` the way `?questions=1` wires it (harness.tsx:583),
   and add a keyboard case in `questions.spec.ts`: Show all on the page leaves it, the items are selected on the real
   canvas, and focus is on the canvas.
2. **Stacking.** Copy `search-results.spec.ts:165–214` for the Ask page. Add an Ask mode to
   `search-results-harness.tsx?canvas=1` drawing `AskPage` where App draws it, not in a fixed box, and check in three
   looks that no point of the page shows the canvas toolbar or `.canvas-corner`.
3. **Ownership.** Revert the comment in `src/brand/containInnerScroll.ts`, which is Rules' file. Ask the orchestrator
   about `live/pid-capture.spec.ts` and `live/capture-kit.ts`, which are in no lane's row. Scope pid-capture's Back to the
   page: `getByRole("region", { name: "Ask & Chat" }).getByRole("button", { name: /^Back to / })`.
4. **Minor, in the same pass:**
   - fix the friction counts (plants and App.search cases, from the file);
   - add jsdom cases for the cross-link leaving the page, Escape doing nothing on the page, and `handoff.view ===
     "questions"` opening it;
   - give `top-bar-harness.tsx:136` `opensPage` for questions;
   - remove the whitespace line in App.tsx's QuestionsPanel props;
   - add "Held by `tests/test_user_guide_ask_chat.py`" to the guide's 1.72 row;
   - wrap spec 02's long Show-all line and name the Show-all case in §2.0d's *Proved by*.
5. **Carried, to name in ready-to-merge:**
   - the page opened while a document from elsewhere is open shows nothing until the reader closes (the results page
     does the same);
   - Help's panel can take focus from the reader (inherited from the results page);
   - AskPage repeats the results page's frame.
6. Plants at the head: `OSPREY_PORTS_SLOT=3 bash OspreyFlow_Build/process/lanes/case-b/v060-fullpage/plants.sh`, logged
   outside the tree and then copied in as `plants-<head>.txt`. Add plants for items 1 and 2. Then the whole keyboard
   suite, every-harness, vitest, tsc, eslint and ruff, a third lane review, rebase if main moved, and ready-to-merge.
   Beat the heartbeat stages as you go.
