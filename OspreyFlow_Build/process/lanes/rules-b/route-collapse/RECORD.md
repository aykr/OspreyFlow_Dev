# rules-b route-collapse: the heartbeat's route view collapses the done rows

The owner's ask of 14 November 2026, through the orchestrator: the default route view listed every step one per line
(47, most done) and was hard to read. `OspreyFlow_Build/scripts/lanes_heartbeat.sh` is admin's; admin is on V4, so rules-b took it for
this change alone.

## What it does

In the default view (and `watch`), the route's done rows collapse, each group's line where its first done row was:

- **A number's sub-steps** (3a … 3i, 3e′, 3f′; the number itself too, when a route has both 3 and 3a): all done,
  one line with the span, `3a–3i ✓ 11 done`; some not done, `3a–3i ✓ 10 of 11 done: <the done ids>` and each one
  not done on its own row after it.
- **The whole-number steps** (1, 2, 4, 5 …), and the letter ids route.tsv's new `# steps` line names (B, U, C, D):
  `steps ✓ 6 done: 1 2 B U 4 5`.
- **The fixes**, every other id (T, Q, … D2, A2, S7, M9, V1 …): `fixes ✓ 21 done: F T Q P …`.
- The ids are listed, wrapped at 120 characters, never cut, so nothing disappears.
- A step not done (running, ready, built, blocked, not started) keeps its own row, with its stages under it, in
  route order.
- The headline's "N of M steps done" counts every step, collapsed or not, as before.

The other views:

- `--steps` (new) is today's route view, one line a step. Its output is byte for byte main's default view, but for
  the "Other views" line, which now names `--steps`.
- `--full` is unchanged. On main it is the overview in full, not the route; the orchestrator's brief said "`--full`
  keeps today's one-line-per-step view". Changing what `--full` shows would have broken the tests that read the overview from it and every
  habit of using it. So the one-line-a-step route went behind a new flag. Rendered against today's tables,
  `--full` is identical to main's (305 lines).

Which letter ids are steps, not fixes, cannot be read from route.tsv's columns (B and U wait on 3c, but so does M9 on
4; all are critical). So route.tsv says so in one comment line, `# steps<TAB>B,U,C,D`. Without the line, every letter
id is a fix. route.tsv is the orchestrator's file, so the line goes as a diff (`route_tsv_steps_line.diff`).

## Gates

| Gate | Where | Result |
| --- | --- | --- |
| Red first | here, main 584db98's script, the branch's tests | 15 red: the 8 new collapse cases, and 7 existing cases adapted to read a done step from its collapsed line; `--full`'s guard green, as it must be (`red-first.txt`) |
| The heartbeat's tests | here, offline ports, 0bb55cc plus the adapted case | 121 passed: `test_lanes_heartbeat_route.py` and `test_lanes_heartbeat.py` |
| Plants | here, `plants.py`, restored from saved text | 6 of 6 red, each on its named case; control 9 passed (`plants.txt`) |
| Today's tables | here, main's route.tsv and progress.tsv, git read | `today-default.txt` (with the `# steps` line: 27 lines, of which 12 are route lines, from 62 lines and 47 route rows); `today-default-without-steps-line.txt` (B and U among the fixes); `today-steps.txt` (`--steps`, identical to main's default but the hint) |
| make test, make -k ci | server, offline | waiting on a slot: the QUEUE has the orchestrator first |

Each existing case adapted (rule 12: the same invariant, read from where it now shows):

- A done step's `" done"` is read from its collapsed line (`_done`): the cases on 2, 3c and 3e done, from the
  progress row, git, LANDED.md and any row shape.
- A done row's full bar `[██████]`, and "no stages under a done row", are read from `--steps`.

The plants (each in the code's own shape):

1. A running step folds into its group.
2. A partly done group shows its span with no ids.
3. The `# steps` line is not read.
4. A long id list is cut, not wrapped.
5. `--steps` is not passed to the view.
6. A whole number with sub-steps is left among the steps.

## Found on the way

`make lanes-check` (in `make ci`) does not run `tests/test_lanes_heartbeat_route.py`: the route view's 50 cases run
only in `make test`. `makefile_lanes_check.diff` adds the file. The Makefile is the owner's, so it goes as a diff.

## Today's default view (main's tables, with the `# steps` line), 22:04Z

```
ROUTE TO V0.5.2 · Tue 17 Nov · 3 days left · on track
  [████████████████░░░░] 38 of 47 steps done · [███░░░░░░░░░░] day 1 of 4

  steps ✓ 6 done: 1 2 B U 4 5
  3a–3i ✓ 11 done
  fixes ✓ 21 done: F T Q P S W E G M R K A V N H D2 A2 S7 S8 S9 M9
  V1  ★ case         14–15 Nov [░░░░░░] running · "View" means a saved view only, and the way back to the whole case…
  V2  ★ case-b       14–15 Nov [░░░░░░] running · The saved views panel: its title, The whole case first, Open now,…
  V3  ★ studio       14–15 Nov [░░░░░░] running · No internal note on screen: "(the client's)", "to be confirmed"…
  V4  ★ admin        14–15 Nov [░░░░░░] running · Every panel and menu on the page's own type scale in both looks, by…
  V5  ★ docs         14–15 Nov [░░░░░░] running · after V1,V2 · The user guide follows the saved-views words; the…
  C   ★ orchestrator 15 Nov    [░░░░░░] not started · after…
  D     orchestrator 15 Nov    [░░░░░░] not started · after C,4 · osprey-small (the GOV.UK demo) from the candidate,…
  6   ★ platform-b   16 Nov    [░░░░░░] not started · after 4,C · The install test on the candidate, from the…
  7   ★ orchestrator 17 Nov    [░░░░░░] not started · after 6 · Cut v0.5.2; print the page tables; the demos when the…
```

Without the `# steps` line, the first and third lines read `steps ✓ 4 done: 1 2 4 5` and
`fixes ✓ 23 done: B U F T Q P S W E G M R K A V N H D2 A2 S7 S8 S9 M9`.
