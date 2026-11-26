# WS4a, round 2: report (26 November 2026, the builder on the owner's Mac)

The verifier's four findings on round 1, all fixed. The workspace stays on Sigma 3.0.3; `package-lock.json` is as on
main; `VERSION_WINDOW.yaml` reads `windows: []` (no entry written, Q1). Nothing in CI, no Makefile, release script or
publish script was changed; the owner's diffs are not applied. Records are in `WS4a_records/`. Synthetic data only.

## 1. Two acceptance tests needed the real window shut (it was three)

Reproduced with GG2a's own lockfile (`37492cc`, one file read from its branch, nothing merged) and its `sigma` entry put
in this checkout, then both files restored byte for byte (`plant_gg2a_state.py`, `plant_gg2a_state-round2.log`). Round
1's tests: **3 failed** there. Besides the two named, `test_an_entry_with_no_difference_left_fails` failed too: it built
its fault on the real lockfile, which then already differs.

**Two assertions in the frozen acceptance file changed.** What they ask now, for the conductor and the owner to see:

| Round 1 | Round 2 |
| --- | --- |
| The real tree passes the merge check **and `--release`** | The merge check passes. `--release` passes **if the real window lists nothing**, and otherwise is refused, naming each entry |
| `test_the_real_window_file_is_empty` | Removed. In its place: **the real window lists Sigma's libraries only** (`sigma`, `@sigma/*`; ADR-002 Amendment 1, items 3 and 4) |

**No longer asserted:** that the real window is shut today. An entry with no difference behind it is still refused by the
check, so the window can open only beside a real difference in the lockfile. `hold_a_checkout` is also run on scratch
trees: it passes in GG2a's shape and fails on a listed `maplibre-gl` difference. With the script's release refusal
switched off in a plant, the open-window case went red, and so did the release case.

The planted faults now start from `LEVEL_LOCK` (the real lockfile with `apps/pages`'s own drawing pins taken out), and
one case holds that it passes as it is.

**For GG2a's merge:** it writes the entry and changes none of WS4a's tests. With its lockfile at `37492cc` and the entry,
all 31 cases pass. I20's third test is still GG2a's (Q5).

**For WS4b:** several planted cases set `apps/pages` on Sigma 4.0.6 against the workspace's own version, or plant under
`@sigma/node-border`. Once the workspace moves to Sigma 4, WS4b will have to change those versions and shapes. They were
not tried against a WS4b tree, which does not exist.

## 2. A window naming one library twice

The check now refuses it in words, whichever entry comes first (`same_drawing_versions_check.mjs`). Four cases, red
before the fix (commit `d6fd73e`): the wrong entry first, the wrong entry last, the same entry twice, and one name in
quotes. At the gate's own call site (`plant_i20_round2.py` and `.log`: no argument, this checkout's own files, GG2a's
lockfile), round 1's script **passed** the window with the wrong entry first; this one **fails** it. The same run planted
Sigma 3.1.0 nested under `@sigma/node-border` again: exit 1, naming both copies. Restored: PASS, hashes unchanged.

## 3. The canvas marks without a browser

`src/canvas/canvasMarks.test.ts`, four cases, run by `npm test`. The stub renderer has Sigma 3's layer ids and Node's
`EventEmitter`, which Sigma's emitter extends. `plant_canvas_marks.py` and `.log`, each fault planted in
`canvasMarks.ts` itself:

| Planted | Red |
| --- | --- |
| The teardown leaves the state mark on | 2 of 4 |
| Nothing listens for a finished frame | 1 of 4 |
| The teardown leaves its listener on | 1 of 4 |
| "drawn" said without waiting for a frame | 1 of 4 |

They hold the marks' own module; that `GlassCanvas.tsx` calls the teardown is not held by them.

**The comments were wrong and are corrected** (`canvasMarks.ts`, `perf/harness.tsx`; no behaviour changed): "drawn" is
the next frame finished **after** the mark is taken. On Sigma 3 that is not the first, which the constructor draws before
anything can listen. The away report's question 3 says "after its first finished frame"; read it as above. The ready
moments are as round 1's report says (Q3): the workspace's budget reads "mounted" (`perf/harness.tsx`'s `readyAt`,
waited for by `perf/perf.spec.ts`); the page service's reads `data-graph-state="ready"`, on GG2a's branch.

## 4. The release-local diff

`git apply --numstat` on round 1's diff counted **1 line removed**: the stray `COMMIT =` hunk. **A second fault in the
same diff, not among the findings:** its docstring said its cases hold whether or not the window is open, and they did
not. The "goes on" case used the real lockfile, and **failed** with GG2a's window open
(`plant_release_window-round2-red.log`). The diff is made again: **20 and 67 lines added, none removed**; the
`release_local.py` half is byte for byte as before.

`plant_release_window.py` and `.log`, in a scratch copy with the diff applied:

| Run | Result |
| --- | --- |
| The diff applied | 9 passed |
| `window_refusal()`'s call removed from `main()` | 1 failed (the refusal case) |
| `window_refusal()` refusing whatever the window holds | 2 failed |
| Restored | 9 passed |
| GG2a's window open in the copy | 9 passed |
| Window open, the call removed | 1 failed (the refusal case) |

The two files have the same four lint findings before and after (at 120 columns, rules E, F, I and UP). The owner's diffs
still apply in round 1's order (checked against a throwaway index).

## The gates at this round's code (this Mac, loaded; not CI's figures)

- `canvasCompare.test.ts` and the two acceptance Python files: green (13 cases; 43 Python cases).
- `npm test --workspace apps/workspace`: 411 files, 3,981 tests, and the 3 budget tests passed.
- `npm run lint`, `npm run typecheck`, `no_react_check.mjs`, `version_isolation_check.mjs`, `ruff check .`: pass.
  `test_no_react_check.py` and `test_pages_foundation.py`: 65 passed. These Python runs used the worktree's own `.venv`;
  the Stop hook runs the frozen commands.
- `citation-check`, `client-name-check`, `test-file-coverage-check`, `route-coverage-check`, `design-check`: pass.
  `test_layout.py`, `test_maintainer_manifest.py`, `test_tree_parity.py`, `test_design_gates_reach.py`: 195 passed.
- **The budget gate** (`test:perf`): 4 passed. Apple M3 Pro, Node 24.10.0 (CI uses 22), load average about 26 to 30.
  First frame `elapsedMs` 7,154 ms (CI's gate 30,000); the page's `readyAt` 2,679 ms (not gated); sweep 1,776 ms a frame
  over 8 frames (gate 3,000).
- **Not run again:** `test:keyboard` and `test:a11y` (round 1's results; this round changes only comments in the files
  they load). The comparison spec: round 1's answer stands. It refused, because the references were made with
  SwiftShader "Subzero" and this Mac draws with SwiftShader "LLVM 10.0.0".

## For the owner (one new question; nothing waits on it)

The check itself still accepts a listed `maplibre-gl` or `graphology` difference, as I20's words allow ("except a
difference written in" the window). ADR-002 Amendment 1 item 4 says MapLibre never differs. The acceptance test now
holds the real tree to Sigma's libraries only. **(a), recommended:** leave it there. (b) The script refuses any entry
that is not Sigma's, so the CI step refuses it too.
