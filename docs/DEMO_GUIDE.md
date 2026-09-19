# OspreyFlow — demo and analyst walkthrough guide

How to get a running OspreyFlow in front of an analyst, and what to show them once it is there.

Written 18 September 2026, at the close of Phase 6. **This guide documents only what is built and
verified today.** Where a demo case is planned but not built, it says so rather than describing it
as though it works — the failure mode this project has already recorded twice in its own
documentation.

Every command below was checked against the repository rather than transcribed from the
specification. Where a step is known to be missing, it is called out as a gap, not written as an
instruction that will fail.

---

## 1. What you can demo today

| Demo case | State | What it shows |
| --- | --- | --- |
| **Scenario A, steps A1–A11** (HMP fixture) | **Built and exit-verified** | Timeline, map, cross-filtering, boundary and site-grid filters, the weekend and time-of-day findings, the site hotspot |
| **The Ingest Studio**, Connect → Publish (CDR fixture) | **Built and exit-verified** | Onboarding a new source without touching the ontology: profiling, row-template mapping, dry-run verify, publish with versioning |
| Scenario A, A12 | Not built — needs Phase 7's Clique Metric | — |
| Scenario A, A13–A15 | Not built — needs Phase 8's assessment and export | — |
| Scenario B (comms and identity pivot) | Partly built; split across Phases 6a, 7 and 8 by ADR-022 | — |
| **Extraction and entity resolution** | Built, **API only** | Demonstrable to engineers through the API; there are no screens until Phase 6a |
| **Scenario C — "Fixture Corp"** (Enron-shaped) | **Script written, fixture never built** | See §6 |
| **VAST Challenge dataset** | **Not decided** — needs an ADR first | See §7 |

The honest summary: **Scenario A on the HMP fixture is the demo that exists**, and it is a good
one. It exercises three of the five analytical capabilities against a live stack.

---

## 2. Before you start: minting a token and a JWKS fixture

The Conduit validates JWTs against a JWKS URL (`OIDC_JWKS_URL`, read with no default in
`services/api/config.py` — the service will not start without it, and only accepts an `http`/
`https` URL, never a bare file path). The Glass sends a bearer token from `VITE_DEV_BEARER_TOKEN`.
`scripts/mint_dev_token.py` wraps `tests/conftest.py`'s own signing logic (`sign_token`,
`default_claims`) the same way `scripts/seed_hmp_fixture.py` already wraps a test fixture — the
correction already made three times for `revert_load`, the local-basemap build and the HMP seed.

```
PYTHONPATH=.:packages python -m scripts.mint_dev_token --jwks-path /tmp/dev-jwks/jwks.json
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

### 3.1 Start the backing stores

```
make dev-up
```

Brings up ArcadeDB, MinIO, Valkey, Postgres, Ollama, LiteLLM and speaches, and blocks until every
health check passes. Published ports: ArcadeDB `2480`, MinIO `9000` and `9001`, Valkey `6379`,
Postgres `5433` (mapped from the container's `5432`), Ollama `11434`, LiteLLM `4000`, speaches
`8001`.

> **Postgres is on 5433 deliberately.** A native macOS Postgres on the host's `5432` once
> intercepted connections meant for the container and cost a session to diagnose. Do not remap it
> back.

### 3.2 Start the Conduit

`services/api` is **not** in the dev compose file, so it runs by hand:

```
PYTHONPATH=.:packages OIDC_JWKS_URL=http://localhost:8888/jwks.json \
  uvicorn services.api.app:app --port 8000
```

(the URL is whatever §2's `mint_dev_token`/`http.server` pair actually served — this is the
common local case, not a fixed value)

`PYTHONPATH` must include both the repository root and `packages/` — neither a bare `python -m`
nor `uvicorn` puts them on `sys.path`, which is why `services/api/Dockerfile` sets it explicitly.

Other settings default sensibly for local use and are all read from the environment
(`services/api/config.py`): `VALKEY_HOST`/`VALKEY_PORT`, `POSTGRES_HOST`/`POSTGRES_PORT`/
`POSTGRES_USER`/`POSTGRES_DB`, `ANALYTICS_DB_PATH` (default `data/analytics.duckdb`),
`OSPREY_CONFIG_PATH` (default `osprey.yaml`).

### 3.3 Create an investigation and note its id

```
POST /v1/investigations
```

with your bearer token. **Keep the id it returns** — the seeding step needs it. If you create the
investigation from the Glass instead, the id is in the browser's
`sessionStorage["ospreyflow.investigationId"]`.

### 3.4 Seed the HMP fixture

```
PYTHONPATH=.:packages python -m scripts.seed_hmp_fixture \
  --investigation-scope <the id from 3.3>
```

`--investigation-scope` is required and deliberately not defaulted. Every automated HMP test seeds
under its own constant scope, which is fine inside a test process; a live demo needs the events
tagged with the investigation id the running Glass session is actually using, because
`EventFilter.investigation_scope` is what every `/v1/analytics/*` route filters on. **Pass the
wrong scope and you will seed data that no query in your session can see** — the graph will look
populated and the timeline will be empty.

Optional arguments, all with environment fallbacks: `--analytics-db-path` (default
`data/analytics.duckdb`), `--principal-id` (default `hmp-seed-worker`), `--clearance` (default
`OFFICIAL`), `--org-unit` (default `unit-1`).

The script writes to both stores a real Conduit reads from — `build_hmp_graph` against the same
ArcadeDB, and `AnalyticsPort.load_events` against the same DuckDB file. It is not a bypass of
either.

### 3.5 Start the Glass

```
VITE_API_BASE_URL=http://localhost:8000 \
VITE_DEV_BEARER_TOKEN=<the token scripts/mint_dev_token.py printed in §2> \
  npm run dev --workspace apps/workspace
```

Then open `http://localhost:5173`. Both variables have defaults — the API base URL falls back to
`http://localhost:8000`, the token to an empty string — so in the common local case only the token
strictly needs setting.

### 3.6 Shut down

```
make dev-down
```

Removes the containers **and their volumes** (`down -v`), so the next `make dev-up` starts from
empty and the fixture needs reseeding. That is usually what you want between demos.

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

**What to avoid promising.** The Clique Metric that ranks the insular subgroup is Phase 7. The
assessment objects, export and handling gate are Phase 8. Entity resolution works but has no
screens until Phase 6a, so it demonstrates through the API or not at all.

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

## 6. Scenario C — the Enron-shaped demo (not yet built)

**The fixture does not exist.** The Scenario C script is a planning document; "Fixture Corp" — around
150 fabricated employees, a five-level hierarchy, four departments, structural statistics modelled
on published Enron corpus research — has never been built as a fixture.

**The real Enron corpus cannot be used, and does not need to be.** `CLAUDE.md` rule 9 is
unqualified: "No real intelligence data anywhere, ever." Standing rule 3 names the demo explicitly:
"No real intelligence data in the repository, in CI, or in a demo." The corpus is the private
correspondence of about 150 identifiable people, most never charged with anything, and loading it
into an intelligence platform to demonstrate network analysis is precisely the thing that rule
prevents — quite apart from being a data-protection problem in its own right.

Fixture Corp gets you what makes Enron the canonical social-network case study — the hierarchy, the
community structure, the communication asymmetries that betray it — with none of that. That it is
Enron-*shaped* rather than Enron is a point to make in the demo, not a caveat to bury.

Building it depends on nothing in Phase 7, because fixtures are synthetic and in-repo by standing
rule 3. It can start now, and if it does, Scenario C's analytics-dependent steps C9–C16 are runnable
the day Phase 7 closes rather than starting then. Follow the discipline `tests/scenarios/fixtures/
cdr.py` already sets: seeded, deterministic, in-repo, with its own shape-correctness test.

---

## 7. The VAST Challenge datasets — decided

`06_DECISIONS.md` ADR-026 settles this: a VAST-2014-MC2-*shaped* fixture, built by a seeded
generator the same way `tests/scenarios/fixtures/cdr.py` and Fixture Corp (§6) already are — never
the published dataset's own files. The licence question (whether VAST's own files could have lived
in-repo) was checked, not assumed, and found genuinely unresolved between two distribution
channels with different apparent terms; the decision does not depend on resolving it, since a
generated fixture needs no licence at all and standing rule 3 is not amended to admit a
synthetic-but-not-generated third category. See the ADR for the full reasoning and its "revisit
if" clause.

The fixture itself is not yet built — this is a decision, not a delivered capability, the same
status Fixture Corp (§6) has.

---

## 8. Related documents

| Document | What it covers |
| --- | --- |
| `08_ACCEPTANCE_SCENARIOS.md` | The full step definitions and assertions behind §4 |
| `05_DEPLOYMENT.md` | Deployment profiles, the harness, the operator runbook |
| `09_INGEST_STUDIO.md` | The Ingest Studio's five stages, for demonstrating source onboarding |
| `07_BUILD_PLAN.md` | What is built, what is not, and each phase's known gaps |
| Developer & Operator Guide | The engineering-facing companion to this document |

> **A caveat on the Developer & Operator Guide.** It was written assuming full completion, and its
> deployment section documents a Phase 8 harness (`docker run ghcr.io/ospreyflow/harness:latest`,
> six setup screens) that does not exist. Do not put it in front of an external audience until that
> caveat is explicit in the document itself.
