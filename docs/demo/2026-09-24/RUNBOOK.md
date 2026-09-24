> **Superseded, 24 September 2026.** `demo_up.sh` is deleted; the scripted
> bring-up is now `python -m harness.apply --profile local-lite`
> (`06_DECISIONS.md` ADR-049 Stage 2 §3). That command renders, runs Preflight,
> builds the owned images, brings the stack up and waits on health. Its own
> remaining blockers are recorded in `07_BUILD_PLAN.md`'s Stage 2 §3 entry.

# Live-demo runbook — 23 September 2026 rehearsal

Only steps that actually passed tonight, against this checkout (`93acbe2`), are listed as runnable.
Everything else found tonight — failures, blockers, not-attempted — is in the rehearsal's own
report, not repeated here. This file is deliberately short: a runbook that overstates what is
proven is worse than no runbook.

## Setup, in order (all commands proven tonight)

```
make dev-up
docker stop compose-ollama-1 compose-litellm-1 compose-speaches-1
# drop and recreate the ospreyflow ArcadeDB database for a clean state
curl -u root:playwithdata123 -X POST http://localhost:2480/api/v1/server -d '{"command":"drop database ospreyflow"}'
curl -u root:playwithdata123 -X POST http://localhost:2480/api/v1/server -d '{"command":"create database ospreyflow"}'

PYTHONPATH=.:packages .venv/bin/python3 -m scripts.mint_dev_token --jwks-path /tmp/dev-jwks/jwks.json
python3 -m http.server 8888 --directory /tmp/dev-jwks &

# Conduit must NOT be running yet when you seed (see the rehearsal's own DuckDB-lock finding) —
# create the investigation first, note its id, THEN seed, THEN start the Conduit.
PYTHONPATH=.:packages OIDC_JWKS_URL=http://localhost:8888/jwks.json \
  .venv/bin/uvicorn services.api.app:app --host 127.0.0.1 --port 8000 &
curl -X POST http://127.0.0.1:8000/v1/investigations -H "Authorization: Bearer <token>"
# note the returned id, then:
kill %<the uvicorn job>
PYTHONPATH=.:packages .venv/bin/python3 -m scripts.seed_hmp_fixture --investigation-scope <id>
PYTHONPATH=.:packages .venv/bin/python3 -m scripts.seed_fixture_corp --investigation-scope <id>
# restart the Conduit, bound explicitly (see the localhost/IPv6 finding):
PYTHONPATH=.:packages OIDC_JWKS_URL=http://localhost:8888/jwks.json \
  .venv/bin/uvicorn services.api.app:app --host 127.0.0.1 --port 8000 &

VITE_API_BASE_URL=http://127.0.0.1:8000 VITE_DEV_BEARER_TOKEN=<token> \
  npm run dev --workspace apps/workspace &
# open http://localhost:5173 (not 127.0.0.1 — the Vite dev server is IPv6-only tonight)
```

**Before opening the Glass**, set its own investigation id in the browser (it otherwise creates a
second, empty one on load — the rehearsal's own finding):
```js
sessionStorage.setItem("ospreyflow.investigationId", "<the id you seeded>")
```
then reload.

## HMP — what is proven runnable tonight

| Step | Command / click sequence | Evidence |
| --- | --- | --- |
| Seed | `scripts.seed_hmp_fixture` above | "Seeded 400 Person nodes, 10 yards. Loaded 262 current-window events and 4 prior-period events." |
| Hotspot concentration | Open the Glass, Map view | `Hotspot cells` panel renders 10 real bins (36, 35, 35, 30, 25, 21×5); top-4 = 136/266 = 51.1%, matching `08_ACCEPTANCE_SCENARIOS.md`'s own documented figure exactly |
| Density timeline | Map view, on load | Real histogram renders across the full fixture window (2025-12-10 to 2026-03-06), sourced from the same seeded investigation |

**Everything else in Scenario A** (site image/control points, cross-filtering, temporal brush,
report view, metrics ranking, radial expansion, link analysis, Clique Metric, assessment objects,
export) **is not on this list tonight** — see the rehearsal's own report for why, step by step. The
map basemap failing to initialise (no local PMTiles built) blocks every map-dependent step; the
remaining canvas-based steps were not reached in the time available.

## Fixture Corp — what is proven runnable tonight

| Step | Command | Evidence |
| --- | --- | --- |
| Seed | `scripts.seed_fixture_corp` above | "Seeded 10 resolution Person nodes and 17 real SAME_AS edges. Seeded 21 community-ring nodes and 63 edges across 3 rings. Seeded the path-spoke hub 'corp-path-hub' with spokes of length [1..8], including a SECRET shortcut on the length-3 spoke." |

This confirms the fixture's own four required properties (`06_DECISIONS.md` ADR-035 §C5) are
structurally present at seed time. **Interactive verification through the Glass — moving the
resolution threshold live, opening `explain` on a merged cluster, running the pathfinder, comparing
two principals' own path lengths — was not completed tonight**; see the rehearsal's own report.

---

## Owner-run real-dataset demonstration — NOT RUNNABLE

Step 0 (owner-run, on the owner's own secured device, not tonight's rehearsal):

```
python -m scripts.real_data_exceptions add "Enron email corpus" \
  --use owner_run_demonstration \
  --added-by <owner> \
  --device <owner's own device> \
  --justification "..."
```
`06_DECISIONS.md` ADR-035 §C3 has the decision record this admission implements.

**Marked NOT RUNNABLE, exactly three preconditions, none satisfied tonight:**
1. No email/maildir ingest path exists — the Ingest Studio is recipe/CSV only.
2. The corpus is not provisioned (`OSPREYFLOW_INTERNAL_DEMO_DATA_DIR` unset, nothing placed at any
   manifest path).
3. The legal-advice requirement in `06_DECISIONS.md` ADR-035 §C3 is outstanding.

The ingest path is not designed here — that is real, separately-scoped work, not tonight's.

---

## 24 September 2026 continuation — overnight round, Stage 3a exit criterion

Owner cancelled the day's demonstration; dev stack and seeded data were free to use. This section
follows the same discipline as the section above: only what was actually run and observed, against
`docs/demo/2026-09-24/demo_up.sh --reset` from a fresh clone of the repository, not the checkout
that made the fixes.

### Product defects fixed, both with tests (see `07_BUILD_PLAN.md`'s own addendum for the full record)

1. The Glass ignoring a seeded investigation — fixed with a `?investigation=<id>` URL parameter,
   precedence over `sessionStorage`.
2. The `file://` basemap source a browser cannot fetch — fixed with a new Conduit route serving it
   over HTTP with Range support, and a "Basemap not built" message in place of a blank canvas when
   the file is absent.

### `demo_up.sh --reset`, from a fresh clone, against the real stack

**Reached READY.** Full log kept in this session's own transcript, not duplicated here; the summary
block it printed:

```
 Glass:          http://localhost:5173/?investigation=01M38XAJ4C7M1W8KTE285WJ2EG
 Investigation:  01M38XAJ4C7M1W8KTE285WJ2EG
```

Seed output, unedited: `Seeded 400 Person nodes, 10 yards. Loaded 262 current-window events and 4
prior-period events.` / `Seeded 10 resolution Person nodes and 17 real SAME_AS edges. Seeded 21
community-ring nodes and 63 edges across 3 rings. Seeded the path-spoke hub 'corp-path-hub' with
spokes of length [1..8], including a SECRET shortcut on the length-3 spoke.` — identical to
tonight's earlier rehearsal, confirming the fixture generators are still deterministic.

**One real operational finding, self-inflicted and disclosed rather than hidden:** the first
attempt at this run collided with a `make test-all` run this same session had left going against
the same ArcadeDB container — the seed step failed with `Error in execution in lock`, and the
concurrent test run's own results (34 failures in `tests/conformance/graph_port/test_suite.py`
alone, plus failures across `tests/ingest`, `tests/golden`, several `tests/scenarios/*`) were
discarded as unmeasurable, not reported as regressions — exactly the contamination `CLAUDE.md` rule
14 names, caused here by one session running two things at once rather than two separate agents.
The orphaned JWKS `http.server` this left behind was killed, and the run was repeated with nothing
else touching the stack; the second attempt is the one reported above and below.

### Scenario A / Fixture Corp, through a real browser (Playwright), from the fresh-clone's own Glass

| Step | Result | Evidence |
| --- | --- | --- |
| Load `?investigation=<seeded id>` | **PASS** — `sessionStorage["ospreyflow.investigationId"]` reads back the URL-supplied id; case banner shows the right id | `A0-glass-loaded-with-seeded-investigation.png` |
| Density timeline renders real data | **PASS** — same shape as tonight's earlier rehearsal | `A0-glass-loaded-with-seeded-investigation.png` |
| Map view, basemap absent | **PASS (the fix, not the basemap itself)** — "Basemap not built" with the route's own detail message, no blank canvas, no stack trace | `A2-map-basemap-not-built-message.png` |
| Hotspot cells panel | **PASS** — 10 real bins render alongside the basemap-not-built message, unaffected by the map's own failure | `A2-map-basemap-not-built-message.png` |
| Global search for a Fixture Corp entity (`corp-path-hub`) | **NOT REACHED** — typed into the search box, no dropdown observed within the time spent; not pursued further this round | `FixtureCorp-search-path-hub.png` |
| A1 site image/control points/grid, A3–A15, Fixture Corp's own resolution-threshold/`explain`/pathfinder steps | **NOT REACHED** — browser automation time was spent proving the two fixes rather than the full walkthrough; `07_BUILD_PLAN.md`'s own addendum records this honestly as "not yet fully walked through a browser," not as demonstrated | — |

**What this round proves and does not prove.** It proves both product defects are real, both fixes
work against a live stack from a fresh clone, and the scripted bring-up reaches `READY` unattended.
It does not prove the rest of Scenario A or Fixture Corp's own interactive properties work through
the Glass — that remains open, named here and in `07_BUILD_PLAN.md` rather than assumed from the
two fixes above.

### `make test-all`, full suite before and after — one more real finding, reinforcing this guide's own §5

`make test-all` (`tests/conformance/graph_port` onward, 293 collected items) could not be run in one
pass tonight: ArcadeDB hit `java.lang.OutOfMemoryError: Java heap space` partway through and went
`unhealthy`, three separate times, the third time even with `ollama`/`litellm`/`speaches` already
stopped — this section's own §5 entry ("ArcadeDB is unhealthy... under a heavy sequential fixture
build") already names the mechanism; tonight is a fresh, reproducible data point for an
already-disclosed fragility, not a new one. Worked around, not fixed, by splitting the run at
`tests/services/api/test_prefetch.py` (roughly where each attempt died) with an ArcadeDB restart
and an orphaned-`conformance_*`-database sweep between the two halves — no code or Makefile change,
a testing-methodology accommodation only. Result, both halves clean: **287 passed, 6 failed**
(`tests/conformance/model_port` ×4, `tests/golden/test_golden_set.py`,
`tests/scenarios/test_witness_statement_extraction.py` — exactly Floor B's own set, minus
`test_phase6_extraction_and_resolution.py`, which `make test-all`'s own target does not include),
plus `npm run test:integration` at 3/3. No new failure anywhere — the earlier, single-pass attempts'
own extra failures (dozens of `F`s across `tests/conformance/graph_port`, `tests/ingest`, several
`tests/scenarios/*`) were the OOM's own contamination, confirmed by the fact that every one of those
suites passed clean once ArcadeDB was healthy again, and discarded rather than reported, per
`CLAUDE.md` rule 14's own "a measurement taken under unknown contention is not a measurement of the
thing it claims to measure."
