# Morning, 7 November 2026

Written by the orchestrator at 00:05 and updated at 05:45. Nothing has been pushed. Local `main` holds one merge, studio's L1.1 (`32c0f36`); the friction rows are assembled at `4124466`.

## Lanes

| Lane · step | State | Commits on `lane/<x>` | What proves it | Left |
| --- | --- | --- | --- | --- |
| studio · L1.1 | **merged locally** as `32c0f36`; session closed by you | `dbc3956` `4f958f5` `e9b8b31` (after the rebase) | ruff and mypy clean; reviewed; `make ci` on the merge is red on 3 gates, down from 5 (below) | your diff; r1/r14 PID tests red since `2f24d85`; the two trivy findings |
| glass · L2.1 | ready to merge, **not rebased**; 3 review fixes not yet made | `fec0e07` `b98668a` | the map, `spec/glass_redesign/ALERTS_GAP_MAP.md` | The reviewer's three must-fix items: K10's schedule requirement, the inbox's `reach_clause`, the gate claim. ADR-146 after your answers. |
| case · L3.1 | waiting for you; **not to be merged tonight** (your rule 4) | `774388a` `3f1bc01` `2bb69c9` `b3906c1` `8708ddd` | `test_analyst_layer.py` (conformance: case B unchanged, under the case lease) and the read-set and store tests, each shown red first. 477 of 478 pass; the one failure was already failing at `83ff99e`. | Phase 5's target-model half (Q4 below); out-of-map files to ratify; 5 minor open items. |
| docs | not opened (P7: after the first merge) | none | none | none |

**Since 05:30:** you closed glass and I reopened it on Prompt R. Its first open swallowed the nudge (an `open`/`resume` defect, fixed red first at `f93e1df`), so I sent it again, and glass is now making the three review fixes before it rebases. Studio rebased once you woke it, and was merged.

**Waiting:** I cannot see the windows. No lane reported a permission prompt, and none shows the signs of one: every lane is idle at its prompt, not mid-tool. Case was silent for 31 minutes while its live suite ran; that was a real run, not a stall.

## make ci

**On the merge `32c0f36`** (full run, 05:38–05:42): red on `trivy-image-harness`, `trivy-image-superset` and `test-file-coverage-check` only. ruff and mypy are green. That is three of the baseline's five, and nothing new.

The full run is at `54fbd3d`, with downloads. It has five failures, which are the baseline:
1. Core `lint` (ruff I001)
2. Core `typecheck` (mypy, 5 errors)
3. `test-file-coverage-check` (unwired live tests: 6, per studio)
4. `trivy-image-harness`: CVE-2026-78661 in the compose plugin's `golang.org/x/net`
5. `trivy-image-superset`: CVE-2026-109518 in Debian 12's `apt`

Studio fixes 1 and 2 on its branch. 3 needs your diff. 4 and 5 need a decision (below). The live `conformance` job will also stay red on r1/r14.

## Questions for you (recommendation first)

**Case, L3.1** (the full text is in `lanes/case/REPORT.md`):
- **Q1.** Where do today's analyst writes go?
  - (a) Hand-marking and `manual_link` into the layer; questions and extractions into the source.
  - (b) All four into the layer.
  - (c) All four stay in the source.
- **Q2.** Where does data go when it is added to a case that reads a composite?
  - (a) The composite's own id.
  - (b) The case's layer.
  - (c) Refused.
- **Q3.** What egress does a layer have?
  - (a) The strictest of its sources'.
  - (b) Always `none`.
  - (c) Set per layer.
- **Q4.** How is phase 5 split?
  - (a) The target model, reference lists and ADR-126 move to a new L3.1b.
  - (b) All of it stays in L3.1.
  - (c) That half goes to Lane 1.

**Glass, L2.1** (the full text is in §6 of the map):
- **Q1.** One alert list or two?
  - (a) One queue.
  - (b) Both, with the inbox renamed.
  - (c) As today.
- **Q2.** Where do the new alert kinds live?
  - (a) The drawn-item match in the case queue; promotions overdue in *Needs you* and Operations.
  - (b) Both in the case queue.
  - (c) A *board* queue kind.
- **Q3.** What does "my team" mean?
  - (a) A label plus filters.
  - (b) The unit only.
  - (c) Remove it.
- **Q4.** How does an alert lead to the case and back?
  - (a) A private view with "← Back to the alert".
  - (b) Home's rows only.
  - (c) As today.

**Orchestrator:**
- **O1.** The trivy findings.
  - (a) Rebuild without cache; where no fixed package exists yet, add a dated `.trivyignore` entry.
  - (b) Hold `make ci` red until upstream ships a fix.
- **O2.** `product-tree-link-check` and the provenance check scan a fixed file list, so `spec/glass_redesign/` and `spec/ingest_studio_redesign/` are never checked.
  - (a) Widen both to every `spec/**/*.md` except `06_DECISIONS.md`.
  - (b) Leave them as they are.
- **O3.** A nudge reaches only a lane that is mid-turn.
  - (a) Record this in an ADR-142 amendment; you wake an idle lane by typing in its window.
  - (b) The orchestrator may `resume` an idle lane that is ready to merge.
- **O4.** Case edited files outside its ownership map: `services/api/{datasets,questions,model_routing}.py`, `scripts/{case_seed,stamp_datasets}.py`, `a11y/every-harness.spec.ts`.
  - (a) Ratify them for L3.1.
  - (b) Move them to a shared commit.

Also asked by the lanes:
- Reserve ADR-146 for "the alerts journey" (glass), and an ADR-136 amendment once case Q3 is ruled.
- `make dev-up` collides with your deployment on 2480 (case).
- `BUILD_PLAN_INGEST_STUDIO.md` is uncommitted (case).

## Diff for `ci.yml` and the Makefile (yours to apply)

1. A `lanes-check` target, added to `ci:` (as sent in chat at 22:45). It runs the five step-0 tests and `python -m tools.adr_reservations_check`.
2. Studio's diff, on `lane/studio`: `OspreyFlow_Build/process/lanes/studio/L1.1_ci_makefile.diff`. It adds six live test files to `ci.yml`'s `conformance` job and to the `test` ignores in both files. The reviewer checked it hunk by hunk.
3. On case's branch: `test_analyst_layer_store.py` and `test_migrate_cases_to_one_dataset_store.py` need the same wiring. The lane has not written a diff yet.

## Notes

- `origin` is public and stands, as you ruled. Pushing waits for a green `make ci`.
- Case's throwaway ArcadeDB was bound to `0.0.0.0:2491`, not loopback. It is stopped now.
