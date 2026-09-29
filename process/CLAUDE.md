# OspreyFlow

Open-source intelligence analysis and network discovery platform. Three tiers — the Glass
(React workspace), the Conduit (FastAPI orchestration), the Vault (graph store, analytics,
models) — separated by four typed ports.

## The specification is in `spec/` and it is binding

`spec/` holds the full architecture pack; `process/` holds the build record. Read what the
current task needs; do not read all of it every session.

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

All decision records in `spec/06_DECISIONS.md` are accepted. If you believe one is wrong, say so
and stop — do not implement an alternative and explain afterwards.

`spec/` is the source of truth for the specification. When a correction to a doc arrives as a
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
9. **Fixtures are synthetic and in-repo.** No real intelligence data anywhere, in this repository
   or in CI, ever — with one narrow exception: a dataset the owner has explicitly named in the
   local, never-committed real-data exceptions list (`scripts/real_data_exceptions.py` —
   `config/real_data_exceptions.yaml`, gitignored; `06_DECISIONS.md` ADR-035 §C3 has the decision
   record), admitted only for local development, scale/realism testing, or an owner-run
   demonstration on the owner's own secured device — never committed, never in CI, never
   distributed to an attendee. No other real dataset is admitted without its own such entry. Map
   data in the demo and CI is tier 1 only.
10. **The performance budget in `spec/02_GLASS_FRONTEND.md` §5 is a CI gate**, not a target.
11. **A genuine spec gap gets fixed in the spec, not answered in chat.** An answer given only in
    conversation is lost by the next session — if `spec/` is ambiguous or silent on something
    needed, the fix is an edit to `spec/` (an ADR, if it is a real decision), not a reply.
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
    recorded (`process/07_BUILD_PLAN.md`'s Phase 8 "ArcadeDB stability" stage, before its 23 September
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
15. **A gate's first green is not a result, it is an untested state. A new gate is not wired into
    `make ci` until it has been shown red.** Worked example, 23 September 2026:
    `scripts/decision_log_publication_check.py` was built, given a fixture test, and reported
    "0 violations" against the real decision log — accepted and recorded as a finding without
    first confirming the comparison itself worked. It didn't: the regex extracting a cited ADR
    number captured two digits after `ADR-0`, compared against a three-digit classification key
    (`"34" != "034"`), so every comparison silently failed regardless of the document's actual
    content. The fixture test itself later caught this before the gate shipped — but the "0
    violations, checked directly" claim had already been written down and trusted in the interim,
    exactly the failure rule 12 names: an invariant stated in prose, exercised by a check that
    could not have found a violation if one existed. A full project audit afterwards found every
    other gate already followed this discipline (`CLAUDE.md` rule 12's own "name the test" habit,
    applied as a `test_the_check_fails_for_X`/`test_X_is_flagged` case built alongside each gate)
    — except one: the Node half of `make licence-check` (`scripts/licence_check.mjs`) had run in
    CI since Phase 0 with no test at all, its own `isAllowed` predicate never shown red. **Before
    trusting or citing a gate's own "0 violations"/"all pass" result, confirm that gate has an
    on-record red-then-green demonstration — a test that plants a real violation and asserts the
    gate reports it — not merely that the gate currently reports none.** Before wiring a new gate
    into `make ci`, that demonstration is what "the gate is ready" means; a gate that has only ever
    been run against content it happens to pass has not been tested, only exercised.

    **An injection that any default-deny fallthrough would have caught proves nothing about the
    specific branch it was meant to exercise.** Found building `licence_check.mjs`'s own first
    red-then-green proof, the same day as the worked example above: the first attempt removed the
    GPL-rejection branch from `isAllowed` and asserted a bare `"GPL-3.0"` string was still
    rejected — it was, because `isAllowed`'s own fallthrough (`ALLOWED_MARKERS.some(...)`) already
    rejects any string matching no allowlisted marker, with or without the branch under test. The
    real risk only appeared testing the shape `main()` actually produces at its own call site
    (`licenses.join(" AND ")` for a dual-licensed package): with the branch removed,
    `isAllowed("MIT AND GPL-3.0")` returned `true`, since `"mit"` alone satisfied the fallthrough.
    **The planted violation must take the shape the code under test actually emits or receives at
    its own real call site, not a convenient hand-written approximation of it** — a bare string
    that happens to fail by a different path proves the test can fail, but not that it fails for
    the reason it claims to.

    **Second worked example, 24 September 2026 — a fixture that accepts what the real dependency
    rejects cannot show a gate red for that defect, and hides it instead.** ADR-043's OAuth2 Token
    Exchange was recorded "built" on 22 September and stayed that way for two days while **never
    once having worked against a real identity provider**. The request omitted `subject_token`,
    which RFC 8693 §2.1 makes REQUIRED; a real Keycloak refuses it outright (`access_denied`,
    "Client not allowed to exchange") and grants the identical request with the field present —
    measured both ways. Every test passed throughout, because the only thing that code had ever run
    against was the ephemeral HTTP fixture ADR-043's own Cost section describes, and that fixture
    happily accepted a request the real server rejects. Nothing was mis-implemented against its own
    tests; the tests measured something more permissive than the dependency. ADR-043 had even
    warned that its fixture "does not and cannot prove a real deployed Keycloak realm is correctly
    configured" — the warning was narrower than the problem, which was in the request this codebase
    sends, not in anyone's realm.

    **So: a fixture standing in for an external dependency models that dependency's *refusals*, not
    only its grants.** A fixture built only from the happy path is a specification of what we hope
    the dependency accepts, and a test against it proves the code agrees with our hopes. Before
    trusting one, ask which requests the real dependency rejects and make the fixture reject them
    too — and where the answer is not known, that is itself the finding, because it means nobody
    has run the code against the real thing. The same question applies to a fake standing in for a
    store, a queue or an IdP: **what does the real one refuse, and does the fake refuse it?**

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
    this conversation, a prior message, another file's import, or one of `spec/*.md`'s own file
    references. A direct `Read` of that file is faster and more precise than a BFS neighbourhood
    around it; this is the case the live test above actually measured.
- `graphify-out/wiki/index.md` exists — use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain
  do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
