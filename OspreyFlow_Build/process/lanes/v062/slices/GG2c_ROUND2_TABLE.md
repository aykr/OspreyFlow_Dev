# GG2c, round 2: the guard finds its folders itself (the conductor, 26 November 2026, 15:10 UTC)

From the round-1 verifier's record (tip `3d3a07114c`): one gap. **This round is the row below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | **`deltaClientHome.test.ts` about 11** walks a hand-written folder list (`SCANNED`), which leaves out `deck-capture/` (four harnesses importing `../src/...`), `compute-tier1/`, `scripts/` and the workspace's root files (rule 12: a walkthrough with no discovery). **Walk the whole workspace** (`apps/workspace/`), skipping only `node_modules`, build output and the guard's own file, and say which you skip and why. A plant at the real shape: an `import … from "../src/workingset/deltaClient"` in a `deck-capture/` harness, and a copy of the client there, each red; then removed. | The guard green on the branch; both plants red; your frozen checks green. If the guard walks a folder by itself, say whether it needs a scan row (the conductor stages it). |
