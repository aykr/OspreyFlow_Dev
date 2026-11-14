# rules-b am20: ADR-124 Amendment 20, `edges_among` from record ids a chunk at a time

The owner's ruling of 14 November 2026 on the 50,000-node measurement (`../v052batch-50k/findings.md`): fix
`edges_among` in v0.5.2 in that record's shape B. Rules reviews; the graph adapter is its file.

| Gate | Where | Result |
| --- | --- | --- |
| Offline red first | here, main 0245427's adapter | 6 of the 7 new cases red (`red-first.txt`) |
| Offline plants | here | 6 red, each on its assertion; control green (`plants.txt`) |
| make test | server, offline, 6e5def2 | 14,441 passed, 1 failed: main's product-tree-link check, fixed on main at 936b7e4 (`make-test.txt`) |
| make -k ci | server, offline, 6e5def2 | every target but that same check (`make-ci.txt`) |
| Live conformance, rights table, red first, callers' suites, 50k rerun | stack e, lease 15:23:37Z, 799145c | `live-1.txt` |
| The chunk-boundary case's fixture fixed, the live plants with reasons | stack e, lease 15:44:30Z, def4443 | `live-2.txt` (its plant green: no link into the omitted chunk) |
| The same, with links into the omitted chunk | stack e, lease 15:49:59Z, 0b3221d | `live-3.txt`: 3 green; both live plants red; control green |

The 50k rerun (the same shape as the first run, `measure50k_after.py`):
- the batch end to end: done in 26.0 s, saving a view of 50,000 nodes and 49,990 links;
- none of the 500 SECRET leaves in the view;
- the view row's lens column: 231,466 bytes;
- `get_nodes` over the 50,000: 7.9 s;
- `edges_among`: 3.5 s, 4.2 s, 5.8 s and 8.1 s at 5k, 10k, 25k and 50k ids, each answer exactly the fixture's link set, none twice.

Host at the rerun's start: load 2.13, 11 GB free (36 GB available). At its end: load 2.67, 8 GB free (36 GB available).
