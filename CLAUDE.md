# OspreyFlow

Open-source intelligence analysis and network discovery platform. Three tiers — the Glass
(React workspace), the Conduit (FastAPI orchestration), the Vault (graph store, analytics,
models) — separated by four typed ports.

## The specification is in `docs/` and it is binding

`docs/` holds the full architecture pack. Read what the current task needs; do not read all of
it every session.

| Read this | When |
| --- | --- |
| `docs/00_ARCHITECTURE.md` | Ports, tiers, geospatial providers, licence register |
| `docs/01_DOMAIN_MODEL.md` | Anything touching entities, edges, provenance, handling, resolution |
| `docs/02_GLASS_FRONTEND.md` | Anything in `apps/workspace` |
| `docs/03_CONDUIT_MIDDLEWARE.md` | Anything in `services/api` |
| `docs/04_VAULT_BACKEND.md` | Adapters, engines, conformance suites |
| `docs/05_DEPLOYMENT.md` | Harness, profiles, containers |
| `docs/06_DECISIONS.md` | Before proposing any alternative to what the spec says |
| `docs/07_BUILD_PLAN.md` | Phase scope and exit criteria |
| `docs/08_ACCEPTANCE_SCENARIOS.md` | The functional definition of done |
| `docs/09_INGEST_STUDIO.md` | Ingest, connectors, mapping, review queue |
| `docs/design/tokens.css` | Any styling. Authoritative — no colour outside these tokens |

All eighteen decision records in `docs/06_DECISIONS.md` are accepted. If you believe one is
wrong, say so and stop — do not implement an alternative and explain afterwards.

`docs/` is the source of truth for the specification. When a correction to a doc arrives as a
whole replacement file, diff it against the working copy before applying it, and reject any hunk
outside the stated scope of the change — a correction to one section must not revert another.

## Rules that hold in every session

1. **Conformance suites are written before adapters.** The suite defines the contract.
2. **Never truncate a result silently.** The working set cap returns a typed `limit_exceeded`
   error with three options. A bare slice near the working set is a defect.
3. **Access control lives in the adapter**, injected into the traversal or the `WHERE` clause —
   never applied in the Conduit after retrieval. An unauthorised principal must not be able to
   detect a filtered node's existence via path length, degree count or histogram bucket.
4. **Every read path gets an access-control test.** No exceptions for internal endpoints.
5. **Model-derived data is `inferred` until a human confirms it.** No automatic promotion, no
   confidence threshold that promotes on the analyst's behalf.
6. **Entities are never merged in storage.** Resolution writes scored `SAME_AS` edges and
   collapses them at query time.
7. **The Glass never sees Gremlin**, a source-system identifier, or an unfiltered count.
8. **No expression or scripting language in the Ingest Studio.** Transforms are Knowledge
   Adapters with golden test files.
9. **Fixtures are synthetic and in-repo.** No real intelligence data anywhere, ever. Map data in
   the demo and CI is tier 1 only.
10. **The performance budget in `docs/02_GLASS_FRONTEND.md` §5 is a CI gate**, not a target.

## Conventions

- Python 3.12, FastAPI, async throughout. Pydantic models in `packages/schemas` are the source
  of truth; TypeScript types are generated from them and drift is a build failure.
- TypeScript strict. React 18 + Vite. Zustand for the working set.
- Ports are `Protocol` classes in `packages/ports`. Adapters live in `packages/adapters/<name>`.
- British English in code comments, documentation and all user-facing copy.
- Conventional Commits.

## Before you write code

State which spec sections you are working from and what you are about to change. If the spec is
silent on something you need, say so and propose — do not fill the gap silently. Undocumented
assumptions are where this build will go wrong.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
