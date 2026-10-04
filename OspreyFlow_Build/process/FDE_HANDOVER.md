# OspreyFlow — Handover to a Claude Code session working directly in the repository

Written 4 October 2026, for Ayan. This file supersedes `SESSION_HANDOVER.md` (18 September 2026, written for
the maker–checker arrangement) as the place a new session starts. It adds to `process/CLAUDE.md`
(rules 1 to 15, which bind) and does not repeat it. Where this file and the code disagree, the code is the
evidence and this file is wrong; say so and fix the file.

## 1. How the owner works with you

- **Role.** Forward-deployed engineer on OspreyFlow, in owner-present mode. The owner is Ayan, Education
  Estates Directorate, Solirius Reply. He tests the product by hand and reports what he sees, usually with
  screenshots; he rules on milestone-level design questions and finds detailed ones hard to judge until the
  product runs.
- **Explain before you fix.** For a defect, say in plain terms what is wrong and why before changing anything.
- **A defect is fixed at the class, not the instance.** Write the failing test first and show it red; fix the
  class of fault; correct the spec in the same commit (rule 11); run the touched tests and lint; add a row to
  the friction log in `OspreyFlow_Build/process/07_BUILD_PLAN.md` ending "Hash: recorded by the follow-up
  commit." Once the owner has committed, replace that sentence with the hash.
- **Design questions.** Ask with multiple-choice questions (at most four at a time) and then wait. Multiple
  choice is easier for him than free text. Do not build a design he has not answered.
- **ADRs.** Never edit an existing ADR. Append an amendment or write a new ADR. The last ADR used is
  **ADR-084**; the next free number is **085**. Check `spec/06_DECISIONS.md` before relying on that.
- **Style.** British English in code comments, documentation and all user-facing copy. Always give full,
  complete commands to run, never "add this line" fragments. Keep replies short; one or two sentences on an
  outcome, not a recap.
- **Git.** The owner commits and pushes. Do not push. Leave changes in the working tree, list the files, and
  give him a complete `git add … && git commit -m "…"` command with a Conventional Commits message. **No
  `Co-Authored-By` or `Claude-Session` lines in commit messages.**
- **Owner runs** the things that need his judgement or his stack: seeds, the live specs, and any step that
  needs a download (downloads need an explicit yes). Docker and the Postgres/Valkey-backed tests may be run
  by you from this machine, one agent at a time (rule 14), and only after you have said what you are about to
  start.
- **Do not over-verify.** Show a new gate red once (rule 15) and run the touched tests; do not re-run the
  world to feel safe.

## 2. Standing constraint (the owner's words)

> Never admit a real dataset, push anywhere public, create a public repository, claim the reserved name,
> restructure the tree, or touch the airbyte container on port 8000.

Also: no credentials in any file or message. `OspreyFlow_Core/Makefile` and `.github/workflows/ci.yml` are
protected: give the owner the change as a command or a diff and do not edit them (a new live-service test
file needs entries in both, which is why `test_investigation_access_store.py` took the new tab-flag tests
instead of a new file). `OspreyFlow_Core/osprey.yaml` and `OspreyFlow_Core/data/` stay uncommitted.

Rules from `process/CLAUDE.md` that bite most often here: **13** (a new workspace action needs a keyboard
case in `keyboard/keyboard.spec.ts` and a registry id in `keyboard/actionRegistry.ts`), **15** (a new gate is
shown red before it is wired in), **3 and 4** (access control in the adapter's query, and an access-control
test on every read path), **6** (entities are never merged in storage), **12** (name the test that would fail
if an invariant were violated).

## 3. Where you are and how to run things

Start Claude Code at the repository root, `/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/ospreyflow`.
It holds `CLAUDE.md` (which imports `OspreyFlow_Build/CLAUDE.md` and so `process/CLAUDE.md`), `.claude/`
(a `graphify` hook guard in `settings.json`, personal permissions in the gitignored `settings.local.json`,
and a `phase` command) and the three sibling trees: `OspreyFlow_Core` (product), `OspreyFlow_Build`
(specification, process, tests, tools) and `OspreyFlow_Data` (per-dataset, empty of raw data).

Run from `OspreyFlow_Core` unless stated. The Python environment is `.venv`.

| What | Command |
| --- | --- |
| Python tests | `PYTHONPATH=.:packages:../OspreyFlow_Build .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini <paths>` |
| Python gates | `PYTHONPATH=../OspreyFlow_Build .venv/bin/python -m tools.<check>` (see the `ci:` target for the list) |
| Lint, types | `make lint`, `make typecheck` |
| Glass unit tests | `cd apps/workspace && npx vitest run src keyboard` |
| Glass types, lint | `cd apps/workspace && npx tsc --noEmit`; from `OspreyFlow_Core`: `npx eslint apps/workspace/src apps/workspace/keyboard` |
| Keyboard browser suite | `npm run test:keyboard --workspace apps/workspace`; one case: `cd apps/workspace && npx playwright test --config keyboard/playwright.config.ts -g "<title>"` |
| Performance gate | `make glass-perf` |
| Bring the running deployment up to date | `make refresh` (theme, images, Keycloak restart, sign-in accounts) |
| Live-service tests | `make dev-up` then the test target in the Makefile (shared containers: rule 14) |

Glass is served at `localhost:8081`. The earlier cloud sessions could not run Postgres, Valkey, Docker or the
live specs; you can, and **the "Not seen" notes in the friction log say which things were never seen against
the real stack** (see section 5).

## 4. State on 4 October 2026

- **Committed:** ADR-081 step A, `346c987` (basis, colour and thickness on relationship types; dotted and
  thick link drawing). Branch tabs, ADR-084, `42d87f6` (branch selected nodes into a new case; the strip of
  case tabs; the Branches list; per-analyst hide flag).
- **Remotes (changed 4 October 2026):** `origin` is the owner's private repo `github.com/aykr/OspreyFlow_Dev`
  (HTTPS, a personal access token held in the macOS Keychain; never put a token in a remote URL).
  `old-origin` is the previous repo, kept for reading, with its push URL set to `DISABLED`. `backup` is
  `github.com/ayankarsolirius/ospreyflow`. Commits are authored as `Ayan`. The owner pushes; you do not.
- **Stray `Icon\r` files:** macOS leaves empty files named `Icon` plus a carriage return throughout `.git`
  and elsewhere in the tree, and they come back. In `.git/refs` they make git fail with `bad object
  refs/remotes/origin/Icon?` or refuse to rename a remote. They are harmless to delete; from the repository
  root: `find .git -name $'Icon\r' -print -delete`. Do not commit them.
- **The sign-in page restyle is committed** as `e1a7572`; its friction-log row in `07_BUILD_PLAN.md` still
  says "Hash: recorded by the follow-up commit." and should carry that hash.
- **Not mine, leave alone:** `OspreyFlow_Core/osprey.yaml` (modified), `OspreyFlow_Core/data/` (untracked).

### Known failures that are not caused by recent work

- `ruff` E501 in `services/api/app.py` near the ADR-068 docstring.
- `tests/harness/test_apply_env.py` (needs Docker) and `test_deployment_schema.py` (reads the uncommitted
  `osprey.yaml`).
- The five `graph_arcadedb[gremlin]` working-set tests fail with "connection refused" unless the dev stack
  is up.
- `route_coverage_check` lists many existing case routes.
- One flaky browser case: "a failed expand announces an error" failed once under load and passed four
  times alone.

## 5. What was never seen against the real thing

From the friction log, the owner's live checks still to do or report:

1. Branch tabs: the strip, the Branches menu, close and reopen, Discard with confirmation, on a real case;
   and `test_investigation_access_store.py` (it now holds five tab-flag tests against Postgres).
2. The sign-in page at `localhost:8081`.
3. The dotted and thick links on a real case (the dot is a fixed 3 pixels on and 4 off, which may look blocky
   at thickness 4 or 5), and `make glass-perf` with the new edge programs.
4. Friction-log rows from earlier rounds that still say "Hash: recorded by the follow-up commit." Ask the
   owner for the hashes; do not guess.

## 6. Open work, in the order the owner raised it

### 6.1 Panel drag and reorder (not scoped)

The owner has panel re-framing (resize and collapse) working and now wants to **drag panels and reorder
them**. Nothing is designed. Ask first (multiple choice): where a dragged panel may go (reorder within its
dock only, move between docks, or float), whether the arrangement is remembered and per analyst or per case,
and what the keyboard route is (rule 13 needs a keyboard case and a registry id, so drag cannot be
mouse-only). Then write an ADR (085) before building. Facts from the Glass that bear on it: there are no
global Zustand singletons; `App.tsx` creates the one working set, the one cross-filter store and the one
delta WebSocket; labels, icons and theme are localStorage singletons; panel state belongs with the design
primitives (`src/design/`).

### 6.2 ADR-081 steps B, C and D (each its own commit; the owner has not said go)

The decision and the owner's answers to its open questions are in `spec/06_DECISIONS.md` (ADR-081 and
Amendment 1 — read both before touching anything).

- **B, the per-link basis.** `Edge` gains a `basis`. A link takes its type's basis; a link of a Direct type
  may be marked probabilistic (statistically derived, or declared by an analyst with a reason); a link of a
  Probabilistic type is always probabilistic; a person never promotes a link to Direct. The Glass draws by
  the link's own basis. The ADR-080 change form asks for the basis each time, with no default, and offers
  Direct only where the type allows it. Confirming a `SAME_AS` link leaves it probabilistic.
- **C, analyst proposals and promotion.** An Editor proposes a type from the change form (name, the entity
  types at each end, directed or not, basis, colour, thickness). It works at once in that case only, is
  labelled analyst-defined, is kept in the control-plane store, never in the shared ontology or the graph,
  is audited with a reason, and is always probabilistic until an administrator reclassifies it. An
  administrator (anyone holding `osprey-admin`) promotes it into a new ontology version through the schema
  step, or rejects it. Routes to propose, list and promote, each with an access-control test: a Viewer
  cannot propose, an Editor cannot promote, a proposal in one case is invisible in another. Step C decides
  whether the promotion screen is in the Glass or the Admin console.
- **D, the Ingest Studio rule.** A relationship written by the Studio from the source's own schema is always
  Direct, and a recipe that names a Probabilistic type is refused at validation. No expression language
  (rule 8). The smallest of the three.

### 6.3 Stage 2 of branch tabs (several live canvases in one page)

ADR-084 decided stage 1 (saved branches that reload on switching) and left stage 2 undecided. Stage 2 is
hard because `App.tsx` owns one working set, one cross-filter store and one delta WebSocket, the server
working set is keyed by `investigation_id`, and `openCase` reloads the page deliberately. Do not start it
without the owner's go and a design round.

### 6.4 Parked (the owner has not asked for these; do not start them)

- Resolution slider: the Strict, Balanced and Broad screenshots (3, 6 and 2 people) did not match the
  intent and were not investigated. The owner marked step 2.7 done. ADR-080 Amendment 2 records what was
  found and what was not reproduced.
- A bounding-box selection for "Branch selected" (spec 02 §3.1h says it has no implementation yet).
- Lookup-cost fix; PaySim into Glass; timeline cross-filter capture; `seed_ingest_folder` output; the
  duplicate case row in Ingest Studio; walkthrough steps 1.3 and 1.7 still describe old behaviour; damaged
  comment lines in the `default.yaml`.

## 7. Glass and server facts worth knowing before you read code

- A branch is a case; `branched_from` is recorded and the creator is its Author (ADR-052). Levels are
  enforced by `InvestigationViewerDep` and `InvestigationEditorDep`; a case with no level reads as 404.
  `tests/services/api/test_investigation_levels.py` must list every case route.
- `authorized_query_check` flags any `*authorized*` store method that does not put `principal.<attr>` in
  its SQL.
- `GlassCanvas` takes `graph` and `store` as props. The cluster drawing puts every node of a cluster at the
  cluster's anchor (spec 02 §1.1 "Collapse").
- Sigma 3.0.3 has no dotted edge program and its plain line is one pixel wide; the Glass carries its own in
  `canvas/dottedEdgePrograms.ts`.
- The strip of buttons over the canvas (`ViewActions`) is right-aligned, and every button added pushes the
  rest left; a keyboard case that clicks near the top of the canvas can end up under it (this broke the
  Group Node double-click case when "Branch selected" was added).
- The owner's browser tests depend on `apps/workspace/keyboard/harness.tsx`; a new prop on `GlassCanvas`
  usually needs a matching line there.
