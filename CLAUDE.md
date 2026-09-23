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

All decision records in `docs/06_DECISIONS.md` are accepted. If you believe one is wrong, say so
and stop — do not implement an alternative and explain afterwards.

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
11. **A genuine spec gap gets fixed in the spec, not answered in chat.** An answer given only in
    conversation is lost by the next session — if `docs/` is ambiguous or silent on something
    needed, the fix is an edit to `docs/` (an ADR, if it is a real decision), not a reply.
12. **When a spec sentence states an invariant, ask which test would fail if it were violated.**
    `upsert_edges` never merged same-pair edges for a whole phase while the conformance suite
    passed, because no case wrote the same pair twice — the invariant was stated in prose and
    exercised by nothing. The same failure has recurred since: a keyboard-navigation CI gate that
    proves a menu opens but not that an item in it activates; a fake test double that proves a
    pure function's logic but not the access control its real caller depends on. Naming the test
    is part of stating the invariant, not a follow-up.
13. **A canvas or workspace action is not reachable-by-keyboard until `keyboard.spec.ts` (or its
    equivalent for a new surface) has a case proving it end to end.** Confirmed directly: that
    walkthrough is hardcoded, with no auto-discovery of new actions, so Phase 4's own exit
    criterion ("keyboard navigation reaches every canvas action") is enforced by a test that
    cannot detect its own violation. A new action's own author owns adding its own step in the
    same change, the same way rule 4 already makes an access-control test the author's
    responsibility rather than a follow-up.
14. **One agent against this working tree and its local dev stack (`make dev-up`) at a time.** A
    subagent that has handed back its report is not necessarily finished — it can keep running,
    keep committing, and keep pushing in the background, and a second agent (the coordinator that
    spawned it, or a person) resuming or continuing work against the same tree and the same
    containers has no way to see that it is happening. Worked example, 23 September 2026: a
    delegated agent handed back a completed report on Phase 8's closing-pass test, and the
    coordinator began independent verification against the same `make dev-up` stack. The delegated
    agent was still alive in the background; it went on to make and push four further commits of
    its own, and separately kept re-running the same test against the same shared ArcadeDB
    container the coordinator was debugging. The result: a reliability figure the delegated agent
    recorded (`docs/07_BUILD_PLAN.md`'s Phase 8 "ArcadeDB stability" stage, before its 23 September
    correction) was contaminated by unknown contention and had to be withdrawn as unmeasurable
    after the fact; a real, finished deliverable (the closing-pass test file itself) sat uncommitted
    for over an hour past its own four commits' claim that it existed and passed; the coordinator
    spent real effort re-diagnosing environment failures that were, in unknown part, two agents
    fighting over one container rather than a property of the container alone; and the coordinator
    initially — reasonably, from the evidence available at the time, but wrongly — read the
    delegated agent's own unreviewed pushes as a stranger's unauthorised commits to `origin/main`.
    **Before resuming or continuing work that touches a shared working tree or a shared local
    stack, confirm no other agent is still active against it** (`ListAgents`, and treat "handed
    back a report" as distinct from "stopped running" for any agent whose task can keep going in
    the background). Before trusting a reliability or timing measurement taken against `make
    dev-up`'s shared containers, confirm nothing else was using them for the duration of the
    measurement — a measurement taken under unknown contention is not a measurement of the thing
    it claims to measure.

## Conventions

- Python 3.12, FastAPI, async throughout. Pydantic models in `packages/schemas` are the source
  of truth; TypeScript types are generated from them and drift is a build failure.
- TypeScript strict. React 18 + Vite. Zustand for the working set.
- Ports are `Protocol` classes in `packages/ports`. Adapters live in `packages/adapters/<name>`.
- British English in code comments, documentation and all user-facing copy.
- Conventional Commits.
- No `osprey` CLI yet. Operational work (seeding a fixture, minting a dev token, reverting a
  load, building the local basemap) is a plain, directly-runnable module under `scripts/`, run as
  `python -m scripts.<name>` — the shape an eventual CLI subcommand would wrap, not a shortcut
  around one.

## Before you write code

State which spec sections you are working from and what you are about to change. If the spec is
silent on something you need, say so and propose — do not fill the gap silently. Undocumented
assumptions are where this build will go wrong.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

**Narrowed 19 September 2026** (`07_BUILD_PLAN.md`'s "Gaps with no owning phase" has the full
finding): the version of this section below that said "first run `graphify query` for codebase
questions" had a measured zero compliance rate across the whole of Phase 6a, and a live test of
that wording — run in response to being asked, not before — found it was also wrong often enough
to explain why: a targeted question about a file already identified returned a 197-node BFS
neighbourhood full of unrelated files, where a direct `Read` found the real answer faster. The
rule below is the corrected scope, not the original one.

Rules:
- **Reach for `graphify query "<question>"` / `graphify path "<A>" "<B>"` / `graphify explain
  "<concept>"` for a broad "how does X relate to Y" question, or orientation in an area of the
  codebase you have not yet read anything in.** These return a scoped subgraph, usually much
  smaller than `GRAPH_REPORT.md` or raw grep output, specifically because they are built for
  "where do I even start" — not for "what does this function I already found do."
  - **Do not reach for a query when you already know which file to look at** — a path named in
    this conversation, a prior message, another file's import, or one of `docs/*.md`'s own file
    references. A direct `Read` of that file is faster and more precise than a BFS neighbourhood
    around it; this is the case the live test above actually measured.
- `graphify-out/wiki/index.md` exists — use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain
  do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
