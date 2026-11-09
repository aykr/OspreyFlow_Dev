# Case lane · brief L3.9 · merging a drawn dataset

Written by the orchestrator, 9 November 2026, after L3.4's merge (`32c6f49`), for a **fresh case session on the
default account** (`ayan`). Read `process/lanes/case/REPORT.md` (L3.4), and in `spec/06_DECISIONS.md` ADR-143
Amendment 2 decisions 6 and 7 and **Amendment 3** (L5 and L6 answered (a): where a fresh drawing's items live, and
who merges a drawn dataset), and Amendment 5 (L3.4 as built), first. Rebase onto `main`. Opus, medium. Size L.
After it comes L3.6 (the `drawn_watch` kind's queue cases, once rules' L2.10 is on main).

**The lane, the stacks, the merge rule.** Case's map; the Studio's *Merge into a dataset…* screen lives in
`apps/workspace/src/ingest/**` **by agreement with Lane 1** (studio is finishing L1.5, then L1.7: tell the
orchestrator which files before you edit them, so studio rebases past them). Test stacks are on the owner's server
only (b to g); Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator for a stack, then
use main's `stack_lease.sh` (acquire, up, `remote case -- …`, down, release; `remote-log case` reattaches). `make
test` runs on the server: `stack_lease.sh offline case -- sh -c 'make -k test SKIP_JS=1; cd ../OspreyFlow_Core &&
make test-js'`. Ask before `make -k ci` or any Playwright here (two heavy runs at most on this Mac). Never call
remote or offline while one of your runs is alive. Prompt L's rules: never stop on a question, except that
loosening access, real data or contradicting an accepted ADR stops the piece. Your own lane-reviewer, then the
gates at a commit rebased onto main, saved under `gates/`, with one leased live run including
`test_route_rights.py` and every live file the change reaches. **Re-gate after any code change.** Report to the
orchestrator **by message**. The riskiest work in the plan: access and existence-leak tests first; the
orchestrator's independent review before merge.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 5, 6, 12 and 15 above all; rule 6: nothing is merged in storage,
resolution writes scored `SAME_AS` edges); ADR-143 Amendments 2, 3 and 5; ADR-140 (one load); ADR-145 Amendment 4
decision 11 (who reviews).

**Build** (the plan's row L3.9): the Studio's *Merge into a dataset…* with map, match, dry run and merge; a drawn
dataset's items merged into a target dataset as one load under the target's policy and highest marking; matches
proposed as scored inferred `SAME_AS`, never collapsed in storage, a person confirming (rules 5, 6); the drawing
becomes a case view with its annotations; the merge reverted as a load is (L3.4's revert). Carried (CARRIES): the
stale `test_valkey_store.py` branch case (rewrite for views, or remove, red first).

**Tests first, each red by a plant at the real call site:** decisions 6 and 7's tests as ADR-143 names them; a merge
into a dataset the merger may not write refused, and one above the target's highest marking refused, nothing
written; no match proposed across a dataset the merger may not read, and a match's existence not revealed by a
count, an order or a timing (rule 7); the dry run counts only what the merger may see; keyboard cases for every
new action (rule 13), registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** The row's exit (decisions 6 and 7's tests); `make ci` and `make test` green; live cases under a named lease
and stack; a friction fragment (one row). Report in Prompt L's format, then stop.
