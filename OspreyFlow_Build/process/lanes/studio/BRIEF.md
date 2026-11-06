# Studio lane · brief L1.1 · phase 4's remainder: `make ci` green

Written by the orchestrator, 6 November 2026 (step 0). Opus, medium. Size S.

**Why.** At step 0 `make ci` was found red at `b548d9f`, before any step 0 change, for causes from 3 to
6 November. The owner ruled "Spec by me, code by L1.1": the orchestrator fixed the spec-text causes
(`54fbd3d`); this brief fixes the rest. Nothing is pushed to `origin` until this lane's merge passes
`make ci` (ADR-142 decision 6); step 0 rides on that push.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 14 as ADR-142 rewords it); ADR-142 decisions 5–8;
`FDE_HANDOVER.md` §1 ("a defect is fixed at the class, not the instance"; explain before you fix).

**The causes, as found by the orchestrator (download-free gates; the full run's other gates follow by
nudge if they are red too).**
1. `OspreyFlow_Core`: `ruff check .` — one error, `TRUST_EMAIL_FIX` and `TRUST_EMAIL_SAYS` imported and
   unused (introduced around `7e1e552`, 5 November).
2. `OspreyFlow_Core`: `mypy packages services harness` — five errors:
   `packages/demo_fixtures/pid_plan.py:2627` `_offset` redefined (first at line 314), and the two that
   follow from it at 2658 and 2661 (`2f24d85`, 3 November); `harness/apply.py:1048` and `:1059`,
   `FilesHeld` against `dict[str, str]` (`6edda39`, 4 November).
3. `test-file-coverage-check`: `tests/services/api/test_pin_calls_refresh_live.py` (`191d24c`) needs a
   live service and is in neither the `test` job's ignore list nor a live-service job's file list. That
   needs lines in `.github/workflows/ci.yml` and `OspreyFlow_Build/Makefile`, which are the owner's:
   **write the exact diff into your report as a request to the orchestrator; do not edit either file.**

**Files this brief lets you change** (beyond the Studio's ownership map, because the causes sit there):
the file holding the unused imports, `packages/demo_fixtures/pid_plan.py`, `harness/apply.py`, and the
tests that cover them. Nothing else outside the Studio's map.

**Tests first.** For each mypy error, say whether it is a real fault or a typing gap. A real one (for
example, `_offset` redefined so that the earlier definition's callers now call the later one) gets a
failing test first, shown red, that would catch it; a typing gap needs none. Run the touched tests and,
for `pid_plan.py`, the PID seed's own tests (`tests/test_pid_*`, `tests/demo_fixtures`).

**Exit.** `ruff check .` and `mypy packages services harness` clean in `OspreyFlow_Core`;
`make -C OspreyFlow_Build test-file-coverage-check` green once the owner has applied your diff (until
then, your report names the diff as the one open item); every touched test green; a friction fragment
in `process/friction/`. No dev stack needed; if you find you need it, take the lease.

**Report** (Prompt L's format, also in `process/lanes/studio/REPORT.md`): each exit criterion with its
proving command or test; the commits; the `ci.yml` and `Makefile` diff; questions for the owner as
multiple choice; one hand check for the owner; whether anything of yours is still running.
