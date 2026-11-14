# v052-load · step B on stack d · record

Graph scale 1.0 (the owner's ruling of 13 November). Stack d, under the rules lane's lease of
2026-11-14T03:27:42Z. Run 1 (`load-b.run1.txt`) stopped in the links stage when the host's
out-of-memory killer took ArcadeDB; the container was recreated at the poc's 9 GiB heap with its data
kept (`arcadedb-recreate.txt`); run 2 (`load-b.run2.txt`, server run 20261114T044557Z-4a75d269)
resumed, skipping the files already loaded.

| Stage | Run | Rows | Wall | Rate | Contended |
| --- | --- | --- | --- | --- | --- |
| generate | 1 | — | 482 s | — | yes (03:45–03:54Z, every core) |
| cases | 1, 2 | — | 6.7 s, 4.5 s | — | run 1 yes |
| nodes | 1 | 650,000 | 2,542 s | 256/s | first 5 min (to 03:54Z) |
| links | 1 then 2 | 896,329 in run 2 (12 files in run 1) | 511 s + 1,107 s | 810/s (run 2) | no |
| same_as | 2 | 54,600 | 77 s | 708/s | no |
| texts | 2 | 72,000 | 153 s | 472/s | no |
| events | 2 | 99,322,372 | 3,104 s | 32,000/s | no |
| check (links stored twice) | 2 | — | 5.9 s | none found | no |
| rebuild | 2 | 642,460 documents from 570,460 nodes | 644 s, 165 MB max | 998 documents/s | no |
| drift (outboxes pending) | 2 | 570,460 nodes, 642,460 documents | 647 s, 168 MB max | none | no |

Memory: available never under 28 GB in run 2 (lowest 06:15:58Z, during the drift check).

## The drain did not run

The outboxes held graph 759,044 and text 72,000 rows after the load. `drain_index.sh` started the
product's worker (`python -m services.api.worker_main`), and the worker stopped within 30 s:
`ApiConfig.from_env()` raises `OIDC_JWKS_URL is not set — Principal resolution has no key source`.
A lane stack has no IdP (stack d runs arcadedb, opensearch, clickhouse, objectstore, valkey, pg), and the
worker takes the API's whole config, which needs a JWKS URL, though the indexer never resolves a
principal. As the orchestrator asked, this was not worked round. The drain's time, its rows a second,
and the final drift check are still owed.
