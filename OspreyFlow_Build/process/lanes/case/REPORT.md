# Case lane · L3.2b (no branches in the Glass, and the check in make ci) · report, 8 November 2026

**Met, each with its test, each shown red (`L3.2b_RED_RECORD.md`):**
- **1 Glass without branches:**
  - *Save as a view* on the selection bar, a node's menu and the over-cap dialog (`save_as_view`; `keyboard.spec.ts`, `view-over-cap.spec.ts`).
  - *Views in this case*, with share and delete for the creator alone, a GOV.UK list, and the Cases list showing every case's views (`ViewsPanel.test.tsx`, `CaseList.test.tsx`, `keyboard/views.spec.ts`).
  - *Ask the model about these* in a private view with `view_id` (`selection.spec.ts`, `questions.spec.ts`).
  - An opened view is a read-only lens (the owner's ruling).
  - `branchNodes.ts` and `branchByFilter.ts` are gone.
- **2** A view opens collapsed at its own threshold (`test_a_view_opens_collapsed_at_its_threshold`). A hidden match collapses nothing (`test_a_match_the_reader_may_not_see_…`).
- **3 G:** no case branch in spec 00–09. B14 has no origin link (Q1).
- **4 H:** target-size on variant c, reproduced red and fixed.
- **5** `no_branches_check` with no xfail, and red on one planted word. Its wiring is `ci-wiring-L3.2b.patch`.
- **6** ADR-144 Amendment 2.
- **Axe** in dark, light and GOV.UK: 446 passed.

**Exit:**
- No branch word where the gate scans (1312 files).
- Gates at `e8f4a9e` (tree `3df33e79aaa98ba1f7f04553e78b85fff8d5425f`), on main `91335b9`:
  - `make -k ci`: only the seven trivy scans failed (Docker Hub 429).
  - `make test`: 8457 passed; only this machine's four failed.
  - test-js: only the timing budget failed, and it passes alone.
- Live: lease case, stack a, 48 passed (`gates/`).
- Friction fragment: `friction/2026-11-08-case-views-in-the-glass.md`.

**Lane review:** two rounds.
- Round 1 found 17 items, two of them blockers (the over-cap dialog over the opened view; the lens unguarded and untested).
- Round 2 found the dialog hidden off the Graph, focus lost, and spec drift.
- All are fixed, except that four invariants have no test at their call site yet: the address losing `case_view`, the window coming back, the form closing on a new selection, and the race guard. They are carried to the next step.

**Decisions taken:** an opened view is a read-only lens. That was put to the owner, who chose it (Am 2 decision 4).

**Commits:** `git log main..lane/case`, from 07372b7.

**For the orchestrator:**
- Apply `registry-L3.2b.patch` and `ci-wiring-L3.2b.patch` at the merge.
- Mark Am 2 written in `ADR_RESERVATIONS.md`.
- Ratify, branch words only:
  - rules: `home/tips.tsx:12-13`, `statusbar/tips.ts:9`, `shell/icons.tsx:6`, `alerts/AlertsPlace.tsx:33`, `case-screen-options-harness.tsx` (H).
  - platform: `map/geometries.ts:24` and its test.
  - studio: `ingest/studio/datasets.ts:39,46-48` (the ranking lost its branch key) and its test.
  - docs: `welcome/WorkspaceWelcome.test.tsx:18,47,69`.
  - In no lane's map: App, questions, workingset, search, strength, watches, auth, crossfilter, linktypes, timeline, primitives.css, `a11y/every-harness.spec.ts`, `live/pid-capture.spec.ts` (CAP-A2-C7, not run: it targets your deployment).
- Docs lane: the guides, site and deck still name branches.
- Port 5185 is shared across worktrees.

**Running:** nothing. The stack is down and the lease released.
