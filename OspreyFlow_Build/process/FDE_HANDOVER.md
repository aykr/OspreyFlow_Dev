# OspreyFlow — Handover to a Claude Code session working directly in the repository

Written 4 October 2026, for Ayan; brought up to date 9 October 2026 (section 4 and section 6.0 are the
current state and the next work; read them first). This file supersedes `SESSION_HANDOVER.md` (18 September 2026, written for
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
  **ADR-106** (9 October 2026); the next free number is **107**. Check `spec/06_DECISIONS.md` before relying on that.
- **Style.** British English in code comments, documentation and all user-facing copy. Always give full,
  complete commands to run, never "add this line" fragments. Keep replies short; one or two sentences on an
  outcome, not a recap.
- **Git.** Since 4 October 2026 the owner lets the session commit directly ("can you start running the commit
  commands"), naming each file; the owner pushes and you never do. Never stage `OspreyFlow_Core/osprey.yaml`
  or `OspreyFlow_Core/data/`. Conventional Commits; each commit's message ends "record <previous hash>" and
  fills the previous friction-log row's hash. **No `Co-Authored-By` or `Claude-Session` lines in commit
  messages.**
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
**On 9 October 2026 a session broke this rule:** commit `47f3516` added `test_entity_pictures.py` to two
lists in `ci.yml` (the live-service job's run list and the `test` job's ignores). The permission settings
blocked the matching `Makefile` edit but not the `ci.yml` one. The owner decides whether to keep it or revert it;
the `Makefile` half is in section 6.0.

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

The knowledge graph (`graphify`) lives at the repository root, `graphify-out/` (gitignored), and is what the
hook guard and `graphify query` read; rebuild it with `graphify update .` from the root after a change (AST only,
no API cost). The older `OspreyFlow_Build/graphify-out/` was built on 29 September 2026 against the layout
before ADR-054 split the tree; its paths are all wrong and it is dead weight (204 MB) to delete when you choose.

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

The Glass is served at **`localhost:8080`** (`OSPREY_WORKSPACE_PORT`) and Keycloak at `localhost:8081`
(`OSPREY_KEYCLOAK_PORT`); `make launch` opens the right door. Opening `localhost:8081` by hand lands on
Keycloak's own `master`-realm administration console, which neither carries the OspreyFlow theme nor knows the
demo accounts (they live in the `osprey` realm). The demo passwords are in
`deploy/generated/local-lite/deployment.env` and `make refresh` sets them again from there. The earlier cloud sessions could not run Postgres, Valkey, Docker or the
live specs; you can, and **the "Not seen" notes in the friction log say which things were never seen against
the real stack** (see section 5).

## 4. State on 9 October 2026 (current)

**Where `main` is.** `fa18859`, 164 commits ahead of `origin/main`, none pushed (the owner pushes). Not mine,
leave alone: `OspreyFlow_Core/osprey.yaml` (modified), `OspreyFlow_Core/data/` (untracked),
`OspreyFlow_Product_Overview_Draft1a.pptx` (untracked, the deck's source).

**Built 6 to 9 October 2026** (each with its friction-log row in `07_BUILD_PLAN.md`; the last rows are the
detail):
- ADR-095 to ADR-102: extraction with a real model and whole decoded emails (095); the side panels as
  accordions (096); the 6 October design review (097); a fast recogniser first and the model on request
  (098); datasets per case (099); the Explore panel, *What's new*, most connected, by type, busiest links
  (100); ArcadeDB 26.10.1 (101); handling never lowered by a rewrite (102).
- **The analyst's journey** (deck chapters 1 to 16, captured as `j01`…`j27`) and the assessment chapter.
- **The data engineer's journey through the Ingest Studio** on synthetic carrier data in the case *Carrier B
  intake* (signed in as `osprey-demo-analyst`, roles named in captions): the phone records (20 numbers, 141
  links), a re-run (nothing duplicated), the subscriber list, the hand-off to the analyst (`d01`…`d20`).
  Faults found on the way and fixed: Run's access gate; rejection reasons that name the cause, not the
  value; links counted, not writes; ADR-103 (Ofcom drama numbers); letters refused in a phone number;
  percentages that never round to 100%; entity rename; notes kept on *Ignore*; identifiers offered as
  properties; ADR-104 (`person_name(part=family)`).
- **The map:** themed basemap (land and water apart, light and dark), place-name glyphs fetched, pinned and
  served by the deployment (`scripts/fetch_basemap_glyphs.py`, `/fonts/`), the hotspot panel counts only
  events at a place. A place loaded through the Studio is now on the map (`connectors/cell-site-csv.yaml`,
  `services/ingest/geometries.py`). Seen live: 8 synthetic masts in Manchester and 31 handset sightings in
  *Carrier B intake*, labelled, with the hotspot panel's 8 bars (`d21_map_masts.jpg`).
- **ADR-105, one entity's own picture:** ontology **version 13** (`DEPICTS`, an image Document to the
  entity it shows), four routes filtered in the adapter, the Inspector's *Picture* part, the canvas drawing
  the entity's picture before its type's. Seen live on one Device.
- **A value the ontology refuses rejects its row** (fa18859) instead of aborting Verify or the load.

**Ontology version 13 is in force.** Every Studio recipe published before it is flagged when the API starts;
reopen each in the Studio and publish it again before it runs (ADR-094 Amendment 1's procedure).

**The deck** (owner-only, never committed; `OspreyFlow_Product_Overview_Draft1b.pptx` at the repository root
is in `.git/info/exclude`): 51 slides, rebuilt from `Draft1a` by
`../OspreyFlow_deck_screens/deck_build/build_deck.py`, run there as
`uv run --quiet --no-project --with python-pptx --with pillow python build_deck.py`. Screens are in
`../OspreyFlow_deck_screens/`; the synthetic sources loaded through the Studio are in its `journey_sources/`.
The Enron slides (32 and 33) carry real data and stay on this machine. `d21_map_masts.jpg` is captured but
not yet in the deck.

**Running things that differ from section 3:**
- The session runs `make refresh` itself after committing a fix that needs deploying (the owner's choice,
  9 October). **Each refresh signs the browser out**, and so does reloading the Glass's tab (its token is
  kept only in the page): the owner signs in again, never the session. Batch work into one refresh before a
  live check, and check persistence read-only from the graph instead of reloading.
- Read-only graph reads on the deployment: `docker exec osprey-local-lite-api-1 python -c '…'` with
  `ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))`; a link's properties sit under
  `properties`, and labels are physical (`mx_DEPICTS`).
- **Throwaway test stack** (not the deployment; replaces section 4a's `fde-test-*` names):
  `osprey-probe-arcadedb-new` (2491), `osprey-test-pg` (55433), `osprey-test-valkey-6379` (6379),
  `osprey-test-minio` (9000, from the local image `quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z`). The
  test line, from `OspreyFlow_Core`: `PYTHONDONTWRITEBYTECODE=1 ARCADEDB_HTTP_PORT=2491 POSTGRES_PORT=55433
  POSTGRES_PASSWORD=throwaway POSTGRES_DB=osprey VALKEY_PORT=6379 PYTHONPATH=.:packages:../OspreyFlow_Build
  .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini <paths> -q -p no:cacheprovider`. Leaving out
  `ARCADEDB_HTTP_PORT=2491` makes every ArcadeDB test fail as if the database were absent.
- Glass type-check is `npm run -s typecheck` from `OspreyFlow_Core` (the root `tsconfig.json`), not `npx tsc`
  inside `apps/workspace`.
- `PYTHONDONTWRITEBYTECODE=1` for any planted-fault loop: a stale `.pyc` once hid a plant.

**Known failures, not from this work** (add to section 4a's list): `test_build_local_basemap_end_to_end.py`
(its fixture path); `test_explore_routes.py` fails 8 to 12 cases only when the whole `tests/services/api`
directory runs, and passes alone (order-dependent, the same at the commit before ADR-105); `test_export.py::
test_export_ledger_entry_survives_investigation_deletion` (a foreign key on `investigation_grants`);
`route-coverage-check` and `test-file-coverage-check` were already red for other routes and files.

## 4a. State on 5 October 2026 (history)

- **Committed on 4 and 5 October 2026, to `439e664`:** ADR-090 and its Amendments 1 to 3 (analyst-proposed
  relationship types, built: C1 `0021c3e`, C2 and C3 `439e664`); ADR-091 (link display names), ADR-092 and its
  Amendments (emails as Documents, the full-screen reader), ADR-093 (selection), ADR-094 steps 1 to 3 (messages,
  held media, file uploads), ADR-081 step D, ADR-084 Amendments 2 and 3, ADR-089 Amendment 1. None pushed.
- **After ontology v12 (ADR-094 Amendment 1)** every published Studio recipe is flagged once: reopen it and
  publish it again before it runs.
- **Throwaway test containers** the session may start for live tests, all on 127.0.0.1 and none part of the
  deployment: `fde-test-minio` (9000), `fde-test-postgres` (5433), `fde-test-arcadedb` (2480). Stop them with
  `docker stop fde-test-minio fde-test-postgres fde-test-arcadedb` when done; they clash with `make dev-up`.

### Earlier state (4 October 2026)

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
- **The sign-in page restyle is committed** as `e1a7572`, and its friction-log row carries that hash.
- **Later commits** run to `4b4a6ba` (ADR-085 to ADR-089, ADR-081 step B); `main` was 20 commits ahead of
  `origin/main` on 4 October 2026, waiting for the owner to push.
- **Not mine, leave alone:** `OspreyFlow_Core/osprey.yaml` (modified), `OspreyFlow_Core/data/` (untracked).

### Known failures that are not caused by recent work

- `ruff` E501 in `services/api/app.py` near the ADR-068 docstring.
- (Fixed 4 October 2026.) `src/inspector/linkHistory.ts` differed from `LinkHistory.tsx` only in case, which on this
  Mac failed `tsc` and six unit cases; it is now `describeChange.ts`, and `tests/test_case_collision_check.py` fails
  if any two tracked files under the product tree differ only in case.
- Keyboard specs built in the cloud mirror may use keys that behave differently on macOS: ArrowDown on a closed
  `<select>` opens the menu here instead of moving the choice. `link-change.spec.ts` was corrected on 4 October 2026;
  any other spec that presses an arrow on a `<select>` will fail the same way until it types a letter instead.
- `tests/harness/test_apply_env.py` (needs Docker) and `test_deployment_schema.py` (reads the uncommitted
  `osprey.yaml`).
- The five `graph_arcadedb[gremlin]` working-set tests fail with "connection refused" unless the dev stack
  is up.
- `route_coverage_check` lists many existing case routes (the access, rename and delete routes, and `GET
  /v1/investigations`).
- `tests/extract/test_profile.py` expects `endpoint_kind` without `account` (added in ontology v10).
- `decision_log_publication_check`: ADR-055 cites ADR-049. `doc_citations_check`: `scripts/probe_write_cost.py`
  (twice in the decision log) and `inspector/linkHistory.ts` (in `tools/case_collision_check.py`).
  `provenance_annotation_check`: spec 03 lines 92 and 118.
- **5 October 2026: a test deleted the owner's deployment.** `tests/harness/test_apply_env.py` runs under `make
  test`, brings up `osprey-local-lite` (the real deployment's project name too) and tears it down with `down -v`;
  run by this session, it deleted every case, the graph and the analytics store. It and the other live harness
  tests now skip when any container or volume of that project exists (`tests/harness/deployment_guard.py`).
  **Still: never run the whole test tree on the owner's machine; run the touched paths.**
- **A live-service test file not yet wired** into `Makefile`'s `test` ignore list and a ci.yml live-service job
  (the owner's edit; `test_file_coverage_check` fails until then): `tests/services/api/test_link_type_store.py`
  (Postgres). The MinIO- and ArcadeDB-backed files from ADR-094 and ADR-090 sit under directories the `test`
  target already ignores (`tests/ingest`, `tests/conformance/graph_port`).
- `make glass-perf` fails two cases (the 50k/250k first frame and the pan/zoom sweep both time out at 60 seconds), at `b10f801` as well as after ADR-091, so the failure predates both; first seen 4 October 2026, not yet investigated.
- `link-selection.spec.ts` ("a click a few pixels off a link selects it", "a click on the link itself") fails on a single worker and passes in the full keyboard run, at `b10f801` as well as later; not investigated.
- One flaky browser case: "a failed expand announces an error" failed once under load and passed four
  times alone.

## 5. What was never seen against the real thing

From the friction log, the owner's live checks still to do or report:

1. Branch tabs: the strip, the Branches menu, close and reopen, Discard with confirmation, on a real case;
   and `test_investigation_access_store.py` (it now holds five tab-flag tests against Postgres).
2. The panel grip rows (ADR-085): Move up / Move down, dragging, and the order surviving a reload, on a real case.
3. A link marked probabilistic from the change form (ADR-081 step B): the question in the form, the dotted line, the Basis row.
4. The sign-in page (reached from the Glass at `localhost:8080`, which sends the browser to the `osprey` realm on 8081).
5. The dotted and thick links on a real case (the dot is a fixed 3 pixels on and 4 off, which may look blocky
   at thickness 4 or 5), and `make glass-perf` with the new edge programs.
6. Friction-log rows from earlier rounds that still say "Hash: recorded by the follow-up commit." Ask the
   owner for the hashes; do not guess.
7. Everything built on 4 and 5 October 2026 after `4b4a6ba` (section 4): each friction-log row says what was
   not seen. In particular, ADR-090 in the live Glass, signed in once as an Editor (*Define a new type…*) and
   once as `osprey-admin` (*Proposed types*), and the media and upload work against the deployment's MinIO.

## 6. Open work, in the order the owner raised it

### 6.0 Next, as of 9 October 2026 (start here)

**Waiting on the owner**
1. (Done 9 October 2026, by the owner's hand: `dba07d5`.) The `Makefile` edit for `test_entity_pictures.py`.
2. (Decided 9 October 2026: keep.) The `ci.yml` lines from `47f3516`.
3. Republish the Studio recipes flagged by ontology version 13 (owner chose: in the same signed-in
   session as the live-check pass below).
4. (Done 9 October 2026.) Pushed to `dba07d5`; commits since then await the next push.

**Live checks to do (sign-in needed; one refresh, then all of them)**
5. **The Studio Map fault** (b475b5a's row): with a link already in the template, picking the next link's
   start was seen to leave only the picked entity drawn. `keyboard/map-canvas.spec.ts` could not reproduce it
   in three sequences (34cb171), so try it on the deployed Studio: a new draft, two entities and a link,
   *+ entity* a third, *+ link*, click the third. If it shows, the fault is in `MapScreen` or the page around
   the canvas, not `MapCanvas`.
6. *Remove picture* on the deployed Glass (only *Set picture* was seen live).
7. The "Not yet seen" rows of 6 to 9 October, each named in its friction-log row: the hotspot panel on the
   HMP case (it is mounted whenever the ontology has a link type to `Location`, which version 13 always has,
   so it shows on every case; on *Carrier B intake* it was seen counting the masts); Run's refusal; a renamed entity and a kept
   note in the Studio; Profile's rates; the export report; the drawer and the menu (`5a08d08`, `93be822`);
   the ranking (`38454f1`); a Verify rejection for a wrongly typed value (fa18859).

**Faults found and not fixed** (each in the friction log)
8. (Fixed 9 October 2026, `65e4d3e`.) The profiler's ranking: a checksum-backed match now outranks a
   shape-only one (spec 09 §3's ranking rule).
9. (Fixed 9 October 2026, `138c031`.) Map's *+ mapping*: rows are editing state, not the Record.
10. The canvas's *Labels* menu does not close on a click outside it; with two entities the right-hand
    label runs under the Inspector; there is no error boundary.
11. The Studio's source list said "No drafts yet" without the case's earlier Carrier B drafts (seen once).
12. (Fixed 9 October 2026, `f369059`.) The picture file control empties once the picture is sent.
13. A geometry ref already loaded at a marking the loader cannot read would collide on insert after the
    graph commits; `scripts/build_local_basemap.py`'s gazetteer load writes no geometries.
14. (Fixed 9 October 2026, `22e76d6`.) An empty file is listed as "empty", bytes below a kilobyte.
15. Enron: document preview times out; quoted-printable bodies; duplicate findings; link-type ids shown
    instead of names.
16. (Decided and built 9 October 2026, ADR-106.) Authors are named at read time from the identity
    provider — judgements, gaps, link notes, questions and Studio recipes; the id shows where no name
    resolves. Also that day, ADR-098 Amendment 3: *Quick scan* / *Deep read (model)* as equal buttons,
    pending findings marked in the reader's text. Both not yet seen on the deployed Glass.
17. `make refresh` does not carry new mounts into the generated compose; the hand edits (ingest root, tiles,
    `fonts`) live in `deploy/generated/local-lite/compose.yaml` and survive it.

**Deck**
18. Add `d21_map_masts.jpg` (and, if wanted, a picture slide) and rebuild with `deck_build/build_deck.py`.

**Unchanged from before 9 October:** sections 5, 6.1 to 6.4, and the standing summary's "Remains after the
milestone" in `07_BUILD_PLAN.md` (the harness-image ports test, GitHub Actions never run, B6's span
anchoring, the local basemap on this host); Phase 8a, the cluster profile, is unstarted.

### 6.1 Panel drag, reorder and resize (built 4 October 2026, ADR-085 and ADR-086; owner's live check to do)

Decided by the owner's four answers and built: the Inspector, Metrics and Query builder can be reordered within the
right-hand column by Move up / Move down buttons or by dragging a grip handle; the order is kept per analyst in
localStorage (`ospreyflow.side-panel-order`); the timeline does not move and nothing floats; ADR-082's width handle
stays open. Code: `src/layout/panelOrder.ts`, `src/layout/SidePanelStack.tsx`, `App.tsx`; keyboard case in
`keyboard/panel-frames.spec.ts`. Then, the same day, ADR-086: every panel edge is a sash (column width, stacked panel
heights, timeline height), dragged or moved by arrow keys, Home or double-click to reset, sizes kept in
`ospreyflow.layout-sizes` (`src/layout/layoutSizes.ts`, `src/layout/Sash.tsx`). **Not seen** on the real Glass: the grip
rows and the sashes.

### 6.1a Built on 4 October 2026 from the owner's live testing (all awaiting his live check)

ADR-086 resizable panels; ADR-087 timeline emergence, dimmed links and the no-events state; ADR-088 the
social-network filters in the Metrics panel; ADR-089 the emails behind an Enron link in three steps (list,
open, extract and accept); ADR-084 Amendment 1 (Shift+click, Branch from a selected node's menu); ADR-060
Amendment 2 (the view never moves by itself). **Enron needs its events re-seeded** for the
4,000-character excerpts before the emails can be read or extracted from. `make seed-enron` refuses
(the events are already loaded and a second load would double every count); run the wrapper
directly with `--replace-events`, which deletes the case's own events, reloads them and keeps the
graph: `cd OspreyFlow_Core && PYTHONPATH=.:packages:../OspreyFlow_Build .venv/bin/python -m
scripts.seed_internal enron --stop-api --replace-events` (the `Makefile` target is unchanged; adding
the flag to it, or a `seed-enron-events` target, is the owner's edit). The extraction routes use the
deployment's local model (`CONFORMANCE_MODEL`) unless the caller names one; the Glass names none.

### 6.2 ADR-081 steps B, C and D (all built; the owner's live checks to do)

The decision and the owner's answers to its open questions are in `spec/06_DECISIONS.md` (ADR-081 and
Amendment 1 — read both before touching anything).

- **B, the per-link basis — built 4 October 2026 (ADR-081 Amendment 2); owner's live check to do.** `Edge` gains a `basis`. A link takes its type's basis; a link of a Direct type
  may be marked probabilistic (statistically derived, or declared by an analyst with a reason); a link of a
  Probabilistic type is always probabilistic; a person never promotes a link to Direct. The Glass draws by
  the link's own basis. The ADR-080 change form asks for the basis each time, with no default, and offers
  Direct only where the type allows it. Confirming a `SAME_AS` link leaves it probabilistic.
- **C, analyst proposals and promotion — built 5 October 2026 (ADR-090 and Amendments 1 to 3; Amendment 2
  replaces the rewrite with labels read by alias, the owner's "rename by alias"). Open: the owner may overrule
  a branch reading its parent's proposals rather than copying them (Amendment 2 decision 3); withdrawing from
  the Glass is not offered (the route is built).** The original design, for reference: An Editor proposes a type from the change form (name, the entity
  types at each end, directed or not, basis, colour, thickness). It works at once in that case only, is
  labelled analyst-defined, is kept in the control-plane store, never in the shared ontology or the graph,
  is audited with a reason, and is always probabilistic until an administrator reclassifies it. An
  administrator (anyone holding `osprey-admin`) promotes it into a new ontology version through the schema
  step, or rejects it. Routes to propose, list and promote, each with an access-control test: a Viewer
  cannot propose, an Editor cannot promote, a proposal in one case is invisible in another. Step C decides
  whether the promotion screen is in the Glass or the Admin console.
- **D, the Ingest Studio rule — built 5 October 2026 (ADR-081 Amendment 3).** A relationship written by the Studio from the source's own schema is always
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
