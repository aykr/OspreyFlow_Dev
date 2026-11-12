# Platform-b lane · brief T2 · tooling carries: per-lane ports, docker-shelling tests, constant registries

Written by the orchestrator, 10 November 2026 evening, for the platform-b session, **from main**. Size S. Tooling
only: no product code. The Playwright configs, `keyboard/registryCoverage.test.ts` and the docker-shelling harness
tests are ratified for this step.

**The lane, the stacks, the merge rule.** Test stacks on the server only, Docker never started on this Mac. **Tonight the demo track (rules L2.11, studio L1.7, docs D2b) has first call on both local heavy slots and the stacks**: work offline first, and ask the orchestrator for a slot or stack, expecting to wait. `make test` through `stack_lease.sh offline <lane>`; a live check through `stack_lease.sh live <lane> -- --continue-on-collection-errors`. Never stop on a question: the strict option for access, logged. Take the `make -k ci` slot at every gate; lint from the branch's own diff. Your own lane-reviewer, then the gates. Report **by message**.

**Build** (CARRIES' orchestrator rows):
1. **Per-lane vite and harness ports** for local Playwright runs (from `lane_stacks.tsv`, as the stores are), so two
   lanes' runs never share 5184/5185 (today's waits and override configs), red first in the configs' test.
2. **Docker-shelling tests skip at once, in words, under `~/.ospreyflow/no-local-stacks`** (`test_workspace_proxy`,
   `test_harness_image` and kin), so no local test starts Docker Desktop again (case did, by accident, today).
3. **registryCoverage sees a registry named through a constant** (twice today a lane passed `REGISTRY` and was read as
   unasserted), or fails in words naming the fix, red first with the constant shape.

**Exit.** Each red first; a friction row.
