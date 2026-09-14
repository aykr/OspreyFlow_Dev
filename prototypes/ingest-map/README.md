# Ingest Studio — Map screen prototype

**This is disposable. It is not the production Glass, it is not built on `apps/workspace`, and
nothing here is expected to survive into Phase 5a.** It exists only so an analyst can react to
the row-template mapping concept (`09_INGEST_STUDIO.md` §4, ADR-018) before the real studio is
built, per ADR-018's own reasoning: *"prototype the Map screen before Phase 5a rather than
during it... finding out then that the row template should be a tree costs a week; finding out
during Phase 5a costs the phase."*

## What it is

A static HTML/JS page (no framework, no build step) rendering the three-pane layout sketched in
`09_INGEST_STUDIO.md` §4 — source fields, the row template as a small graph, and an inspector —
over **real** data: the actual `cdr-fixture` recipe
(`tests/scenarios/fixtures/cdr_recipe.yaml`) resolved against the actual synthetic CDR fixture
(`tests/scenarios/fixtures/cdr.py`) by the actual headless recipe engine
(`services/ingest/engine.py`), not mocked-up JSON shaped to look convincing.

`generate_data.py` calls `resolve_rows` — the same function `run_recipe` calls — and writes what
it returns to `data.json`, which the page reads by `fetch`. Every entity, edge, property binding,
duplicate collapse and rejection reason shown is what the pipeline actually produced for that row.

## Running it

Regenerate the data (only needed if the recipe or fixture changes — `data.json` is committed so
the page works without a Python environment):

```
PYTHONPATH=packages python3 prototypes/ingest-map/generate_data.py
```

Serve the directory statically (needed because `fetch` of a local file is blocked by the
browser's own-origin rules for `file://`):

```
python3 -m http.server --directory prototypes/ingest-map 8008
```

Then open `http://localhost:8008/`.

## What to look for, and what not to conclude

Per ADR-018, only the **structural** decisions (recipe is versioned YAML, one record maps to a
graph not a flat form, POLE-first typing, transforms are Knowledge Adapters with no expression
language) are settled. Everything about *how this looks* — three panes vs. something else, a
canvas vs. a tree, click vs. drag-to-bind — is explicitly free to change after this is reviewed,
and this prototype's specific choices (click-only selection, no editing, no drag-and-drop) are
not a recommendation, only what was cheapest to build to make the row-template *concept*
inspectable.

## What it does not do

- No editing. The recipe is read-only; there is no save path.
- No drag-to-bind, no keyboard binding path — `09_INGEST_STUDIO.md` §4 describes both as the
  eventual studio's interaction model, but proving the row-template concept doesn't need them.
- No profiler, no verify/publish stages, no unstructured-source path.
- No connection to a live ArcadeDB or MinIO — it reads a static, pre-generated `data.json`.
