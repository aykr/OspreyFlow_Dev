# The heartbeat: done from git, ready from the route (the owner's order, 14 November 2026)

Twice on 14 November the route view fell behind: steps showed building after they were on main, and later steps
kept their typed dates after the steps before them finished. Both came from hand-typed rows.

**What changed** (`scripts/lanes_heartbeat.sh`: `read_git`, and the route view's ready rule):

1. **Every view reads one table, with git's done**: the route (with its FINISHED and OUTSIDE lines), `--lanes`,
   `--overview` and `summary`. A progress.tsv row reads done, whatever its status says, in either case:
   - Its new, optional sixth column names a branch whose head is the second parent of a merge on main's
     first-parent line, and that merge's subject names the branch. The subject can be `merge: <lane> <name>` or
     `merge(lane/<lane>): <name>, …` (hyphens aside), or the branch written whole.
   - merger/LANDED.md has `<main parent> <lane head> <lane> <step> done`, tab-separated where the step has a
     space.
2. A route step that hasn't started, and whose `after` steps are all done (the ids split on commas or spaces),
   shows "ready", with the days it could gain against its typed start. The headline counts it.

**Why so narrow** (the orchestrator approved the variant, 14 Nov; the lane review's findings 1, 2 and 5):

- **Parts merge ahead from a step's own branch.** 258b510 merged step 5's drafts, aca0591 step 4's plan, and
  8a5bde1 step 6's run sheet, each from the step's branch, while the step itself was not done. LANDED.md
  records those parts under the step's name (line 65 "docs v052-sweep part one", line 110 "platform
  v052-measure"). So:
  - a branch is never guessed from a step's name;
  - the branch a row names is the one whose merge finishes the step (the header says so);
  - a LANDED line counts only when it says `done`.
- **A branch cut afresh at a lane's last merged head looks merged to git.** Its head is the old merge's second
  parent, and git can't tell two branches on one commit apart. Only the merge's subject names which branch was
  merged.

**Records**

- `red_before_code.log`: the step's tests against main's script. Seven new cases are red. The other four guard
  against a false done, so they pass on main by design; their plants show them red.
- `plants.py` and `plants.log`: 15 plants, each red at its own assertion (the line is printed).
- `real-tables-render.log`, two renders of today's real tables:
  - as they are;
  - with the six rows that name a branch typed back to building, so that git alone shows 3f, 3f′, 3g, 3h, U
    and B done.

  Each view, route, overview and summary, says 113 done. On today's main, steps 4 and 5 are typed building, so
  they read "running", not ready.
- `merger_brief.diff`: the merger's step 6, writing `done` and the exact step id. It is the orchestrator's file.
- The order's points 3 to 5 are carried post-cut in `process/lanes/CARRIES.md`.
