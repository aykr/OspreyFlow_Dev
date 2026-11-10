# Platform-b · the preflight ports fix (after P5b, before P6): report

P5b merged at f8df603; its report is in main's history.

1. **Exit, met.** A deployment kept by name is no longer refused where another deployment holds 2480. The ports check resolves the published `${OSPREY_ARCADEDB_PORT:-2480}` from the deployment's own `deployment.env`, under the shell's environment, as Compose does (`harness/preflight/ports.py`, ratified). Proved by `tests/harness/test_named_render.py::test_the_preflight_checks_the_deployments_own_graph_port`, run through `harness.apply.preflight` on the install's context: its own port is checked, a held one is refused, and the shell still wins. `::test_the_ports_check_reads_an_env_file_as_compose_does` covers `export`, inline comments and quotes. Each branch was shown red by a plant (`plants.md`).
2. **Spec.** Spec 05 §2.1 now says which environment the check resolves against (rule 11).
3. **Live driver.** Its port workaround is taken out, because the shell's value would have hidden the fix. The driver still refuses to run until the owed proof's carry closes.
4. **Review.** The lane-reviewer found:
   - the workaround masking the fix;
   - the red not on record;
   - the test copying the call site rather than going through it;
   - the env reader differing from Compose's.

   All four are fixed.
5. **Left, and why (for CARRIES' platform-b row).**
   - `declared_ports` still defaults to `os.environ` for its two test-side callers, `test_harness_image.py` and `test_apply_changed_settings.py`, both on checkout renders whose `deployment.env` says 2480. `test_harness_image.py:129`'s docstring now over-claims "the same function the check calls".
   - The tree has five hand-written `deployment.env` readers. One beside `SECRETS_FILE` could serve them all, which is a refactor for its owners.
   - The reapply path (with `own_ports`) uses the same `check`, but has no named-deployment case of its own.
6. **Gates.** `make test` (offline, on the server) and `make -k ci` (here) at the ready-to-merge head, `gates/<sha>.*`. The counts go in the message.
7. **Friction:** `process/friction/2026-11-10-platform-b-preflight-ports.md`. **Route:** none added. **Questions:** none. **Next:** P6 (`P6_PLAN.md` on `prep/platform-b-p6`), folded into the BRIEF when it starts.
