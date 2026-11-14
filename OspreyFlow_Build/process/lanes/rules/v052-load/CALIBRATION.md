# v052-load · the calibration (14 November 2026)

Stack d under the rules lane's long lease (taken 2026-11-14T03:27:42Z), at lane/rules-v052-load a816268
(on lane/rules-adr124-am18: ADR-124 Amendment 18's write path). `calibrate.sh` at `--scale 0.02` and
`--graph-scale 0.02`, the stack reset (`reset_stack.py`), then `--graph-scale 0.1`, reset again. Raw:
`calibration.txt`.

**Contended (rule 14), so not a measurement for step 4.** The orchestrator's notice of 14 November: the
case-b lane ran CPU load tests on the server, light rounds from 03:14 to 03:35Z and every core from
03:45 to 03:54Z. The whole calibration ran from 03:28 to 03:40Z, inside the light rounds (at 0.1, its
nodes, links and same_as from 03:32 to 03:38Z). Its rates sized B's projection; step 4 takes B's own
per-file rates from after 03:54Z instead. B's generation (03:41 to 03:49Z) and the first five minutes
of its node stage (03:49 to 03:54Z) fell in the every-core window and are marked so in B's record.

| Stage | 0.02 | 0.1 | Rate at 0.02 | Rate at 0.1 |
| --- | ---: | ---: | ---: | ---: |
| nodes | 13,009 in 40.4 s | 65,046 in 172.4 s | 322 a second | 377 a second |
| links (bulk) | 23,282 in 37.4 s | 115,960 in 178.7 s | 622 a second | 649 a second |
| same_as | 5.3 s | 20.6 s | | |
| texts | 1,440 in 3.9 s | 7,200 in 33.1 s | 374 a second | 217 a second |
| events | 1,953,163 in 69.0 s | 1,981,125 in 76.3 s | 28,300 a second | 26,000 a second |

The graph's rates hold as the graph grows fivefold (they rise a little: fixed costs spread wider), as
the write path's scale test showed. The texts' rate falls (374 to 217 a second); it is the one stage
whose rate drops with size, and at 1.0 it is taken at half 0.1's.

## B at `--graph-scale 1.0`, projected

| Stage | Items at 1.0 | At 0.1's rate | At half it (the margin) |
| --- | ---: | ---: | ---: |
| generate (`--scale 1`, 15 jobs) | about 20 GB | about 15 min (from the 0.02 run's 0.34 GB in 27 s) | 30 min |
| nodes | 650,000 written | 29 min | 58 min |
| links | 1,157,000 | 30 min | 60 min |
| same_as | 54,000 | 4 min | 8 min |
| texts | 72,000 | 6 min (at 217 a second) | 12 min |
| events | 100,000,000 | 64 min | 128 min |
| check | | 1 min | 2 min |
| **load** | | **about 2.5 h** | **about 5 h** |

Then the search index's rebuild from the graph and the drift check, unmeasured here (each a page at a
time; estimated under an hour each). From a start at 04:00Z, B is loaded by about 09:00Z on 14 November
at the margin, well before Wed 18.
