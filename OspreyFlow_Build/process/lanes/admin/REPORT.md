# admin · T1 part 5 · report (12 November 2026): the up-check and the reaper, after two orchestrator reviews

`lane/admin-t1p5` over main `9a4a0fb`, gated at `a23886c`. The reset is its own step (the split ruling); its code
stays on `srv-wt/lane/admin-t1p5`. `SERVER_LOG_T1P5.md` has every finding and its red. (P10 part 2's report is in
main's history at `33e402d`.)

**What merges.** The per-worker store plugin named in the root conftest (`conftest-T1p4.diff`) and the flag dropped
from `make test` (`makefile-T1p4.diff`, the owner's, against main as it stands); in `stack_lease.sh` and its tests
(`stack-lease-T1p5.diff`, the orchestrator's): the up-check before `remote` and `live`; each run tagged and reaped
when it ends and on TERM; `stop <lane>` to end a run (TERM to its group, a bounded wait, KILL, its exit written;
Ctrl-C on the lane's machine ends only the follow); `reap <lane>` for what an ended run left, failing closed; the
start call no longer holding ssh; a run's folder new or refused. Committed: `test_worker_isolation_wired.py`, the
plants harness, `apply_diff.py` (all or nothing across files, whole lines, CRLF, no-newline), the reads audit, the
log, the friction fragment and the gate records.

| Gate, at `a23886c` with the three diffs applied | Result | Record |
| --- | --- | --- |
| Plants, on the server (Linux) | 24 plants, 31 case runs, all red, 0 missed, 0 faults; the whole file green before (72) and after (50, main's script) | `gates/t1p5_plants_a23886c.txt` |
| `make -k ci`, the server, offline | exit 0; cp-policy-check 0 violations | `gates/t1p5_a23886c.ci.raw.txt` |
| `make test`, the server, offline, each part run | pytest 12,789 passed, the server's GPU case alone failed, the plugin's header `worker_isolation: 15 workers …`; live-collect ran (its counts in the log); test-js 3,135 passed and MatrixView's first-frame budget failed (a known perf-budget item, MORNING, failing on main under load too) | `gates/t1p5_a23886c.test.raw.txt` |
| test-js, the Mac | 3,135 passed; MatrixView's budget failed in the full run (3,099 ms against 2,500), passed alone twice at `c2a0010` | `gates/t1p5_mac_a23886c.test-js.raw.txt` |
| Hand-made reds | the old `pkill` (confined to the case's own group: this Mac runs another session's heartbeat watcher); the wired cases; the nested xdist case under an enclosing run of 15; the applier against the old one | `gates/t1p5_{pkill_plant,wired_red,wired_nested,apply_diff}.txt` |

**Found on the way:** a run on a host starts with INT ignored, from main's own start call, so INT does nothing to a
run (stopping one is `stop`); an attempt of mine to make INT work made gate runs uninterruptible and was taken out;
the stand-in ssh hid exit codes and returned before its output closed, so two cases could not be red until it did as
ssh does; the old applier could not apply a diff of two files at all; the nested xdist case did not fit inside `make
test` at 15 workers until it ran offline.

**Not shown red alone:** the reaper's re-read before TERM (a pid changing between the scan and the TERM cannot be
timed; the re-read before KILL, the same function, is red); "no error lines in a run's log" (as root on the server
every environment is readable).

**Carried:** the INT row's text, for the orchestrator to add (not edited on the branch). **Decisions:** the
orchestrator's rulings only (the split; the diffs' ownership; `stop`). Nothing of mine is running; no stack is held.
