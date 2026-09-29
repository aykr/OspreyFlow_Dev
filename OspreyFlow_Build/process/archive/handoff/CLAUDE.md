# OspreyFlow

Open-source intelligence analysis and network discovery platform. Three tiers — the Glass
(React workspace), the Conduit (FastAPI orchestration), the Vault (graph store, analytics,
models) — separated by four typed ports.

## The specification is in `docs/` and it is binding

`docs/` holds the full architecture pack. Read what the current task needs; do not read all of
it every session.

| Read this | When |
| --- | --- |
| `spec/00_ARCHITECTURE.md` | Ports, tiers, geospatial providers, licence register |
| `spec/01_DOMAIN_MODEL.md` | Anything touching entities, edges, provenance, handling, resolution |
| `spec/02_GLASS_FRONTEND.md` | Anything in `apps/workspace` |
| `spec/03_CONDUIT_MIDDLEWARE.md` | Anything in `services/api` |
| `spec/04_VAULT_BACKEND.md` | Adapters, engines, conformance suites |
| `spec/05_DEPLOYMENT.md` | Harness, profiles, containers |
| `spec/06_DECISIONS.md` | Before proposing any alternative to what the spec says |
| `process/07_BUILD_PLAN.md` | Phase scope and exit criteria |
| `spec/08_ACCEPTANCE_SCENARIOS.md` | The functional definition of done |
| `spec/09_INGEST_STUDIO.md` | Ingest, connectors, mapping, review queue |
| `spec/design/tokens.css` | Any styling. Authoritative — no colour outside these tokens |

All eighteen decision records in `spec/06_DECISIONS.md` are accepted. If you believe one is
wrong, say so and stop — do not implement an alternative and explain afterwards.

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
10. **The performance budget in `spec/02_GLASS_FRONTEND.md` §5 is a CI gate**, not a target.

## If a knowledge-graph index is available

A graph index over `docs/` and the codebase may be present. Use it to find things and to
understand how parts connect. Do not use it to decide things: when a specification section or a
decision record governs what you are about to build, read the actual file. An index can be
stale; `docs/` is the source of truth. Cite the document and section, never the index.

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
