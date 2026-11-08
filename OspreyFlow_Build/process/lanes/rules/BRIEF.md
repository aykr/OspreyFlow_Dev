# Rules lane · brief L2.8c · the other supersedes through the repoint journal

Written by the orchestrator, 8 November 2026, for the **rules lane's first session**, on account `sol`
(ADR-142 Amendment 3: glass split into admin and rules). Rules continues glass's alerts strand: read
`process/lanes/glass/REPORT.md` (L2.8b, merged at `2671fe3`) and ADR-109 Amendment 10 first. Opus, medium.
Size S. After it come L2.9 to L2.12, each briefed when this one merges.

**The lane.** `lane/rules` owns `apps/workspace/src/{shell,layout,home,statusbar,theme,brand}/**` (the
places and the GOV.UK header), `apps/workspace/src/alerts/**` and the Rules and Monitoring place, and the
alerts, rules, watches and monitoring modules and routes in `services/api`
(`process/BUILD_PLAN_PARALLEL_LANES.md`'s map). The graph adapter, `same_as_writer` and the Studio's
`pipeline_run` belong to other lanes: each change there is listed in your report for ratification, with
why the step needs it. Live runs take a test stack (`stack_lease.sh acquire rules "<purpose>"`, a or b)
and pin the ports it prints.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 12 and 15 above all); ADR-109 and its Amendments 9 and
10; ADR-146 decision 10; the L2.8b review's carry list (`process/lanes/glass/REPORT.md` item 4, ruled).

**Build** (the plan's row L2.8c):
1. **D8–D10 from L2.8b's review:** the journal's id-path timing recorded; the rename taken under the
   id-ordered lock; the lock pool given a timeout and its own advisory-key space.
2. **The other supersedes go through the repoint journal:** every caller that clones or replaces a link
   an alert can cite: `supersede_node`'s clones in `confirm_node` and `retract_node`, `supersede.py`,
   `pipeline_run`, `same_as_writer`'s `NOT_SAME_AS`, and publishing's removals.
3. **`settle_repoints`' tolerance that only the fakes needed** (glass's report names it): make the fake
   refuse what the real store refuses (rule 15's second worked example), then drop the tolerance.

**Tests first, each shown red by a plant at the real call site:** for each caller in 2, an alert citing
the link that caller replaces stays listed for its readers, red with that caller's journal entry
removed; the lock's timeout refuses in words, red with no timeout; the conformance guard's confinement
check (`make confinement-check`) still green, or a new allowed caller named in it with its reason.

**Exit.** The row's exit; `make ci` and `make test` green offline (closed ports); the live cases under a
named lease and stack; a friction fragment. Report in Prompt L's format, then stop.
