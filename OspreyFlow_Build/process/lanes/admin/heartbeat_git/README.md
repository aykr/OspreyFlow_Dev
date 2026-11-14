# The heartbeat: done from git, ready from the route (the owner's order, 14 November 2026)

Twice on 14 November the route view fell behind: steps showed building after they were on main, and later steps
kept their typed dates after the steps before them finished. Both came from hand-typed rows.

**What changed** (`OspreyFlow_Build/scripts/lanes_heartbeat.sh`: `read_git`, and the route view's ready rule):

1. **Every view reads one table, with git's done**: the route (its FINISHED and OUTSIDE lines too), `--lanes` and
   `show`, `--overview`, `--full`, `summary`, and each pass of `watch`. A progress.tsv row reads done, whatever its
   status says, when either holds:
   - Its new, optional sixth column names a branch whose head is the second parent of a merge on main's
     first-parent line, and that merge's subject names the branch. The subject may be the merger's
     `merge: <lane> <name>` (hyphens aside), or the branch written whole as a word of its own:
     `merge(lane/case-x): …`, or git's `Merge branch 'lane/case-x'`. A bare `lane/<lane>` never counts.
   - merger/LANDED.md has `<commit> <commit> <lane> <step> done …`, tab-separated where the step has a space.
   perl runs git itself, reads its output as UTF-8, and passes nothing large through the environment. Any fault
   reads the typed table.
2. A route step that hasn't started, and whose `after` steps are all done, shows "ready", with the days it could
   gain against its typed start. The ids split on commas or spaces, and the headline counts these steps.

**Why so narrow** (the orchestrator approved the variant, 14 Nov; the two lane reviews):

- **Parts merge ahead from a step's own branch.** 258b510 merged step 5's drafts, aca0591 step 4's plan, and
  8a5bde1 step 6's run sheet. LANDED.md records those parts under the step's name. So:
  - a branch is never guessed;
  - a row names a branch only once no further part of the step will merge from it, and until then the merger's
    LANDED `done` is the way;
  - a LANDED line counts only when it says `done`.
- **A branch cut afresh at a lane's last merged head looks merged to git.** Only the merge's subject says which
  branch was merged, so the subject must name this branch, as a whole word. That is also why a bare
  `lane/<lane>`, which each of the lane's steps merges from, is never read.

**Records**

- `red_before_code.log`: the step's tests against main's script, unfiltered. Eleven of the 16 new tests fail
  there. The other five guard against a false done and pass on main by design; their plants show them red.
- `plants.py` and `plants.log`: 21 plants, each red at its own assertion, with the line printed.
- `tests.log`: the three heartbeat test files at the head.
- `real-tables-render.log`: two renders of today's real tables, in full.
  - As they are.
  - With the six rows that name a branch typed back to building: git alone shows 3f, 3f′, 3g, 3h, U and B done.

  Route, `--overview`, `--lanes` and `summary` each say 113 done. Steps 4 and 5 are typed building on today's
  main, so they read "running", not ready.
- `merger_brief.diff`: the merger's step 6 writes `done` and the exact step id. It is the orchestrator's file. The
  progress.tsv header with its six values and the LANDED.md header are ratified at merge, by the orchestrator's
  word.
- The order's points 3 to 5 are carried post-cut in `process/lanes/CARRIES.md`.
