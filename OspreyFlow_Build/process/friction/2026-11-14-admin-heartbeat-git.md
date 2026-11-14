# Friction: the heartbeat reads done from git (admin, 14 November 2026)

- **The order assumed a branch the tables don't hold.** It said to read each step's branch "from groups.tsv or
  progress.tsv as they record it". Neither records one, and step names don't match branch names (3h is
  v052-cluster-on-entry on lane/case-merged-clusters). Guessing a branch from names would have shown steps 4, 5
  and 6 done, because a part of each had already merged from the step's own branch. The variant was settled with
  the orchestrator before any code. **Next time:** check a stated data source exists before building on it.
- **The first "came in by a merge" test was too weak.** "An ancestor of main, not on its first-parent line" also
  matches a branch cut afresh at a lane's last merged head. Git can't tell two branches on one commit apart; only
  the merge's subject can. The lane review found it (finding 1).
- **The first version fixed one view of four.** `--lanes`, `--overview` and `summary` still read the typed
  column, so the views disagreed by two steps on the real tables. All views now read one table (`read_git`).
- **The tests landed with the code**, so the red-before-code record was taken afterwards: the new tests run
  against main's script (`red_before_code.log`).
