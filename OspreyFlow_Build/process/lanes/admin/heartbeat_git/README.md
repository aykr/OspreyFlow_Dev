# The heartbeat: done from git, ready from the route (the owner's order, 14 November 2026)

Twice on 14 November the route view fell behind: steps showed building after they were on main, and later steps
kept their typed dates after the steps before them finished. Both came from hand-typed rows.

**What changed** (`scripts/lanes_heartbeat.sh`, `merged_by_git` and the route view):

1. A progress.tsv row's step is done when the branch named in its new, optional sixth column has its head on main
   through a merge (an ancestor of main, not on main's first-parent line). It is also done when merger/LANDED.md has
   `<main parent> <lane head> <lane> <step> done`. Either holds whatever the row's status says.
2. A route step that hasn't started, and whose `after` steps are all done, shows "ready", with the days it could
   gain against its typed start. The headline counts it.

**Why not the branch named by convention, or any LANDED line naming the step** (the orchestrator approved this
variant, 14 Nov). Steps merge in parts from one branch: 258b510 merged step 5's drafts from lane/docs-v052-sweep;
aca0591 step 4's plan from lane/platform-v052-measure; 8a5bde1 step 6's run sheet from lane/platform-b-v052-r1.
Each head is on main while its step is not done. LANDED.md records those parts under the step's own name (line 65
"docs v052-sweep part one", 110 "platform v052-measure"). So a branch is never guessed, the branch named is the one
carrying the step's whole delivery, and a LANDED line counts only when it says `done`.

**Records**

- `plants.py` and `plants.log`: 9 plants, each red at its own assertion.
- `real-tables-render.log`: the route over today's real tables. 3f, 3f′, 3g, 3h, U and B show done; step 5 shows
  ready (and so does step 4, since B, its one `after`, is done).
- Points 3 to 5 of the order are carried post-cut in `process/lanes/CARRIES.md`.
