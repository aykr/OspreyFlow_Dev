# admin · T1 part 1 red record (10 November 2026)

Each check was planted out at its real call site, its test run red, and the file put back and green. These plants were
run by hand, one at a time. Offline: closed ports, no lane.

| Plant | File | Test | Red |
| --- | --- | --- | --- |
| No `PYTEST_ADDOPTS=--durations=30`, no wall time line (main 2ccdf75's `run_on_host`, the tests written first) | `OspreyFlow_Build/scripts/stack_lease.sh` | `test_stack_lease.py`: `…remote_run_lists_its_30_slowest…`, `…offline_run_lists_its_30_slowest…` and the old line test | 3 failed |
| `c=\$?` written `c=$?`: this machine expands it, so every run's exit file says 0 (the reviewer's finding 1) | `OspreyFlow_Build/scripts/stack_lease.sh` | `…start_line_the_host_receives_runs_and_keeps_the_command_s_own_exit_code` | 1 failed (`'0' == '7'`) |
| `echo \$\$` written `echo $$`: the pid file holds this machine's shell, so `tail --pid` stops at once | `OspreyFlow_Build/scripts/stack_lease.sh` | the same | 1 failed (`runner 38235 == runner 38135`) |
| The wall time line removed | `OspreyFlow_Build/scripts/stack_lease.sh` | the same | 1 failed (last line not the wall time) |
| No `slowestReporter.ts` (the test written first) | `src/testing/slowestReporter.ts` | `slowestReporter.test.ts` | 1 failed (import) |
| `ModuleLike` no longer the shape of vitest's own `TestModule` (`relativeModuleId` renamed) | `src/testing/slowestReporter.ts` | `npx tsc --noEmit` (`make typecheck`) | TS2741 at the guard's own line, 18 |

**Found by the plants themselves (rule 15).**
- The first line test rebuilt this machine's quoting by hand, with `replace("\\$", "$")`. A lost backslash therefore passed
  through it green; the lane-reviewer found this (finding 1). The test now runs the very start call the recording ssh
  received, from a `HOME` folder here, as the host runs it.
- That test's first pid check compared the pid file with pytest's own pid, so the `$$` plant stayed green. It now
  compares the file with the parent of the shell that ran `cmd.sh`.
