# L3.2b's gates at e8f4a9e (tree 3df33e79), rebased on main 91335b9

Offline runs: closed ports, no lane. `registry-L3.2b.patch` and `ci-wiring-L3.2b.patch` were applied to the
working tree for the runs and reverted at once; the orchestrator commits both at the merge.

- **`make -k ci`** (`e8f4a9e.ci.txt`): every target green except the seven trivy image scans. Each was refused
  by Docker Hub's pull limit (429, `toomanyrequests`, when resolving `python:3.12-slim` and
  `nginx:1.30-alpine`), so `core-check` reports Error 2. The new `no-branches-check` is green: 1312 files,
  no branch named, and its 12 tests pass.
- **`make test`** (`e8f4a9e.test.txt`): 8457 passed, 2 skipped, 4 failed. The four failures are this
  machine's own and the same four as at L3.2's 153f878: the local `osprey.yaml`, the closed Valkey port,
  `graphify-out` at the root, and the phone extraction fixture, which needs stack a's object store on
  9000.
- **`make test-js`** (`e8f4a9e.testjs.txt`): 2671 passed, 1 failed. The failure is `MatrixView.budget`, a
  timing budget under load; it passed re-run alone (appended to the file).
- **Live** (`L3.2b.live.txt`): lease case on stack a, 18:10:57–18:11:25Z, 48 passed. The real
  ArcadeDB adapter's `edges_among` edge-type filter: 4 conformance cases passed.
- **Keyboard and axe** (not in `make ci` locally): every harness scanned, 446 passed in dark, light and
  GOV.UK. The changed keyboard specs passed on a throwaway port-5195 config, because studio's dev server
  held 5185. Two cases failed only because of that port (a case that expects 5185, and the registry
  check after that case's worker restart).
