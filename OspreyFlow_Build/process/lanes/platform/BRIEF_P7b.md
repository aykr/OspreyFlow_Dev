# Platform · brief P7b · the `cloud-platform` profile's proof-of-concept shape

Written by the orchestrator, 11 November 2026, when P7 merged (c73e4f1). Binds: `process/CLAUDE.md` rules 1–15,
`process/lanes/PROMPT_L.md`, ADR-142 Amendments 6–8, ADR-148 and its Amendment 1 (P7 as built).

**What (ADR-142 Amendment 8 decisions 6 and 10; ADR-148 Amendment 5, reserved for this step).** The profile gains
`shape: poc` beside the production shape P7 built, which stays unchanged:
- one ArcadeDB and one ClickHouse with its Keeper, inside the server; no PodDisruptionBudgets; a scratch volume for
  Ingest;
- a manual-install runbook and a decommission runbook, each written to be run end to end by the client's team.

**Exit.**
- The acceptance scenarios (`spec/08_ACCEPTANCE_SCENARIOS.md`) green on kind in the `poc` shape. That run stands as the
  client install's acceptance.
- `cp-policy-check` green on both shapes, and red on each planted fault in the `poc` shape's own render.
- The install and decommission runbooks each run end to end on kind. The decommission leaves nothing behind, checked by
  a test shown red first with a planted leftover.
- Every other profile's render, and the production shape's, unchanged (`p7_renders_unchanged.py`, at the head).

**Order and ownership (Amendment 8 decision 3).**
- `values.yaml`, the profile's settings model, `render.py`'s profile entry and `harness/cloud_platform/**` are yours.
  P9, P10, P11 and P12's part 2s send you diffs, applied at merge in this order: P10 and P9 first, then P11, P12 and L1.9.
- P7b renders what they leave, so its final render, and the kind run, come after P11's and P12's part 2s land.
  Start with the shape, the runbooks and the decommission test now.
- P7's carries in `CARRIES.md` (platform rows) are yours to fold in where they touch the same files.

**Runs.**
- kind on the test server only, through `stack_lease.sh`.
- No Docker on the Mac.
- Gates once at the head: `make test` and `make -k ci` through `stack_lease.sh offline platform`; `harness-a11y` needs
  `OSPREY_PORTS_SLOT` set.

Write the as-built record as ADR-148 Amendment 5. Send "built" and "ready-to-merge" to the orchestrator.
