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

## The drain (the product's worker, until both outboxes were empty)

The first attempt (in `load-b.run2.txt`) stopped at once: `ApiConfig.from_env()` raises when
`OIDC_JWKS_URL` is unset, and a lane stack has no identity provider. By the orchestrator's ruling the
drain gives the worker a placeholder on a closed port, `http://127.0.0.1:9/jwks` (test-environment
configuration; the indexer never resolves a principal; the product change is a CARRIES row). Try 1
(`drain.try1.txt`) then started the worker without its indexer: the lease gives only `OPENSEARCH_PORT`,
and the worker feeds the index only where `OPENSEARCH_URL` or `OPENSEARCH_HOST` is given, as a rendered
deployment gives it. That worker was stopped by hand, and the drain sets `OPENSEARCH_HOST=localhost`.
Try 2 (`drain.try2.txt`, server run 20261114T062953Z-83fb5d52), uncontended:

| Measure | Value |
| --- | --- |
| Outboxes before | graph 759,044, text 72,000 |
| Drained in | 432 s (06:29:54Z to 06:37:07Z, polled every 30 s) |
| Overall | 831,044 rows in 432 s, 1,924 rows/s |
| Text outbox | 72,000 in at most 93 s (both outboxes fed together), at least 770 rows/s |
| Graph outbox | 759,044 in 432 s, 1,757 rows/s; 1,926 rows/s once the text outbox was empty (653,044 rows in 339 s); fastest 30 s window 2,450 rows/s |
| Final drift check | none, nothing pending: 570,460 nodes in the graph, 642,460 documents in the index; 711 s, 169 MB max |

Memory in the drain: available never under 29 GB (06:44:54Z, during the drift check).

## Step 4's M10 subjects (granted 2026-11-14T08:37:44Z, server run 20261114T083744Z-a6eacc0f)

By the orchestrator's ruling (with platform's revision: a principal holds one `org_unit`, and a code-R
record is read only in its own unit), the cases stage was rerun on stack d under the rules lane's lease
of 2026-11-14T03:27:42Z with `--grant` (the loader's `SOURCE:` form for one source's case). It made no
case; it found the same twelve and set 51 grants, listed back from `investigation_grants`:

| Subject | Level | Cases | Claims for step 4's issuer |
| --- | --- | --- | --- |
| `m10-cleared-unit-fiu` | viewer | all twelve Client-size cases | SECRET, codes P C R, unit-fiu |
| `m10-cleared-unit-intel-covert` | viewer | all twelve | SECRET, codes P C R, unit-intel-covert |
| `m10-cleared-unit-covert` | viewer | all twelve | SECRET, codes P C R, unit-covert |
| `m10-cleared-unit-border` | viewer | all twelve | SECRET, codes P C R, unit-border |
| `m10-part` | viewer | Nominal index, Intelligence reports | OFFICIAL-SENSITIVE, codes P C, unit-records |
| `m10-measure` | editor | Intelligence reports (`01M7C2SXAPP3RF8QRSR2SKEMJK`), the measure case, where M6 draws | OFFICIAL-SENSITIVE, codes P C, unit-intel |

The units owning code-R records in B (`scripts/client_size_plan.py`): unit-fiu (cs-sars, SECRET/R),
unit-intel-covert (5 % of cs-intel's reports, SECRET/R), unit-covert (cs-covert, SECRET/R) and
unit-border (cs-watchlist, OFFICIAL-SENSITIVE/R). A hidden record without code R (cs-intel's SECRET/C
reports, unit-intel) is read by any of the four cleared subjects. No token was minted or written
anywhere: the issuer and the Conduit in front of stack d are step 4's setup.
