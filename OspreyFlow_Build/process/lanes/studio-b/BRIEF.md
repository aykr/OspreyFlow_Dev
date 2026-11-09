# Studio-b lane · brief L1.8 · the Studio's tips, who-can refusals and Domain model wording

Written by the orchestrator, 9 November 2026, after L1.6's merge (`9b266d8`), for a **fresh studio-b session on
the default account** (`ayan`; the owner, 9 November: every lane moves to it at its next changeover). Read
`process/lanes/studio-b/REPORT.md` (L1.6), ADR-145 Amendment 4 (decision 12) and ADR-140 Amendment 9 first.
Rebase onto `main`. Opus, medium. Size S. Studio (the parent) is on L1.5 beside you, then L1.7.

**The lane, the stacks, the merge rule.** Your files are the map's row for this lane in
`process/BUILD_PLAN_PARALLEL_LANES.md`; anything else is a request to the orchestrator, and never your parent's
files. A test stack by `stack_lease.sh acquire studio-b "<purpose>" && …` only, and at most two leased live runs on
the machine at once while its swap is high (check `stack_lease.sh status`). Prompt L's rules: never stop on a
question; schemas ride with the step; every live test removes what it writes; your own lane-reviewer, then
make -k ci and make test at a commit rebased onto main, saved under gates/, with a leased live run including
`test_route_rights.py`.

**Binds.** `process/CLAUDE.md` rules 1–15 (4, 7, 12, 13 and 15 above all); ADR-145 Amendment 4 decision 12; the
words rules in spec/02.

**Build** (the plan's row L1.8):
1. **Tips and who-can refusals** in the Studio, from `help/roles.ts` (rules-b's; read it, change it only by a
   patch): every disabled Studio action says why and who can, in words, never a role id.
2. **"Domain model" wording everywhere** on screen; no "target model".
3. **`tools/ui_words_check.py`**: a gate that fails on "target model" in user-facing copy, shown red by a plant
   at the real shape of a Glass string (rule 15) before it is wired into `make ci` (as a diff).
4. **Carries** (`process/lanes/CARRIES.md`, studio-b rows): the subscribed list ids into `studio_staging` and
   `reference_list_import` with L1.4's stand-in import retired; getaddrinfo off the event loop; the SQL byte
   cap checked before a row is held, counted in bytes. Each with a test red first.

**Exit.** The row's exit; make ci and make test green offline; a friction fragment. Report in Prompt L's format,
then stop.
