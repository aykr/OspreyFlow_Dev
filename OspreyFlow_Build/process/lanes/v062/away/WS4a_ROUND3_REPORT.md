# WS4a, round 3: report (28 November 2026, the builder on the owner's Mac)

The verifier's one finding, fixed. The references, the tolerance, the comparison spec and the product are unchanged;
`package-lock.json` is as on main and `VERSION_WINDOW.yaml` reads `windows: []`. Nothing in CI, no Makefile, release
script or publish script was changed. Synthetic data only.

## A reference changed by hand now has a red case

The finding was right: with the hash comparison in `readReferences` turned off, every case passed. The file's header
said otherwise. A missing record and a record with no reason had no case either.

`readReferences` now takes the folder to read. The committed one is the default, and the comparison spec calls it as
before. Each new case plants its fault in a scratch copy, never in the references, and asks for the whole list of
problems. One case holds that an untouched copy has none.

Red first (`bda85b7`): 7 failed and 14 passed, because the folder argument was ignored. Green after (`9525da3`): 21.

`WS4a_records/plant_references.py` and `.log`, each fault planted in `canvasCompare.ts` itself, restored byte for byte:

| Planted | Red, of 21 |
| --- | --- |
| The hash comparison turned off (the verifier's) | 4: a replaced picture, one changed byte, a changed hash, no entry |
| A picture the record has no entry for let through | 1 |
| A missing picture not reported | 2 |
| A record with no reason taken | 1 |
| A missing record is no problem | 1 |
| A recorded scene that is gone let through | 1 |

My first plant for the missing record changed nothing (`[] && […]` is the second list), so it stayed green. The log is
from the run with the plant corrected.

## The gates at this round's code (this Mac, load about 21; not CI's figures)

- The acceptance command, as frozen: 21 vitest cases and 43 Python cases, green.
- `npm test --workspace apps/workspace`: 414 files, 4,011 tests, and the 3 budget tests passed. `npm run lint`,
  `npm run typecheck`, `no_react_check.mjs`: pass. `test_no_react_check.py` and `test_pages_foundation.py`: 65 passed.
  `ruff check .`: pass. By hand these two Python steps used the worktree's own `.venv`: the line's guard refused a
  command naming the shared acceptance environment. The Stop hook runs the frozen form.
- `same_drawing_versions_check.mjs`: PASS. `citation-check`, `client-name-check`, `test-file-coverage-check`: pass.
- **Not run again:** the budget gate (`test:perf`; round 2's figures stand, taken before this branch's latest merge of
  main), `test:keyboard`, `test:a11y`, and the comparison spec (round 1's answer stands: it refuses on this Mac's
  WebGL renderer).

The owner's question at the end of round 2's report still stands.
