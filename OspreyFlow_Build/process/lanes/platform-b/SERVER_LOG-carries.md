# Platform-b · server log for the carries branch, 11 November 2026

P11 part 1's log is `SERVER_LOG.md` on `lane/platform-b-p11` (a second file here, so the two branches never
add the same path).

## About 07:50 UTC · my own lane-reviewer on cf92e93 (read-only)

It would not let the carries merge: 2 blocking, 12 must-fix, 2 minor groups. In short:
1. **Contradicts an accepted ADR (stop-question).** Refresh counts a value in the shell as held before moving
   files into place (`scripts/refresh.py` `_unset_required`); ADR-114 Am 39 decision 2 says only a value in
   `deployment.env`. CARRIES row 104 asked for it, but PROMPT_L makes an ADR contradiction the
   orchestrator's question first. **Held as Q1; the code is put back to the ADR** (strict).
2. Through `ospreyflow apply` the new refusal words are hidden by the CLI's `Redactor` (every missing value
   is a `*_PASSWORD`/`*_SECRET`), and the test called the harness directly, not through the CLI.
3. The words advise restoring values from the backup set, which a v0.4.12 set does not hold; and apply
   refused where a re-render would have repaired the deployment.
4–5. Apply's `move_into_place` (and `write_shared`, `put_back`) overwrite in place, so the atomic
   `write_private` does not protect the live `deployment.env`; a symlinked file is written in place.
6. A run under sudo leaves a root-owned lock, pending record or stage that stops every later run.
7–8. The pending-restart record is cleared before `update`'s restarts and can be dropped twice more; the
   lock covers the files pass only.
9. Three readers of the env file that disagree (quotes, ` #` comments, empty values); parity untested there.
10. The chart test cannot go red for `checksum/files`. 11. The owner tests cannot tell the old owner from
   the runner. 12. Sibling CLI verbs (`_switch`, status, start, logs, uninstall) unchecked.
13–14. Spec (rule 11), report, friction and the docs request owed; files outside the map.
15. Minor: other unquoted scalars in the chart; a vacuous assertion; "never a value" untested; no folder
   fsync, a left temp file, a pid-named temp. 16. My counts ("20/20 chart tests", "132 green") named no files.

## Questions held for the orchestrator

- **Q1 (contradicts ADR-114 Am 39 decision 2):** should a value from the shell count as held when refresh
  decides to move a compose file into place (CARRIES row 104), given that the next `stop`/`apply` from
  another shell is then locked out? Recommended: no (the ADR as written); the code follows the ADR until
  ruled. `stop`'s own lockout check still reads the shell, because there it predicts what Compose does.
