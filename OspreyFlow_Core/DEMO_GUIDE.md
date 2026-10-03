# OspreyFlow — demo and analyst walkthrough guide

How to get a running OspreyFlow in front of an analyst, and what to show them once it is there.

**This guide documents only what is built and
verified today.** Where a demo case is planned but not built, it says so rather than describing it
as though it works — the failure mode this project has already recorded twice in its own
documentation.

Every command below was checked against the repository rather than transcribed from the
specification. Where a step is known to be missing, it is called out as a gap, not written as an
instruction that will fail.

---

## 0. System requirements

**Minimum: 16GiB system RAM, with the Docker Desktop VM allocated 10GiB of it** (Docker Desktop
→ Settings → Resources → Memory). **32GiB total system RAM is the comfortable floor**, not the
minimum — 16GiB leaves the remaining 6GiB to cover macOS/Docker Desktop's own overhead, the
Conduit, the Glass, and a browser tab actually rendering the Glass, which is tight rather than
comfortable. Both numbers come from measuring this stack directly, not from a vendor
specification: ArcadeDB alone peaked at 7.75GiB in a demo rehearsal, above an earlier measurement's
5.2–6.9GiB range — corrected here rather than left stale, since the 10GiB VM floor above already
covers the higher figure with headroom. The Docker
Desktop VM's default allocation on a typical machine, 8GiB, is not enough headroom above either
figure to run reliably — this was measured as repeated out-of-memory kills before the VM allocation
was raised).

**The containers this demo actually needs: ArcadeDB, Postgres, Valkey, MinIO.** Plus the Conduit
(`uvicorn`, a host process — §3.2 below) and the Glass (a Vite dev server, also a host process —
no packaged build exists yet). `make dev-up` starts three more — **Ollama, LiteLLM and speaches —
and none of the three is required for either acceptance scenario** (`08_ACCEPTANCE_SCENARIOS.md`'s
own A1–A15/B1–B21, checked directly: neither calls `ModelPort` anywhere; both fixtures are built
entirely through structured recipe/CSV ingest, never free-text extraction). Stopping all three
after `make dev-up` (`docker stop compose-ollama-1 compose-litellm-1 compose-speaches-1`) does not
affect either scenario and meaningfully reduces the memory this demo needs to survive.

**What is unavailable without Ollama/LiteLLM:** free-text entity extraction — "ingest a witness
statement, extracted entities appear as `inferred` with correct source spans" — real and already
built, demonstrable through the API — and anything built on top of it.
Neither of the two acceptance-scenario demo cases in §1 below needs it. `speaches` (speech-to-text)
is not used anywhere in this codebase's own routes or either scenario; nothing is lost by leaving
it stopped.

---

## 1. What you can demo today

Every demo case below has a **distribution class** (`06_DECISIONS.md` ADR-035): `shipped` means it
is allowed inside an artefact given to a customer or tester; `internal` means it must never leave
this project, in any form, at packaging time — enforced by a fail-closed registry and a packaging
gate ADR-035 designs and not yet built. Until that registry exists, treat the
column below as the same binding statement in prose that the registry will enforce mechanically.

| Demo case | Distribution | State | What it shows |
| --- | --- | --- | --- |
| **Scenario A, steps A1–A11** (HMP fixture) | `shipped` | **Built and exit-verified** (automated CI — `glass-perf`/`glass-keyboard`/`glass-map-verify` and the acceptance-scenario test suite). **Live-walkthrough verification through a running Glass: recorded in an internal rehearsal log** for exactly which sub-steps have actually been driven through a browser and which have not | Timeline, map, cross-filtering, boundary and site-grid filters, the weekend and time-of-day findings, the site hotspot |
| **The Ingest Studio**, Connect → Publish (CDR fixture) | `shipped` | **Built and exit-verified** | Onboarding a new source without touching the ontology: profiling, row-template mapping, dry-run verify, publish with versioning |
| Scenario A, A12 (Clique Metric) | `shipped` | **Built and verified through the Glass** — computed and ranked after a real keyboard-driven expansion (`apps/workspace/live/scenario-a-a12-a15.spec.ts`, and an internal rehearsal log) | Ranking the insular subgroup |
| Scenario A, A13–A15 (assessment, export) | `shipped` | **Built; partly verified through the Glass** — the assessment composer opens from the Inspector and the export drawer offers all three kinds, both asserted live. **Submitting a judgement end to end, and the S2-marked-item blocked-then-justified path, are still not walked through a browser** (recorded in an internal rehearsal log, §4) | — |
| Scenario B (comms and identity pivot) | `shipped` | Partly built; the remaining work is split across several build stages by ADR-022 | — |
| **Extraction and entity resolution** | `shipped` | Built, **API only** | Demonstrable to engineers through the API; there are no screens yet |
| **Scenario C — "Fixture Corp"** (Enron-*shaped*, R24, AMLSim-*shaped* generator) | `shipped` | **Built** (`scripts.seed_fixture_corp`) — its four ADR-035 §C5 properties are **verified structurally** (`tests/scenarios/test_fixture_corp_shape.py`). Moving the resolution threshold live is now verified through the Glass. **`explain`, the pathfinder and path-length comparison are not, and currently cannot be: no Fixture Corp entity can be loaded into the working set** — 0 of its 65 Persons carry any of the identifiers search matches on, against 400 of 400 for HMP (measured directly). See §6 and the internal rehearsal log, §4. Not the ~150-employee Enron-shaped corporation §6 and Scenario C (C1–C20) describe — see §6 | See §6 |
| **The real Enron email corpus** | `internal`, **admitted only via the owner's own local exceptions list — see §6** | Owner-run demonstration only, on the owner's own device, never distributed to an attendee | — |
| **VAST Challenge dataset** (generated fixture) | `internal` | Decided (ADR-026); fixture not yet built | See §7 |
| **VAST Challenge dataset** (the published files themselves) | Not admitted, any class | ADR-026: "standing rule 3 is not amended" — never used, shaped or verbatim | See §7 |

The honest summary: **Scenario A on the HMP fixture is the demo actually driven through the
Glass**, and it is a good one — as of 26 September 2026 that now includes A12's Clique Metric and
the local PMTiles basemap rendering real tiles, both asserted by automated live specs rather than
by eye. Fixture Corp is built and structurally proven, and its resolution threshold is
demonstrable, but the rest of it cannot be shown in the Glass at all until it gains a searchable
identifier or the query builder gains a way to load its results. an internal rehearsal log
has the honest state of what has, and has not, actually been driven through a browser.

---

## 2. Before you start: minting a token and a JWKS fixture

The Conduit validates JWTs against a JWKS URL (`OIDC_JWKS_URL`, read with no default in
`services/api/config.py` — the service will not start without it, and only accepts an `http`/
`https` URL, never a bare file path). The Glass sends a bearer token from `VITE_DEV_BEARER_TOKEN`.
`scripts/mint_dev_token.py` wraps `tests/conftest.py`'s own signing logic (`sign_token`,
`default_claims`) the same way `scripts/seed_hmp_fixture.py` already wraps a test fixture — the
correction already made three times for `revert_load`, the local-basemap build and the HMP seed.

**Use the project venv's own interpreter, not a bare `python`** — the 23 September 2026 demo
rehearsal (an internal record) found a bare `python -m tools.mint_dev_token` picks
up whatever interpreter is first on `PATH`, which on a machine with more than one Python install is
not necessarily the one with this project's own dependencies (`pyjwt`, `cryptography`) installed:

```
PYTHONPATH=.:packages .venv/bin/python3 -m tools.mint_dev_token --jwks-path /tmp/dev-jwks/jwks.json
```

Prints a signed token to stdout and writes the public JWKS to the given path. Re-running it at the
same `--jwks-path` reuses the same keypair, so minting a second token — a different `--clearance`,
say — never invalidates one already in use by a running session. `--ttl-hours` defaults to 8: the
test helper's own 5-minute `default_claims` default is right for an assertion that runs in
milliseconds and useless for a person working a session.

**DEV-ONLY — read the script's own module docstring before using it against anything but a local,
throwaway setup.** It mints a token for any clearance and org-unit asked for; the docstring states
why this is safe in practice (never present in any deployment image; meaningless against a real
IdP unless someone deliberately repoints `OIDC_JWKS_URL` at it) and prints the same warning as a
banner on every run.

Serve the JWKS directory it wrote — the script prints the exact command:

```
python3 -m http.server 8888 --directory /tmp/dev-jwks
```

---

## 3. Bringing up a demo environment

Run from the repository root. Roughly fifteen minutes on a cold machine, most of it image pulls.
**This sequence is scripted — an internal `demo_up.sh --reset` script runs every step below in
the order that actually works, and is the recommended path.** The manual sequence below is the
reference the script encodes, kept for anyone who wants to run a step by hand or understand what
the script is doing; both were proven against a real stack on 23–24 September 2026
(an internal rehearsal log).

**The order below differs from an earlier version of this guide in two ways, both found by that
rehearsal.** Creating the investigation needs the Conduit briefly running (it is an HTTP call);
seeding needs the Conduit stopped (DuckDB takes an exclusive lock the Conduit's own `AnalyticsPort`
also holds a handle to) — so the Conduit starts twice, not once, with seeding in between. And the
Conduit is bound to `127.0.0.1` explicitly, with the Glass opened at `localhost:5173`, never
`127.0.0.1:5173` — the rehearsal found the Vite dev server on this machine resolved `localhost` to
`::1` (IPv6) only, so `127.0.0.1:5173` did not connect at all.

### 3.1 Start the backing stores

```
make dev-up
docker stop compose-ollama-1 compose-litellm-1 compose-speaches-1
```

`make dev-up` brings up ArcadeDB, MinIO, Valkey, Postgres, Ollama, LiteLLM and speaches, and blocks
until every health check passes. Published ports: ArcadeDB `2480`, MinIO `9000` and `9001`, Valkey
`6379`, Postgres `5433` (mapped from the container's `5432`), Ollama `11434`, LiteLLM `4000`,
speaches `8001`. The second command stops the three model containers this demo does not need —
§0 above has the full reasoning; skip it if you also want the extraction/resolution API demo.

> **Postgres is on 5433 deliberately.** A native macOS Postgres on the host's `5432` once
> intercepted connections meant for the container and cost a session to diagnose. Do not remap it
> back.

**Resetting to a clean database.** Between demos, or the first time on a machine, drop and
recreate the ArcadeDB database rather than trust whatever an earlier run left in it:

```
curl -u root:playwithdata123 -X POST http://localhost:2480/api/v1/server -d '{"command":"drop database ospreyflow"}'
curl -u root:playwithdata123 -X POST http://localhost:2480/api/v1/server -d '{"command":"create database ospreyflow"}'
```

### 3.2 Start the Conduit, briefly, to create an investigation

`services/api` is **not** in the dev compose file, so it runs by hand — bound to `127.0.0.1`
explicitly, not a bare `--port` (see this section's own opening note):

```
PYTHONPATH=.:packages OIDC_JWKS_URL=http://localhost:8888/jwks.json \
  CORS_ALLOWED_ORIGINS=http://localhost:5173 \
  .venv/bin/uvicorn services.api.app:app --host 127.0.0.1 --port 8000
```

(the JWKS URL is whatever §2's `mint_dev_token`/`http.server` pair actually served — this is the
common local case, not a fixed value)

**`CORS_ALLOWED_ORIGINS` is required now.** The Conduit used to default to `http://localhost:5173`,
which meant a *rendered deployment* that set nothing inherited a development origin — found
running a rendered deployment for real, and fixed by making the default empty and the render
explicit. A Conduit serving a Vite-hosted Glass must therefore be told the
Glass's origin; without it every request fails at the browser's preflight and the app sits on
"Loading…" with nothing in the Conduit's log naming CORS (§3.7 has that story).

`PYTHONPATH` must include both the repository root and `packages/` — neither a bare `python -m`
nor `uvicorn` puts them on `sys.path`, which is why `services/api/Dockerfile` sets it explicitly.

Other settings default sensibly for local use and are all read from the environment
(`services/api/config.py`): `VALKEY_HOST`/`VALKEY_PORT`, `POSTGRES_HOST`/`POSTGRES_PORT`/
`POSTGRES_USER`/`POSTGRES_DB`, `ANALYTICS_DB_PATH` (default `../OspreyFlow_Data/_local-runtime/analytics.duckdb`, the Data folder beside the product folder),
`OSPREY_CONFIG_PATH` (default `osprey.yaml`).

### 3.3 Create an investigation and note its id, then stop the Conduit

```
curl -X POST http://127.0.0.1:8000/v1/investigations -H "Authorization: Bearer <token>"
```

with your bearer token from §2. **Keep the id it returns** — the seeding step needs it, and the
Glass reads it from a `?investigation=<id>` URL parameter (§3.6 below). Then stop this Conduit
process (`Ctrl-C`, or `kill` its job) — §3.4's seed step needs the DuckDB file free.

### 3.4 Seed the fixtures, with the Conduit stopped

```
PYTHONPATH=.:packages .venv/bin/python3 -m scripts.seed_hmp_fixture \
  --investigation-scope <the id from 3.3>
PYTHONPATH=.:packages .venv/bin/python3 -m scripts.seed_fixture_corp \
  --investigation-scope <the id from 3.3>
```

`--investigation-scope` is required and deliberately not defaulted on both scripts. Every automated
HMP/Fixture Corp test seeds under its own constant scope, which is fine inside a test process; a
live demo needs the events and graph tagged with the investigation id the running Glass session is
actually using, because `EventFilter.investigation_scope` is what every `/v1/analytics/*` route
filters on. **Pass the wrong scope and you will seed data that no query in your session can see**
— the graph will look populated and the timeline will be empty.

Optional arguments to `seed_hmp_fixture`, all with environment fallbacks: `--analytics-db-path`
(default `../OspreyFlow_Data/_local-runtime/analytics.duckdb`, the Data folder beside the product folder), `--principal-id` (default `hmp-seed-worker`), `--clearance`
(default `OFFICIAL`), `--org-unit` (default `unit-1`). §6 has `seed_fixture_corp`'s own shape.

Both scripts write to the same stores a real Conduit reads from — `build_hmp_graph`/the Fixture
Corp graph builder against the same ArcadeDB, and `AnalyticsPort.load_events` against the same
DuckDB file. Neither is a bypass of either store.

### 3.5 Restart the Conduit

Same command as §3.2 — the Conduit has no persistent state of its own beyond the stores it reads,
so restarting it after seeding needs nothing special:

```
PYTHONPATH=.:packages OIDC_JWKS_URL=http://localhost:8888/jwks.json \
  CORS_ALLOWED_ORIGINS=http://localhost:5173 \
  .venv/bin/uvicorn services.api.app:app --host 127.0.0.1 --port 8000
```

### 3.6 Start the Glass

```
VITE_API_BASE_URL=http://127.0.0.1:8000 \
VITE_DEV_BEARER_TOKEN=<the token scripts/mint_dev_token.py printed in §2> \
  npm run dev --workspace apps/workspace
```

Then open `http://localhost:5173/?investigation=<the id from 3.3>` — **`localhost`, never
`127.0.0.1`** (this section's own opening note). The `?investigation=` parameter is read once on
load and takes precedence over anything left in `sessionStorage` from an earlier session in the
same browser tab (`02_GLASS_FRONTEND.md` §2.1's own proposal has the full reasoning) — this
replaces an earlier version of this guide's manual `sessionStorage.setItem(...)` + reload step
entirely. Opening the bare URL with no parameter still works exactly as before: the Glass creates
its own investigation via `POST /v1/investigations` when neither the URL nor `sessionStorage` names
one.

**The Map view will show "Basemap not built" rather than a blank canvas** unless a local PMTiles
build already exists at `osprey.yaml`'s configured path. Every other view (Timeline, Graph, the
hotspot panel) works without it — `02_GLASS_FRONTEND.md` §3.5's own proposal has the full
reasoning for why this now fails loudly instead of silently.

**Building one, proven end to end on 26 September 2026** (an internal rehearsal log has
the timings and the full transcript). It needs a JDK and a planetiler jar, neither of which this
repository ships:

```
brew install openjdk            # openjdk 27 on the machine this was proven on
export PATH=/opt/homebrew/opt/openjdk/bin:$PATH
curl -L -o planetiler.jar \
  https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar

PYTHONPATH=.:packages .venv/bin/python3 -m scripts.build_local_basemap \
  --region berkshire --output-dir <a directory outside this checkout> \
  --planetiler-jar ./planetiler.jar --osprey-config <your osprey.yaml>
PYTHONPATH=.:packages .venv/bin/python3 -m scripts.verify_map <your osprey.yaml>
```

**Use `--region berkshire`, not a smaller one, and not `great-britain`.** The extract has to
cover the fixture you are going to look at: the HMP fixture's ten yards sit at roughly 51.5°N,
-0.6°E, which is Berkshire. A Rutland build (England's smallest county, and the quickest way to
prove the pipeline itself works) is a perfectly valid PMTiles file that the Glass opens, reads
and draws nothing from, because the viewport is over an area it does not contain — and it fails
*silently*, with no "Basemap not built" message, because the file is there and readable. This is
the single easiest way to conclude the basemap is broken when it is not; `scripts/
build_local_basemap.py`'s own `GEOFABRIK_REGIONS` note has the reasoning in full.
`great-britain` works too and is ~1.9GB of download and a much longer planetiler run.

Timings measured on an Apple Silicon laptop: Rutland (1.9MB extract) 6m13s end to end including
planetiler's own first-run download of its three auxiliary sources; Berkshire (22MB extract)
longer in proportion. The auxiliary sources are fetched once into `<output-dir>/sources` and
reused.

**Do not point `--osprey-config` at this repository's own committed `osprey.yaml` unless you mean
to rewrite it.** `register_local_provider` round-trips the file through `yaml.safe_dump`, which
preserves neither comments nor key order — the committed file's explanatory comments would be
lost. Copy it somewhere first and point `OSPREY_CONFIG_PATH` at the copy when starting the
Conduit (§3.2/§3.5), which is what the 26 September run did.

Once built and registered, the Map view renders tiles from it and shows the provider's own
credit, "© OpenMapTiles © OpenStreetMap contributors", in the bottom right. That is asserted
end to end by `apps/workspace/live/basemap.spec.ts` — see §3.8.

### 3.7 Checking the bring-up actually worked, without clicking through it

Everything above is a sequence of commands whose success is judged by eye. `make glass-live`
drives the same running stack from a browser and asserts what §4 and §6 say a presenter will
see, so a bring-up can be confirmed before an audience is watching rather than during.

```
OSPREY_TEST_LIVE_GLASS=1 \
OSPREY_LIVE_API_BASE_URL=http://127.0.0.1:8000 \
OSPREY_LIVE_BEARER_TOKEN=<the token from §2> \
OSPREY_LIVE_INVESTIGATION_ID=<the id from §3.3> \
OSPREY_LIVE_SECOND_INVESTIGATION_ID=<a second investigation, seeded with hmp> \
  make glass-live
```

**B16 and B18 (`live/scenario-b-timeline.spec.ts`) need two things the other specs do not.** The
first investigation must also be seeded with `scripts.seed_scenarios` (§3.4, the same way as the
other two) — B18's trail is the seized handset's sightings. And B16 overlays a *second*
investigation's timeline, so `OSPREY_LIVE_SECOND_INVESTIGATION_ID` names one: create it in §3.3's
step and seed `seed_hmp_fixture` under it. A second investigation with no events fails B16 by
name rather than passing on an empty track.

**Each spec creates its own investigation** and asserts its working set starts empty, so a run
never inherits state from an earlier one. That is not tidiness: the working set is server-side and
the Glass loads it on open, and the A12 case was once measured reporting green for exactly that
reason while its own expansion contributed nothing — a false positive worth remembering when
reading a result. A consequence worth knowing when demonstrating by hand: **reusing one investigation
across several attempts accumulates nodes and edges**, so if the canvas looks fuller than you
expect, open a fresh `?investigation=` rather than wondering what expanded.

It starts its own Vite server on 5173 and stops it again, so §3.6's own `npm run dev` must not
already be running on that port. **5173 is not arbitrary**: the Conduit's `CORS_ALLOWED_ORIGINS`
defaults to `http://localhost:5173`, and a Glass served from any other port has every request
refused at the browser's CORS preflight — the app then sits on "Loading…" indefinitely with
nothing in the Conduit's log naming CORS as the reason. Set `CORS_ALLOWED_ORIGINS` explicitly if
you need a different port.

Without `OSPREY_TEST_LIVE_GLASS=1` every spec skips with its reason printed, so running it with
no stack up is a skip and not a failure. These specs are not in `make ci` and are not intended to
be: they need real containers, real seeded fixtures and a real basemap build.

### 3.7a The ingest folder, and showing the Studio with a real file

**Owner ruling R6, 27 September 2026.** The Ingest Studio's Connect stage lists whatever is in the
deployment's ingest folder, so a demonstration that includes ingest needs a file in it *before*
the Studio is opened — an empty folder is a correct and very dull screen.

For a **rendered deployment** the folder is `components.storage.ingest` (default
`/var/lib/osprey/ingest`), mounted read-only into the Conduit:

```
sudo mkdir -p /var/lib/osprey/ingest
PYTHONPATH=.:packages .venv/bin/python -m scripts.seed_ingest_folder \
  --ingest-root /var/lib/osprey/ingest
```

**Corrected.** This block used to say
`sudo cp tests/scenarios/fixtures/files/*.csv …`. **That directory has never existed** — the CDR
fixture is generated (`packages/demo_fixtures/cdr.py`), not stored — so the documented step
copied nothing and left Connect listing an empty folder. Found installing from a fresh clone and
following this guide as written rather than from memory; `tests/test_seed_ingest_folder.py` is
what fails if the procedure stops working, and one of its cases asserts that directory stays
absent so the guide cannot quietly become correct by accident.

For a deployment whose ingest root is somewhere else, point the script at the rendered config and
it will read the root itself:

```
PYTHONPATH=.:packages .venv/bin/python -m scripts.seed_ingest_folder \
  --osprey-config deploy/generated/local-lite/osprey.yaml
```

For the **hand-run stack** in §3.2, the Conduit reads its own host filesystem, so point it
somewhere writable and tell it where:

```
mkdir -p /tmp/osprey-ingest && cp <your source files> /tmp/osprey-ingest/
# then add to the uvicorn command in §3.2:
OSPREY_INGEST_ROOT=/tmp/osprey-ingest
```

**Your dev token needs the Studio roles, and by default it has none of them.** Listing the folder
needs `source_author`, publishing needs `source_approver`, and running a recipe needs `loader`
(`09_INGEST_STUDIO.md` §8). `mint_dev_token` defaults to a plain analyst, which is right for every
other part of this guide and wrong for this one — the folder simply 403s, with
`principal lacks required studio role: source_author`. Mint one that can:

```
PYTHONPATH=.:packages .venv/bin/python3 -m tools.mint_dev_token \
  --jwks-path /tmp/dev-jwks/jwks.json \
  --roles analyst,source_author,source_approver,loader
```

A rendered deployment's own `--demo-analyst` subject already holds all four (`harness/realm.py`),
so this step is only for the hand-run stack.

Then, in the Glass: **Ingest Studio → Connect → "Choose file…"** and pick a file from your own
computer (it is uploaded to the deployment's `uploaded` folder and selected), or choose one already
on the server from the list beneath it. Answer the gate questions (handling — the classification may
be left blank and is then recorded as PUBLIC — legal basis, connector), and continue to Profile →
Map. The analyst never types a path (ADR-067); it is still available behind "Or type a path or
address" for an `s3://` address.

**Which connector to pick, and why it matters on screen.** The connector list is derived from the
`connectors/` directory — one validated YAML file per carrier layout, the same pattern map
providers follow (`09_INGEST_STUDIO.md` §2, ADR-016). For a CDR export pick **`cdr-generic-csv`**,
not `generic-csv`: it declares `date_order: dmy`, so `12/01/2026` is read as the twelfth of
January rather than the first of December. Both profiles will happily read the file; only one
reads the dates the way a UK carrier wrote them, and the difference does not announce itself —
the graph looks perfectly reasonable either way. That is the demonstrable point: **adding a new
carrier layout is a file, not a release.**

**Then the alert, which is the moment the demo turns from "we loaded data" into "the system told
me something".** Put the SIM's IMSI on a hotlist (`234150123456782` — the SIM still in the handset
at seizure), then ingest `seizure-record.csv` from the same ingest folder with the
`seizure-record-csv` connector. The load fires an alert naming the rule and the entity, and
**Open into investigation** branches a new working set pre-populated with the alert's entities and
linked back to where it fired.

Order matters and is worth saying out loud: create the hotlist *before* the ingest. A hotlist
watches incoming data; it does not retro-fire against what is already in the graph. Doing it the
other way round produces no alert and looks like a defect.

**After the run, search the number — this is the step that makes it a demonstration rather than a
report.** Put `+441621926368` into the search box and the `Endpoint` the load just created comes
back; add it to the working set and expand, and the calls are there. Saying out loud that the
analyst typed the *canonical* form, while the file contained four different renderings of it
(`01621926368`, `+44(0)1621926368`, `441621926368`, `#31#01621926368`), is the point of
`01_DOMAIN_MODEL.md` §7 made visible in one action.

Worth knowing if you are asked: that search once returned nothing. Search matched each entity
type's declared `identifiers` as property names — right for `Person.nino`, wrong for `Endpoint`,
whose identifier value lives in `value_normalised`. An analyst could ingest a number and then not
find it; `01_DOMAIN_MODEL.md` §7 now states which reading is authoritative.

**The whole chain runs, Connect → Profile → Map → Verify → Publish → Run.** Verify is the one to
linger on: it is a dry run that shows the graph it *would* make, plus a rejection report grouped
by cause. The fixture deliberately contains a row whose timestamp cannot be parsed, and it is
listed there by name — a demonstration that the system refuses what it cannot read rather than
guessing is worth more than one where everything is clean.

**What it does not do**: upload from the presenter's laptop through the browser. That is
deliberately post-milestone (R6). If you need a file on the deployment host, put it there the way
the block above does.

### 3.8 Shut down

```
make dev-down
```

Removes the containers **and their volumes** (`down -v`), so the next `make dev-up` starts from
empty and the fixtures need reseeding. That is usually what you want between demos.

---

## 4. The Scenario A walkthrough

The analyst-facing narrative. Full step definitions and assertions are in
`08_ACCEPTANCE_SCENARIOS.md`; this is the version to talk through while driving.

**The setting.** A fixed site — a prison — with recorded incidents, movements and associations
between people. The question is whether a pattern exists in where and when things happen, and
whether a particular subgroup is unusually insular.

1. **Seed a working set** from the fixture's person population, and expand into their associations.
   Point out that expansion previews its cardinality before running: the analyst is never
   surprised by ten thousand nodes, and a result that would exceed the working-set cap returns a
   typed error offering three ways forward rather than silently truncating.
2. **Open the timeline.** The density strip shows event counts over the period. Brush a range and
   watch the canvas and the map restrict to it. Switch to the cyclical weekday-by-hour view — this
   is where the weekend and time-of-day findings become visible, and it is the most persuasive
   single moment in the demo.
3. **Open the map.** The basemap is OpenStreetMap built locally to PMTiles — no account, no key,
   no network at run time, which is worth saying aloud to anyone who has sat through a demo that
   died on an expired API key. Attribution and licence render with the layer and travel onto
   exports.
4. **Draw a boundary filter** on the map and watch the timeline and canvas restrict. Cross-filtering
   runs in every direction: canvas, timeline, map and histograms are four views of one working set.
5. **Open the site grid.** An uploaded site image, control points, a drawn grid whose cells are real
   `Location` entities. Filter to a cell and find the hotspot.
6. **Inspect a node.** Properties, provenance, the source excerpt, and the handling marking. Make
   the point that provenance is per-element and that model-derived values sit at `inferred` until a
   human confirms them — nothing is promoted automatically, and no confidence threshold promotes on
   the analyst's behalf.
7. **Open the reports for the filtered selection** (`08`'s A6). Each report is a `Document` that
   links back to the file and the row it came from — worth showing because "where did this come
   from" is the first question anyone asks of an intelligence product, and the answer is one click
   rather than a spreadsheet lookup.
8. **Open a message document** (`08`'s B6). The message text renders with the extracted entities
   highlighted **in place**, each span drawn as `inferred` rather than asserted. Two things to say
   while it is on screen: the highlight is anchored to a character span in the *source* text, not
   to a copy of it; and a span whose node the viewer may not see is dropped from the response
   entirely rather than shown redacted, because a redacted highlight still says "something was
   found here".

   **Before this step, submit a document.** Extraction is the only part of the demo that needs the
   model tier, so it is also the only part that will not work in the first minute or two after a
   first install — the models are still being pulled (§3.7 has the check). The pinned demo model
   is a 0.5B one chosen for size and speed, not for extraction quality: it will sometimes return
   nothing from a short document, and running the extraction again is the honest thing to do in
   front of an audience rather than pretending otherwise. A 7–14B model is what
   `03_CONDUIT_MIDDLEWARE.md` §5.2 names as the production default.

7. **Rank the insular subgroup (A12).** Metrics panel → Primary metric → Clique Metric. Expand at
   least one node first: the metric measures how tightly a node's neighbours interconnect, so on
   an unexpanded single node it correctly ranks nothing.
8. **Record a judgement, and export (A13–A15).** Inspector → Judgements → "Add judgement, gap or
   assumption". Then Export ⚙. An export carrying an item the principal may not release is
   refused with every reason named — never silently dropped — and an overridable refusal takes a
   justification and an originator reference before it will resubmit.

**Corrected.** This section previously ended with "what to avoid promising: the Clique Metric [...]
is not yet built. The assessment objects, export and handling gate are not yet built either." All
of it is now built, and §1's own table had already said so — §4 was left contradicting it.
Steps 7 and 8 above are now walked by `apps/workspace/live/scenario-a-a12-a15.spec.ts` against a
real stack (an internal rehearsal log).

**What to avoid promising.** Entity resolution's threshold control and `explain` work, but
**Fixture Corp cannot be loaded into the working set at all** — see §6. Demonstrate resolution on
the HMP fixture or through the API. A13–A15's composer and export drawer open and are proven to;
submitting a judgement end to end and driving the S2 blocked-then-justified path have not been
walked through a browser.

### 4.1 Marking a node for suppression — new, and worth showing

**Owner ruling R7, 27 September 2026 — TENTATIVE**, so treat this as a preview rather than a
settled feature when describing it to an audience.

Open the radial menu on any node (`\` from the keyboard, or right-click) and choose **Mark for
suppression**. The node carries a marker afterwards; the menu item flips to **Remove suppression
mark**, and taking it off leaves nothing behind.

What to say while doing it, because it is the point of the design: **marking suppresses nothing.**
The record stays in every view, its revision does not move, and nothing is hidden from anyone. R7
makes retraction two steps precisely so that no record is ever suppressed on the strength of a
click — the suppression itself is meant to arrive as evidence through the Ingest Studio.

**What not to promise:** that second step is **not built**. A suppression today still takes effect
through the existing retract route, not through an ingested retraction record.
`06_DECISIONS.md` ADR-046's addendum records the two decisions it waits on.

---

## 5. Troubleshooting

Every item here has actually happened during this build.

**ArcadeDB is unhealthy, or the container is killed with exit 137.** Memory contention on the host's
Docker VM, recorded four times now in `deploy/compose/dev.yaml`'s own notes — under concurrent
schema DDL, under a heavy sequential fixture build, alongside Ollama's resting footprint, and under
disk exhaustion. Raising the Docker VM's memory ceiling is a host setting, not an in-repo fix. If
you are demonstrating rather than developing, stopping the `ollama`, `litellm` and `speaches`
services frees the most headroom and Scenario A does not need any of them.

**ArcadeDB will not start and the volume looks full.** Orphaned `conformance_*` databases from an
interrupted conformance run. ArcadeDB opens every database directory it finds at start-up, so dead
test databases cost start-up memory as well as disk. The conformance suite now sweeps stale ones
automatically at session start; older orphans may need clearing by hand from the volume, and the
real dev database is named `ospreyflow` — leave it alone.

**The graph has data but the timeline is empty.** Almost always the wrong `--investigation-scope`
at seed time. See §3.4.

**Connections to Postgres behave strangely.** Check nothing else on the host is listening on `5432`.
The container publishes on `5433` precisely because of this.

**The Glass loads but every request is rejected.** An expired token — the test helper's default is
five minutes. See §2.

---

## 6. Scenario C — the Enron-shaped demo — `shipped`, R24

**Built, and narrower than the Scenario C script's own planning-document description — corrected
here rather than left stale.** The Scenario C script (C1–C20) describes "Fixture
Corp" as around 150 fabricated employees, a five-level hierarchy and four departments, structural
statistics modelled on published Enron corpus research. What `scripts.seed_fixture_corp` actually
builds and `tests/scenarios/test_fixture_corp_shape.py` proves is `06_DECISIONS.md` ADR-035 §C5's
own narrower property fixture, not that corporation: **five resolution `Person` pairs** (ten nodes,
seventeen `SAME_AS` edges at descending scores, so entity resolution at τ 0.99/0.95/0.80 produces
visibly different projections), **three community-ring fraud rings** (twenty-one nodes, sixty-three
edges, for Louvain to actually find structure in), and **one path-spoke hub with eight spokes**
(lengths 1–8, exercising the pathfinder's full supported range, including a `SECRET`-classified
shortcut on the length-3 spoke for the access-control-lengthened-path property) —
**AMLSim-*shaped*, not AMLSim-generated** (neither candidate generator ADR-035 §C5 originally named
turned out to be pip-installable; `06_DECISIONS.md` ADR-035 §C5's own addendum has the full record).
Whether the ~150-employee Enron-shaped corporation the Scenario C script describes is still to be
built, and whether it replaces or sits beside this property fixture, is undecided — the property
fixture satisfies ADR-035 §C5's own minimum bar, not Scenario C's full C1–C20 script. `06_DECISIONS.md`
ADR-035 gives Fixture Corp its own distribution class (`shipped`) — it is the demo this platform
can actually put in front of a customer.

**Resolved by owner ruling R4 — Fixture Corp entities now carry a searchable
identifier.** Every `Person` has a synthetic `nino` and every `Organisation` an `org_ref`, both
deterministic from the node id, so the search box reaches them like any HMP entity. `QQ` is a
prefix HMRC never issues, so no value can collide with a real person's NINO. ADR-035 §C5's five
resolution scores were re-measured either side of the change and are bit-for-bit identical; that
addendum has the table.

**What to type.** These are stable across reseeds:

| Entity | Search for | What it is |
| --- | --- | --- |
| `corp-res-identical-1` | `QQ118439C` | One half of the pair that merges at every detent |
| `corp-res-identical-2` | `QQ843781D` | The other half — load both to explain the merge |
| `corp-path-hub` | `QQ418550B` | The eight-spoke hub, for the pathfinder |
| `corp-ring0-org` | `FIXTURE-67BD0781` | A fraud ring's shell organisation |

**The pathfinder, by keyboard.** Search one
ring member, search another, then from the canvas: `Ctrl`/`Cmd`+`Shift`+`ArrowRight` to walk to
the second node, `Space` to add it to the selection, `\` to open the menu, and "Find paths to"
is there. Two members of one ring are one hop apart. Asserted end to end by
`apps/workspace/live/fixture-corp.spec.ts`.

**`explain` on a merged cluster, by keyboard** — demonstrable, and the
order matters. Search `QQ118439C`, then `QQ843781D`, so both halves of the identical pair are in
the working set. From the canvas, `\` and pick **SAME_AS** to pull the resolution edge in — the
projection collapses over the working set's own edges, and a searched node arrives with none.
Then move the resolution slider (press `Home` for Strict; a fresh session already sits at
Balanced, so moving *to* Balanced changes nothing and computes nothing). Now `\` again and
"Explain cluster" is there, showing every gamma level, the model version, and whether the pair
meets τ.

**A claim that this fixture's resolution scores had diverged from ADR-035 §C5 was wrong and is
withdrawn** — it read each edge's `weight` (a load-time strength figure every edge carries)
instead of `properties.score`, which is the match probability resolution actually uses. All five
scores match §C5 exactly.

**The original blocker, kept for the record:** The Glass's working set has exactly one entry point — the search box —
and `services/api/search.py`'s own scope note states what that does: "exact identifier match
against the graph, not full text". `search_nodes` matches only the identifier fields the ontology
declares, which for `Person` are `nino`, `pnc_id` and `prison_number`. **None of Fixture Corp's
65 Person nodes carries any of the three, and none of its 3 Organisations carries an `org_ref`**
— measured directly against a real seeded store, against 400 of 400 for the HMP fixture, which is
precisely why HMP can be demonstrated and this cannot.

The visual query builder is not a second way in. It selects on entity type, finds them, and
reports "N node(s) matched" — but `06_DECISIONS.md` ADR-032 decided deliberately that Run returns
the set and its count rather than drawing anything, so it loads nothing into the working set.
That is the specified behaviour, not a defect in it.

So `explain` on a merged cluster, the pathfinder and path-length comparison — three of the four
interactive checks this disclosure asks for — cannot be performed at all today. Closing
this needs either a searchable identifier on the fixture (an ADR-035 §C5 fixture-shape change,
which would want checking against §C5's empirically measured resolution scores) or a way to load
a pattern result into the working set (which ADR-032 considered and decided against). Both are
design decisions; neither has been taken. Do not promise these three in a demo.

**The real Enron corpus is `internal`, and stays narrower than "usable for any demo audience."**
No real intelligence data is admitted anywhere in this repository or in CI, ever, with one narrow
exception: a real dataset is admitted only if it is explicitly named in the
local, never-committed real-data exceptions list (`scripts/real_data_exceptions.py`), and only for
local development, scale/realism testing, or an owner-run demonstration on the owner's own secured
device — never committed, never in CI, and never distributed to any attendee. ADR-035 §C3 has the
decision record and the amendment. It is the private correspondence of about 150 identifiable
people, most never charged with anything; that this exception exists at all does not lessen the
data-protection question in its own right (ADR-035 §C3 has the full GDPR/redaction/licence
reasoning, which now also covers demonstration use, not only development).

Fixture Corp gets you what makes Enron the canonical social-network case study — community
structure a real algorithm finds, and the identifier-resolution and path-length asymmetries that
betray it — with none of the real corpus's own data-protection question. That it is Enron-*shaped*
rather than Enron is a point to make in the demo, not a caveat to bury. It is not, today, the
hierarchy/departments shape the Scenario C script's own C1–C20 narrative was written against — the
property fixture and that narrative script are not yet the same thing, per the correction above.

Built following the discipline `packages/demo_fixtures/cdr.py` already set: seeded,
deterministic, in-repo, with its own shape-correctness test
(`tests/scenarios/test_fixture_corp_shape.py`) proving `06_DECISIONS.md` ADR-035 §C5's own minimum
set (τ 0.99/0.95/0.80 resolution, Louvain community structure, the pathfinder's full hop range, and
an access-control-lengthened-path case) against real adapters, not only a docstring claim.
Scenario C's own analytics-dependent steps (C9–C16, in the script's original numbering) are not
proven runnable against this fixture — the script was written for the hierarchy/departments shape,
and nobody has walked C1–C20 against what is actually built.

---

## 7. The VAST Challenge datasets — decided, `internal`

`06_DECISIONS.md` ADR-026 settles this: a VAST-2014-MC2-*shaped* fixture, built by a seeded
generator the same way `packages/demo_fixtures/cdr.py` and Fixture Corp (§6) already are — never
the published dataset's own files. The licence question (whether VAST's own files could have lived
in-repo) was checked, not assumed, and found genuinely unresolved between two distribution
channels with different apparent terms; the decision does not depend on resolving it, since a
generated fixture needs no licence at all and standing rule 3 is not amended to admit a
synthetic-but-not-generated third category. See the ADR for the full reasoning and its "revisit
if" clause.

The fixture itself is not yet built — this is a decision, not a delivered capability, the same
status Fixture Corp (§6) has. `06_DECISIONS.md` ADR-035 §C4 gives the generated fixture's own build
artefacts a distribution class (`internal`, same as Enron's development-only use) and reconfirms,
against ADR-026's own text rather than assuming it still holds, that the published VAST files
themselves are not admitted into this project in any distribution class — `internal` never means
"the actual dataset, kept private"; it means the generated, VAST-*shaped* fixture's own
intermediate build output.

---

## 8. Provisioning internal demo datasets

Applies to any demo whose distribution class (§1's table, `06_DECISIONS.md` ADR-035) is `internal`
— today, real-corpus development/scale-testing data (§6) and any intermediate build output from the
VAST-shaped generator (§7). **This section describes the mechanism only; it contains no dataset, no
download link, and no identifying detail about what an internal dataset contains** — this guide is
Apache-licensed product documentation (`06_DECISIONS.md` ADR-034 §B2) and stays that way regardless
of what any one internal demo happens to be.

**The mechanism.** Set `OSPREYFLOW_INTERNAL_DEMO_DATA_DIR` to a local directory holding whatever
internal datasets you have separately obtained the rights to use, then place each dataset at the
path its own demo's manifest names (once ADR-035's registry exists — until then, whatever path the
demo's own README/module docstring names). This directory is never `/demo-data/` inside the
repository by accident — `.gitignore` excludes exactly that path so a dataset placed there cannot be
committed even by mistake, but the environment variable has no default, precisely so an unset
variable means "nothing provisioned" rather than silently resolving to a path that might exist.

**A dataset must be admitted before it is placed.** No real dataset is admitted without an entry
in the exceptions list, independently of the mechanism above: before placing any real dataset at
its manifest path, admit it with `python -m scripts.real_data_exceptions add` (the local,
never-committed exceptions list). A dataset placed at its manifest path without a
matching admitted entry is treated exactly as an unprovisioned one — "dataset not provisioned,"
never an error, never a signal that distinguishes "not admitted" from "not placed."

**What happens if it is not set, or the file it names is absent.** The Glass renders that demo as
unavailable, with the reason "dataset not provisioned" — never an error, never a stack trace naming
a path that doesn't exist on the machine an analyst is looking at (design target; the rendering
itself is not yet built, `06_DECISIONS.md` ADR-035 §C1).

**Obtaining rights to an internal dataset is out of scope for this guide entirely.** Whether a given
dataset may be used at all — under what licence, for what purpose, under what data-protection basis
— is a decision recorded in `06_DECISIONS.md` (ADR-035 for the datasets named above), not something
this operator-facing guide adjudicates or grants.

---

## 9. Related documents

| Document | What it covers |
| --- | --- |
| `08_ACCEPTANCE_SCENARIOS.md` | The full step definitions and assertions behind §4 |
| `05_DEPLOYMENT.md` | Deployment profiles, the harness, the operator runbook |
| `09_INGEST_STUDIO.md` | The Ingest Studio's five stages, for demonstrating source onboarding |
| `06_DECISIONS.md` (ADR-035) | Demo distribution classes, the packaging gate, and each named demo's own disposition (§1, §6–8 here) |
| Developer & Operator Guide | The engineering-facing companion to this document |

> **A caveat on the Developer & Operator Guide.** It was written assuming full completion, and its
> deployment section documents a harness (`docker run ghcr.io/ospreyflow/harness:latest`,
> six setup screens) that does not exist. Do not put it in front of an external audience until that
> caveat is explicit in the document itself.
