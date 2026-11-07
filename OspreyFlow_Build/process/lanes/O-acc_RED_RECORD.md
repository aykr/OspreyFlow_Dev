# O-acc · red-then-green record (ADR-142 Amendment 1; rule 15)

Run on 7 November 2026 by the orchestrator, `make ci`'s pytest of `tests/test_lanes_launch.py` and
`tests/test_lanes_heartbeat.py` with the throwaway ports pinned. No stack was reached; every test runs
the real scripts in a `tmp_path` repository with stand-in `osascript` and `docker`.

**Red before the build.** With the new tests and the scripts as they stood at `ce785b8`: 9 failed,
8 passed (every new case red; every old case green).

**Green.** With the new scripts: 32 passed (launcher and heartbeat together).

**Each check shown red with its own branch removed** (one planted defect at a time, the rest of the script
as built; each a single failing case):

| Planted defect | Red case |
| --- | --- |
| The session started under the default directory, not the account's | `test_a_lane_started_with_an_account_runs_under_that_accounts_directory` |
| An account `accounts.conf` does not name let through | `test_an_unknown_account_or_a_missing_directory_is_refused_before_any_session_starts` |
| An account whose directory is missing let through | the same |
| `pause-done`'s lease release removed | `test_pausing_a_lane_holding_the_lease_releases_it_before_the_lane_is_paused` |
| `merge-ok`'s `wip(` match removed | `test_the_merge_gate_refuses_a_branch_holding_a_wip_commit` |
| Prompt R's HANDOFF.md line removed | `test_resume_after_a_pause_starts_prompt_r_with_the_handoff_named_first` |
| An account directory's credential file written into the lane's state | `test_no_output_log_or_commit_holds_anything_from_an_account_directory` |
| `fallback-switch` falling back to the orchestrator's account with no fallback line | `test_watch_never_switches_a_lane_without_the_owners_fallback_line` |
| `fallback-switch`'s once-only check removed | the same |
| `paused` handled as `working` in the monitor | `test_a_paused_lane_is_shown_paused_with_its_account_and_never_as_stalled` |
| The usage-limit line removed from Needs you | `test_a_lane_at_its_usage_limit_names_its_account_for_the_owner` |

The planted credential takes the shape a signed-in config directory holds (`.credentials.json`); the
watch case runs the real heartbeat's `watch` pass, which calls the real launcher, as on the owner's
machine.

Not covered by a test: the Terminal window itself (osascript is a stand-in), and a lane's own judgement
of a safe point. `switch` against a live session is exercised only through `fallback-switch`'s path.
