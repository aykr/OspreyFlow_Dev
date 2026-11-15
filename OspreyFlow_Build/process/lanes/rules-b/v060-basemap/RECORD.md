# rules-b v060-basemap: v0.6.0 item 10, the Great Britain basemap as a step of the demo's recipe

The owner's plan of 15 November 2026 (`process/lanes/v060/OWNER_PLAN_2026-11-15.md`, item 10): the local basemap for
`great-britain`, built as a step of the demo's install recipe. The owner's ruling: the gazetteer carries settlements
only. The item came to rules-b from platform, which owns the code. Platform's three findings, each confirmed in the
code before building:

- the command-line build wrote no points (`map_places.NO_POINTS_HERE`);
- the load used one ArcadeDB transaction for every place;
- planetiler had no `-Xmx`.

## What changed

| Change | Where |
| --- | --- |
| The gazetteer is **named settlements only**: `place` in city, borough, town, village, hamlet, isolated_dwelling, suburb, quarter, neighbourhood, after OSM's "populated settlements" (https://wiki.openstreetmap.org/wiki/Key:place). Farms, localities, islands, squares and every POI are left out | `services/ingest/connectors/geo/osm.py` (`SETTLEMENT_PLACES`) |
| The load runs **5,000 places to a transaction** (`GAZETTEER_BATCH`). A failed batch is rolled back alone and stops the load, and the dataset is registered only after the whole load. Given a `tx`, it uses that one transaction, as the script's own build still does | `scripts/build_local_basemap.py` (`load_gazetteer`); `services/api/map_admin.py` (`_build_here`); `services/api/app.py` (the Admin route) |
| The extract is **read once**, for both the load and the points (it was read twice) | `scripts/build_local_basemap.py` (`read_places`) |
| planetiler is given **`-Xmx2g`** (`PLANETILER_HEAP`); the measurement below held it | `scripts/build_local_basemap.py` (`run_planetiler`) |
| **The points.** `map admin build` opens the Conduit's analytics store as the Conduit does. With the Conduit stopped, it writes the points. With the Conduit running, DuckDB's lock refuses the open, and the build says so, as before | `services/api/map_admin.py` (`_analytics_if_free`) |
| **Two stages** for the rebuild window (the orchestrator, on the owner's word): `--stage tiles` (download, planetiler, the settlements saved to `<region>.places.json`; no graph, store or registration) and `--stage places` (that file loaded, with no extract, download or planetiler; the points and the registration; refused in words without the tiles stage's files). No `--stage` is the whole build | `services/api/map_admin.py` (`build_basemap`, `STAGES`, `PLACES_FILE`) |
| The demo recipe's step, (A) before the window and (B) in it, as a diff for the demo lane's file | `demo_handoff_basemap_step.diff` |

## Gates

| Gate | Result |
| --- | --- |
| Red first, the first five changes, on main's code | 6 failed (`red-first.txt`) |
| Red first, the stages | 7 failed (`red-first-stages.txt`) |
| Plants | 10 of 10 red, each on its named case; control 17 passed (`plants.txt`) |
| Offline suites: the new files, the connector, registration order, the build script, the Admin route, dataset registration, the set-up console, the shipped profiles | 85 passed |
| Core `ruff check .` and mypy on the changed modules | clean |
| make test, on the server, offline, at 1abec56 | 14,708 passed and 45 skipped in Python; 398 files with 3,593 tests in the workspace, and the two smaller JavaScript suites, all passed; exit 0 (`make-test.txt`) |
| make -k ci, on the server, offline, at 1abec56 | every target but `trivy-image-superset`: 192 HIGH, 0 CRITICAL in the Superset image, main's own (rules' v0.6.0 Superset CVE item); exit 2 (`make-ci.txt`) |
| Live: `tests/ingest/test_gazetteer_batches_live.py` (12 settlements over three batches, a cafe and a farm left out, a rebuild finding all 12 held) | written. It runs in the live suite, not under this item's lease, which was the measurement's |

Tests adapted, each with its reason in the test:

- **The connector's "keys on name, not place" case** is now "settlements only", the owner's ruling. The shared
  fixture's cafe became a suburb, so the live tests' counts of three stand.
- **The registration-order and Admin-route cases** no longer see the caller begin or commit a transaction. The load
  commits its own batches. A failed build after the load leaves the batches committed and the dataset unregistered.
- **The planetiler argument list** gains `-Xmx2g`.

## The measurement

ospreyflow-test, stack b, under the lease rules-b took at 2026-11-15T10:55:47Z. The QUEUE showed rules-b first and
`pgrep -x make` was empty. The line was deleted and the stack was brought down and released afterwards. The script is
`measure_gb.sh` with `measure_load.py`; the log is `measure-gb.txt`.

- planetiler ran in the Conduit's own image, `ospreyflow/api:ci` (Temurin 21.0.13), with only the scratch folder
  mounted.
- The loader ran from the run copy at 75d9ad2 against stack b's ArcadeDB, with a scratch DuckDB for the points.
- The scratch folder was removed at the end.
- A first attempt, 10:56Z, stopped after 4 s on the script's own URL lookup (`measure-gb-attempt1.txt`); it was
  fixed at 75d9ad2.

The host had 16 cores and 62 GB, with about 49 GB available at both start and end. Load was 2.6 at the start and 1.4
at the end. Wall time was 70 min.

| What | Figure |
| --- | --- |
| Download: Geofabrik `great-britain-latest.osm.pbf` and planetiler v0.10.2's jar | 646 s; extract 2,201,340,386 bytes; jar 93,278,824 bytes, sha256 `f310bd04…c167e4d` |
| planetiler at `-Xmx2g` | **438 s (7 min 18 s)**, exit 0, not OOM-killed; **container peak 3,020 MB** (the heap plus the JVM's own); all 16 cores |
| The pmtiles | 1,581,680,656 bytes |
| The load (one pass over the extract, 12 batches, the points) | **2,239 s (37 min 19 s)**: 56,486 created, 0 referenced, 0 rejected; 56,486 points written; **peak 2,400 MB** |
| A pass over the extract alone (the count) | 855 s (14 min 15 s); peak 2,344 MB. So about 14 of the load's 37 minutes are reading and about 23 are writing |
| **Named points against settlements** | 236,115,110 nodes; **1,059,567 named points**; **56,486 named settlements** (5.3%) |
| Settlements by kind | hamlet 20,169; village 14,933; isolated_dwelling 10,445; suburb 5,800; neighbourhood 2,685; town 1,546; quarter 837; city 71 |
| Disk | extract 2.1 GB; planetiler's sources 1.4 GB; pmtiles 1.5 GB; the points' DuckDB 9.8 MB. About 5 GB in all, 3.5 GB of which can go after the build |

**What this means for the demo.** The whole build is about 45 min of work plus the 11-minute download. Memory stays
under about 3 GB at any moment.

- **(A), before the window, with the demo up: about 32 min.** That is the download, planetiler, and the settlements
  read. planetiler takes every core for its 7 minutes.
- **(B), in the window: about 23 min of writing.** (B) was not measured on its own. The figure is the load minus the
  read pass. Its peak memory should be well below the read's 2.4 GB, since it reads 56,486 rows from a small file,
  but that was not measured.

## Not done here

- **Nothing ran on the demo server.** The owner is told before the first real build there.
- **Rule 13 needs no `keyboard.spec.ts` step**: no screen changed.
- **Writing 56,486 settlements at about 41 a second is slow.** It is the recipe engine's per-row work. It is left as
  it is: speeding it up is outside item 10.
