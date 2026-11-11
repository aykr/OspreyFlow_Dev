# Platform-b · server log for the carries branch, 11 November 2026

P11 part 1's log is `SERVER_LOG.md` on `lane/platform-b-p11` (a second file here, so the two branches never
add the same path).

## About 07:30 UTC · my own lane-reviewer on cf92e93 (read-only)

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

## 07:35 to 07:55 UTC · the fixes (times are the commits' own)

- 39a48b0: one atomic writer (`harness/atomic.py`) for every writer of `deployment.env` (items 4, 5, 11).
- 4c74ace: refresh back to the ADR (item 1), the lock over the whole refresh opened read-only, the
  stale stage said, the pending record kept until done and cleared by `update` after its restarts,
  apply asking Docker by label rather than refusing, the words pointing to `apply`, one env reader
  (items 2, 3, 6–9). A real bug found on the way: `X= # note` read as `# note` by the shared reader too.
- 70a96429: the chart's ConfigMap keys and `subPath` quoted; the checksum case can fail for both lines
  (items 10, 15).
- 96453a0: every verb checked through one helper, `switch` stopping a locked-out other deployment by
  label, `status` saying why (item 12); lint.
- 16 plants, each red for its stated reason (`plants.md`). 665 tests (refresh, update, CLI, the
  harness files touched) and 52 chart tests green offline. ruff clean on every file touched; mypy's
  three errors in `scripts/refresh.py` are on main already.

## Decisions taken

1. **Item 1 withdrawn to the ADR, not built** (PROMPT_L: a contradiction of an accepted ADR goes to the
   orchestrator first). `stop`'s own check still reads the shell: there it predicts what Compose does.
2. **Apply renders rather than refuses** (item 3): the re-render is Amendment 39's own way out, and a
   refusal there is what the redactor hid (item 2), so removing it answers both.
3. **The pending record survives `--files-only`**; `update` clears it after its restarts (one line in
   `harness/update.py`, for the ownership ruling). Cost: a service may restart once more than needed.
4. **A file mounted on its own is still written in place** (`write_shared`, refresh's mounted files):
   a rename would leave the running container on the old inode. None holds a secret.
5. **`doctor` keeps the bare compose argv**, so it still runs on a locked-out deployment to say why.

## Built

**The carries built at 96453a0** after my own lane-reviewer's round, all findings fixed but Q1 (the
ADR) and the two the orchestrator owns (amendment numbers, ownership). Records:
`carries/{REPORT.md,ADR-114-AS-BUILT-DRAFT.md,DOCS_REQUEST.md}`, `plants.md`, the friction row.
The orchestrator's independent review is owed, then the rebase and the gates once. Nothing running.
