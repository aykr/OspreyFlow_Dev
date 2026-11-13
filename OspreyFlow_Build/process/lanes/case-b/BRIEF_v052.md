# Case-b lane · brief v052 · step 6's install-test driver, then the owner's Parts C and E once approved

Written by the orchestrator, 13 November 2026 evening, for a **case-b session on `sol`**. The route to v0.5.2 is
`process/lanes/ROUTE_052.md` and the owner's navigation decision is `process/lanes/NAVIGATION_2026-11-13.md`. Read
both. Opus, medium. Offline. Nothing merges before v0.5.1's candidate is cut.

## Now: step 6's driver (`v052-r1-driver`), built ahead

Step 6 is the one install test on v0.5.2's candidate: install v0.5.1, upgrade to the candidate, verify everything
in the manifest, run spec 08's acceptance scenarios, then decommission. Build the driver now, so the day is just the
run.

- **A verifier** that reads the poc manifest (on `lane/platform-v052-manifest` until it merges, so branch from it) and
  checks a live kind deployment against it:
  - every workload is ready;
  - every image is pushed;
  - every database is reached by its reader;
  - every bucket is written;
  - every egress host is allowed, and an unlisted host is refused;
  - every Entra registration is used.

  **A listed component with no check stops the run** ("listed but not exercised").
- **A runner for spec 08** (`OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md`), adapted to the Entra stand-in's
  bearer tokens. Each scenario that cannot run on this shape is marked with its reason.
- **Reuse R1's driver** (`process/lanes/platform/gates/r1_kind.py`). Platform owns it; coordinate with platform, and
  with platform-b, which leads step 6.
- **Red first:** the verifier fails a deployment missing any one listed item.

## Then, once the owner approves their estimates: Parts C and E

Part C (one set of actions for the selection) and Part E (the typeface in the GOV.UK look), as in
NAVIGATION_2026-11-13.md. Both looks, keyboard and every-harness updated, tests first. Coordinate with the case lane,
which is changing the shell for Part B.

**Never.** Nothing on the server except through `stack_lease`. Never osprey-small. No push. Synthetic data only.
