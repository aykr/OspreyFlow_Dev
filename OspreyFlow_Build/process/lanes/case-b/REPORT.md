# case-b · L3.7 (the grading scheme setting and its change command) · report, 9 November 2026

L3.5 was merged at a1e4091. Its report is in that commit. This branch, `lane/case-b` (fast-forwarded to `lane/case-b-l37`'s head, as the orchestrator asked), holds L3.7 alone.

**Exit, met.**
- **The setting.** `install.yaml`'s `grading.scheme` reaches `osprey.yaml`, is rendered as `OSPREY_GRADING_SCHEME`, is read first by the Conduit's start (an unknown scheme stops it) and is answered at `GET /v1/grading-scheme` (`test_grading_setting.py`, `test_grading_answers.py`).
- **The boards.** An opened board offers the deployment's scheme. A node, link or edit graded in another scheme is refused (422) before any write (`test_grading_boards.py`).
- **The dry run writes nothing** (`test_the_dry_run_writes_nothing_and_counts_each_mapping_line`, and live against ArcadeDB).
- **Grades keep their original** through two changes (`test_every_item_keeps_its_original_grade_and_scheme_through_two_changes`, and the same live). Marking, datasets, properties, resolution and occurrences are kept too (live).
- **Refused whole before any write**, a dry run included, for:
  - an incomplete mapping, or one from another scheme;
  - an item in another scheme, or one that can't be read back;
  - an item whose write would be refused.
- **The plan is said and audited before the first write.**
- **Red record.** Every test was shown red by a plant: 28 offline and 8 live (`L3.7_RED_RECORD.md`, `plants_L3.7.py`).
- **Keyboard and axe: none due.** L3.7 adds no screen or action. The board editor already takes the scheme the Conduit sends (`BoardEditor.tsx:118`). Admin's read-only display is a request (below).

**Gates** at `f0ddc50` (tree `2a3049ce36929f16b952fe970c9f4f4093fbee9d`), on main `451a648`, with `GRADING_CI.diff` applied. Main has moved since only by the orchestrator's `CARRIES.md`.
- `make -k ci`: green whole, the trivy scans included (`gates/f0ddc50.ci.txt`).
- `make test`: 9168 passed. 4 failed and 2 errored, all this machine's: the same list L3.5's gate explained.
- test-js: 2756 passed. 1 failed, the Matrix first-frame timing under load, which passes alone.
- Earlier runs caught three of mine, all fixed: the admin guide's `grading` lines, `GradingSchemeAnswer` missing from spec 01, and the guide's PDF.
- The guide is 1.58. If studio-b's L1.6 (also 1.58) merges first, mine becomes 1.59 at a rebase.

**Live.** Lease case-b on stack c, 32 passed (`gates/live-L3.7-stack-c.txt`): route rights, the registry read, the change against ArcadeDB, the board store, restoring the drawn layer, and the datasets and link-type stores. The stack is down and the lease released. 4 `conformance_*` databases were on stack c when I stopped it (`down` stops the containers without removing them). My fixtures drop their own databases, so whose these are is unknown.

**Lane review.** 18 findings, all fixed or answered here:
- Blocking: the command's adapter held no ontology, so every real write would have been refused, and no test caught it. It is now caught through the command's own `graded_items`.
- The rewrite dropped resolution and re-counted occurrences.
- Checks were met mid-run.
- The CI wiring was missing; it is now `GRADING_CI.diff`.
- The others: the Conduit's start order, the route's default fallback, plant paths, and tests without plants.

**Decisions taken** (the owner may overrule each):
1. **The command is `python -m scripts.grading_change`.**
   - Decision 11 names `ospreyflow grading change`. Options: (a) the script also rewrites `osprey.yaml`; (b) the script, then the operator sets `grading.scheme` and restarts; (c) build the verb now.
   - I chose (b). The script runs inside the deployment, where the host's `osprey.yaml` isn't reachable, and a YAML rewrite would drop the owner's comments. The verb is the CLI's to wrap, as with `revert_load`.
   - A drawing made before the restart is changed by running the same change again (spec 01).
2. **Decision 11's "scheme file" is not built.** The setting takes `5x5x5` or `3x5x2` (recorded in spec 01).
3. **"A dry run first" (C13) is offered, not enforced.** A real run says the plan before writing.
4. **The audit is written twice:** before the first write and after the last (or stopped). This means a changed grade is never left without a record.
5. **The registry's one cross-case read.** The command reads every case's live drawn items, as an operator (carved out in spec 01).
6. **Withdrawn items keep the grade they were drawn with.** The plan says so.
7. **The board routes refuse a grade in another scheme.** Otherwise a drawing made after a change would refuse the next change whole.

**Left.**
- Admin's read-only display of the scheme (Admin lane; `GET /v1/grading-scheme` is ready).
- The `ospreyflow grading change` verb.
- `board_fakes.py` keeps resolution on merge, where the store doesn't (Case's file).
- Untested: the operator reading another unit's restricted item.

**For the orchestrator.**
- Apply `GRADING_CI.diff`, which wires the two live files into `ci.yml`. The gates were run with it applied.
- Ratify these outside the lane's map:
  - `docs/administration-guide.md` and its PDF (the Docs lane's);
  - `app.py`: the route, the four board routes, and the start;
  - `config.py`, `answers.py` and `render.py`;
  - the Build `Makefile`, `tools/admin_guide_options.py`, both administration guides, `test_route_rights.py`, and specs 01, 03 and 10;
  - the schemas commit at the branch's head.

**Commits:** `git log main..lane/case-b`. Nothing of mine is still running.
