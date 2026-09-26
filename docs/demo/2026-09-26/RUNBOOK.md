# Live runbook — 26 September 2026, Stage 3a's residual

Same discipline as the 24 September precedent: **only what actually ran tonight, against this
checkout, is listed as runnable.** Everything attempted and not reached is in the "not reached"
section with the reason, not quietly omitted.

Machine: Apple Silicon laptop, 36GiB system RAM, Docker Desktop VM allocated 9.70GiB.
Checkout at `968b555` at the start of the round.

---

## 1. The local PMTiles basemap — built for real, twice

The thing `07_BUILD_PLAN.md`'s Stage 3a disclosure said had never happened. It happens now.

**Prerequisites installed tonight** (neither ships with this repository):

```
brew install openjdk            # openjdk 27 (2026-09-15)
export PATH=/opt/homebrew/opt/openjdk/bin:$PATH
curl -L -o planetiler.jar \
  https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar
                                # 93,278,824 bytes
```

**The builds**, both via the real `python -m scripts.build_local_basemap`, end to end — download,
planetiler, gazetteer load into a real ArcadeDB, provider registration:

| Region | Extract | PMTiles out | Gazetteer | Wall time |
| --- | --- | --- | --- | --- |
| `rutland` | 1,934,666 B | 1,767,790 B | 855 places created, 0 rejected | **6m 13s** |
| `berkshire` | 22,488,305 B | 14,954,836 B | 9,695 places created, 0 rejected | **2m 07s** |

Berkshire is the faster of the two only because planetiler's three auxiliary sources (lake
centrelines, water polygons, Natural Earth) were already downloaded by the Rutland run and reused
from `<output-dir>/sources`. Rutland's 6m13s is the honest cold-start figure.

`python -m scripts.verify_map <config>` — `verify map: 2 provider(s) passed.`, exit 0.

The output is a real PMTiles v3 archive (`50 4D 54 69 6C 65 73 03` — `PMTiles\x03`), served by the
Conduit at `GET /v1/map/local-source/{provider_id}` with real `206 Partial Content` range
responses, and rendered by the Glass. Proven by `apps/workspace/live/basemap.spec.ts`, not by eye.

**Three faults found by doing this, all fixed tonight** (`6cfe5ab`, `2f6a8e7`):

1. `run_planetiler`'s flag list had never been run against a real planetiler and was wrong —
   missing `--download`, so it exited non-zero before reading a node. `--download_dir` is now
   pinned too; its default is relative and would have written several hundred megabytes into this
   repository's own `data/`.
2. `download_extract` would have written Geofabrik's HTML home page to disk as a `.osm.pbf`.
   Geofabrik has renamed `great-britain` to `united-kingdom` and answers the retired *sub*-extract
   path with a 302 to its home page, which `follow_redirects=True` turns into a 200. The
   top-level `great-britain-latest.osm.pbf` alias still resolves (checked directly), which is why
   nothing had noticed.
3. The Glass could not fetch a local basemap from an authenticated Conduit **at all** — MapLibre's
   `pmtiles://` protocol handler does not go through `transformRequest`, so every tile read came
   back 401 while the availability preflight (which uses `fetch`, and does send the token)
   succeeded. A silent blank map with no error shown.

**And one licence correction.** planetiler's own closing output states the tiles it generates are
a CC-BY work of the OpenMapTiles profile as well as ODbL OpenStreetMap data, and must display
"© OpenMapTiles © OpenStreetMap contributors". Every provider `register_local_provider` wrote
declared only the OSM half. Fixed; `00_ARCHITECTURE.md` §1.2 principle 3 is why it matters.

**The region has to cover the data.** The HMP fixture's yards are at ~51.5°N, -0.6°E — Berkshire.
The Rutland build is a valid PMTiles file from which the Glass draws *nothing*, silently, because
the viewport is 130km away from anything it contains. Every other signal said the basemap was
fine. This is now recorded in `GEOFABRIK_REGIONS` and in `DEMO_GUIDE.md` §3.6.

---

## 2. `DEMO_GUIDE.md` §2–§3, re-run command by command

Run in order, on a database dropped and recreated first. Every step below completed.

| Step | Result |
| --- | --- |
| §3.1 `make dev-up` | 6m 45s, all containers healthy |
| §3.1 stop ollama/litellm/speaches | 3.2s |
| §3.1 drop + recreate `ospreyflow` | `"result":"ok"` both |
| §2 `mint_dev_token` + `http.server 8888` | JWKS served, 200 |
| §3.2 Conduit up | responding in ~6s |
| §3.3 `POST /v1/investigations` | `01M3FQ4QW8VQPP1NNNCJYVWP1G` |
| §3.4 `seed_hmp_fixture` | 400 Person, 10 yards, 262+4 events — **27.1s** |
| §3.4 `seed_fixture_corp` | 10 resolution Person + 17 SAME_AS, 21 ring nodes/63 edges, 8-spoke hub — **5.2s** |
| §3.5 Conduit restarted | 200 on `/v1/map/providers` |
| §3.6 Glass | started by the live tier's own Playwright `webServer` |
| §3.7 `make glass-live` | **6 passed** |

**Corrections this run forced into the guide** (all in `DEMO_GUIDE.md`, listed per the brief):

- §3.6's basemap paragraph rewritten from "building one needs planetiler and a network-reachable
  OSM extract, neither available in every environment" to the actual, proven procedure, with the
  region-coverage rule and the measured timings.
- §3.6 gains the warning not to point `--osprey-config` at the committed `osprey.yaml`:
  `register_local_provider` round-trips through `yaml.safe_dump` and would strip every comment in
  it. This run used a copy, with `OSPREY_CONFIG_PATH` pointed at it.
- New §3.7 ("Checking the bring-up actually worked") documents `make glass-live`, and records that
  **port 5173 is not arbitrary** — `CORS_ALLOWED_ORIGINS` defaults to `http://localhost:5173`, and
  a Glass on any other port has every request refused at the browser's CORS preflight while the
  app sits on "Loading…" with nothing in the Conduit's log naming CORS. Found by running the live
  tier on 5186 first.
- §1's table and §4's "what to avoid promising" were stale — see §4 below.

---

## 3. What the live tier now proves

`make glass-live`, six specs, all green against the stack above; all six skip with a named reason
when `OSPREY_TEST_LIVE_GLASS=1` is absent (verified both ways).

| Spec | Step it closes |
| --- | --- |
| `basemap.spec.ts` | Stage 3a residual 1 — the Map view draws tiles from the real build |
| `fixture-corp.spec.ts` → query builder | ADR-032's "set returned with its count"; also the user-visible face of the `select`/`project` fix |
| `fixture-corp.spec.ts` → threshold | ADR-035 §C5 property 1 — the threshold moved live, merged/split/affected reported |
| `scenario-a-a12-a15.spec.ts` → A12 | Clique Metric computed and ranked, after a real keyboard-driven expansion |
| `scenario-a-a12-a15.spec.ts` → A13–A15 | The assessment composer opens from the Inspector's Judgements tab |
| `scenario-a-a12-a15.spec.ts` → A15 | The export drawer opens and offers all three export kinds |

---

## 4. Not reached, and why

**Fixture Corp's `explain`, pathfinder and path-length comparison — not merely undone, currently
impossible.** No Fixture Corp entity can be put into the Glass's working set. The working set has
one entry point, the search box, and search is exact identifier match; the Fixture Corp seed sets
no identifier on any of its entities. Measured directly against the real store:

| Fixture | Persons | carrying `nino`/`pnc_id`/`prison_number` |
| --- | --- | --- |
| HMP | 400 | **400** |
| Fixture Corp | 65 | **0** |

Its 3 Organisations carry no `org_ref` either. The visual query builder finds them by entity type
but, per ADR-032, reports the matched count rather than loading anything — that is the specified
behaviour, decided deliberately, not a defect in it.

So closing this needs either a searchable identifier on the fixture (an ADR-035 §C5 fixture-shape
change) or a way to load a pattern result into the working set (which ADR-032 decided against
once). Both are design calls. `Claude outputs/handoff/DECISION_NEEDED.md` asks the owner.

**A13–A15 are opened, not driven to completion.** The composer opens and the export drawer opens
with all three kinds; a judgement is not submitted end to end, and the S2-marked-item
blocked-then-justified path is not exercised. The specs say what they assert and no more.

**The rendered `local-lite` deployment was not launched, and nothing here ran against one.** This
machine's Docker daemon reports 9.70GiB against `local-lite`'s 16GiB floor — unchanged since
round 05, and `tests/harness/test_six_screen_live_exit.py` already asserts Preflight's correct
refusal on it. Everything above ran against `DEMO_GUIDE.md` §3's host-process stack (a `uvicorn`
Conduit and a Vite Glass over `make dev-up`'s containers), which is what that guide documents and
what Stage 3a's disclosure is about. It is **not** the "real installed stack, demo analyst signed
in through the real OIDC flow" round 12's brief asked for: there is no Keycloak in
`deploy/compose/dev.yaml`, and the bearer token here is `mint_dev_token`'s, not an OIDC flow's.
