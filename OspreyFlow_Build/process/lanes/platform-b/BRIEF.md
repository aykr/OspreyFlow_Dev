# Platform-b lane · brief ci-diag · the six red GitHub CI jobs, diagnosed from their logs (S)

Written by the orchestrator, 12 November 2026 evening, at the owner's request, for a **fresh platform-b session on
`sol`**, from **main** (branch `lane/platform-b-ci` from `main`). Opus, medium.

**Tonight: diagnose only, from the logs, with no server time.** The demo rebuild and the owner's walk-through have
the server tonight; nothing of yours runs there. Nothing is pushed (each fix's proof needs a GitHub run, which is an
owner's push, later).

GitHub CI run **43198701543** on feb4a79 (the first since 8 November) failed six jobs. Fetch the logs yourself:
`gh run view 43198701543 --log-failed`, and `gh run view 43198701543 --json jobs`. The jobs and their first lines:
- **test**: 7 failures in tests/test_port_guard.py ("DID NOT RAISE ConnectionRefusedError");
- **conformance**: 2 errors, a second Conduit "never came up" (test_statelessness.py, test_statelessness_clickhouse.py);
- **conformance-model**: test_phase6_exit_criterion_end_to_end, "there is no case's analyst layer to write into";
- **glass-perf-a11y-keyboard**: "ALERTS_ACTIONS: keyboard action(s) registered with no proving test case";
- **harness-keyboard-a11y**: "SETUP_SCREENS_ACTIONS: … with no proving test case";
- **harness-image-exit-test**: the pull-mode render needs OSPREY_LITELLM_MASTER_SECRET.
Also read CARRIES.md's rows on these (the CI hygiene row, and phase 8's exit on stack c).

**For each job, tell the orchestrator by message tonight:**
- what it is;
- whether the cause is **the code** (a real defect: which file and line, and since which commit) or **the CI
  environment** (what the runner lacks or does differently from the test server, and where ci.yml sets it up);
- the smallest fix, and how its proof would be shown (red then green, on GitHub once the owner pushes).

Compare with the test server's own runs wherever the same test passes there (the lanes' gates under
process/lanes/*/gates/), and say why it differs. Use main as it now stands: some of these may already have moved.

Then wait. Fixes come after the owner's word, and before v0.5.1. `.github/` is the owner's: a fix there is a diff
for the owner, never applied by you.

**Never.** osprey-small is never touched, and no lane stack is used tonight. No push.
