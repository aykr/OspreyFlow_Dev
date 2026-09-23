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
