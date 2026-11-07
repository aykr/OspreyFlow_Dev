# Morning, 7 November 2026

Written by the orchestrator at 00:05 and updated at 07:05. Nothing has been pushed. Local `main` holds two merges: studio's L1.1 (`32c0f36`) and glass's L2.1 (`6e178b2`). Their friction rows are assembled.

## Since 08:00 (you were away from about 08:20)

You allowed L1.2, L2.2 and the docs lane's first brief, and merging as overnight. The briefs are at `e1423d4` and `cf1dc54`, and the Studio's build plan is committed at `a56f2f9` so lanes can read it. The studio and glass branches were fast-forwarded to `main`, and docs was set up and opened.

| Lane · step | State at 08:40 | What it needs |
| --- | --- | --- |
| studio · L1.2 | you answered Q1–Q3 (a, a, a) at about 09:20; building; ADR-140 Amendment 8 reserved (`6b3895b`) | its report when it is ready |
| glass · L2.2 | you chose 'Rights decide' and narrowing the crossing rights; building. The narrowing changes ADR-112's bundles, so it needs a reserved amendment (I check at review) | its report when it is ready |
| docs · website | **merged locally** as `fb03eae` after review fixes and a rebase; session closed. Your rulings: a section turns 'Built' as soon as its feature merges, in text only; i2 is named once the import's ADR is accepted | none. The publish script still does not copy the two new pages (README.md says so) |
| case · L3.1 | says every review item is built; wider live run under the lease | my second review, then yours. Not merged |

Nothing merged since glass, and nothing pushed. A lane that asks you a question only in its window, rather than in `REPORT.md` as Prompt L says, cannot be answered from here (O3).

## Lanes

| Lane · step | State | Commits on `lane/<x>` | What proves it | Left |
| --- | --- | --- | --- | --- |
| studio · L1.1 | **merged locally** as `32c0f36`; session closed by you | `dbc3956` `4f958f5` `e9b8b31` (after the rebase) | ruff and mypy clean; reviewed; `make ci` on the merge is red on 3 gates, down from 5 (below) | your diff; r1/r14 PID tests red since `2f24d85`; the two trivy findings |
| glass · L2.1 | **merged locally** as `6e178b2`, after two reviews | `7df24ec` to `6f1fa89` (rebased) | the map, `spec/glass_redesign/ALERTS_GAP_MAP.md`; citation-check green; second-review fixes spot-checked | ADR-146 (the alerts journey) after your answers to its §6; widening `APACHE_DOC_PATHS` (O2) |
| case · L3.1 | Q1–Q4 built and recorded (07:35); **review 07:45: not merge-ready**, two cross-case leaks from Q1 (an extraction record readable by case B; the resolution trigger reads layer `NOT_SAME_AS`) and seven untested invariants; your rulings on findings 5, 7 and 8 sent in a nudge | `7a6097f` `ef0a7fa` `8d7c4e2` and five earlier (rebased) | conformance and read-set tests; ADR-143 Amendment 1, ADR-099 Amendment 14 and ADR-136 Amendment 1 written | the two leaks; findings 3–6, 9, 11–13; then your review. Not merged. |
| docs | not opened (P7: after the first merge) | none | none | none |

**Since 05:30:** you closed glass and I reopened it on Prompt R. Its first open swallowed the nudge (an `open`/`resume` defect, fixed red first at `f93e1df`), so I sent it again, and glass is now making the three review fixes before it rebases. Studio rebased once you woke it, and was merged.

**Waiting:** I cannot see the windows. No lane reported a permission prompt, and none shows the signs of one: every lane is idle at its prompt, not mid-tool. Case was silent for 31 minutes while its live suite ran; that was a real run, not a stall.

## make ci

**On the merges `32c0f36` and `6e178b2`** (full run, 05:38–05:42): red on `trivy-image-harness`, `trivy-image-superset` and `test-file-coverage-check` only. ruff and mypy are green. That is three of the baseline's five, and nothing new.

The full run is at `54fbd3d`, with downloads. It has five failures, which are the baseline:
1. Core `lint` (ruff I001)
2. Core `typecheck` (mypy, 5 errors)
3. `test-file-coverage-check` (unwired live tests: 6, per studio)
4. `trivy-image-harness`: CVE-2026-78661 in the compose plugin's `golang.org/x/net`
5. `trivy-image-superset`: CVE-2026-109518 in Debian 12's `apt`

Studio fixes 1 and 2 on its branch. 3 needs your diff. 4 and 5 need a decision (below). The live `conformance` job will also stay red on r1/r14.

## Questions for you (recommendation first)

**Case, L3.1: answered 06:55, all (a).** ADR-143 Amendment 1, ADR-099 Amendment 14 and ADR-136 Amendment 1 are reserved (`81bd510`), and L3.1b is in the plan. Type `read your nudge` in case's window to start it. For reference:
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

- **My judgement, 11:05, under your delegation:** dev-up's ports stay as they are. Moving ArcadeDB off 2480 would have pointed the demo guide's reset (`drop database`), the hand-run Conduit and `seed_paysim` at your deployment, because they default to `localhost:2480`. The leased stack is now the throwaway test stack the lanes already used, and the lease checks it.

- **main's fast test tier** (`ci.yml`'s `test` job, not `make ci`) has three real failures from phase 4's withdrawal: `test_revert_elements_by_type` and `test_write_onto_a_reverted_node` (SQL expectations), and `test_unfiltered_node_lookup_confined` (`snapshot_withdrawal.py` calls `live_edges_touching`). Your ruling: studio fixes them as L1.2a, after L1.2. Two more fail on this machine only: `test_deployment_schema` (your local `osprey.yaml`) and `test_layout` (`graphify-out` at the root).

- **Owner rulings, 10:45.** Trivy: rebuild, then a dated ignore where no fix exists yet. The perf budget (`MatrixView.budget`, failing on main) is to be measured under the lease on a quiet machine. Widen the link and provenance gates to all of `spec/` except the decision log. Ratify out-of-map changes where needed (now in the build plan). Owner questions now reach the owner through the orchestrator, by cross-session message.

- A change to `lanes_heartbeat.sh` reaches a running `watch` only after it is restarted (Ctrl-C, then run it again). The merged-lane false alarm was fixed at `cc2e443`, and the monitor was restarted at 07:20.

- A beat the orchestrator sends on a lane's behalf records the orchestrator's head, not the lane's (glass, 05:53). Send it from the lane's worktree. Minor; not fixed tonight.

- `origin` is public and stands, as you ruled. Pushing waits for a green `make ci`.
- Case's throwaway ArcadeDB was bound to `0.0.0.0:2491`, not loopback. It is stopped now.
