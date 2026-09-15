# OspreyFlow — session handover

Written 14 September 2026, at the start of Phase 3. Everything durable about the *system* is in
`docs/` in the repository. This file covers what `docs/` does not: how the review has been run,
what keeps going wrong, and what is open right now.

---

## First: the repository is the source of truth

`docs/` in the OspreyFlow repository is authoritative for the specification. Do not keep a
separate working copy and do not apply whole-file replacements to it.

This caused two regressions in the previous session. Claude Code corrects `docs/` as it builds —
documenting shapes it implemented, removing stale framing — and those corrections never came back
to the reviewing session. Copying a whole file over then silently reverted them. A rule now
exists in `CLAUDE.md` to catch it, but the reliable fix is: **send targeted edits, exact old text
and new text, never a replacement file.**

---

## Where the build is

| Phase | State |
| --- | --- |
| 0 — Skeleton and guard rails | Complete |
| 1 — Domain model and graph adapter | Complete, but with an open defect: the `GraphPort` conformance suite is intermittently flaky against a live ArcadeDB container (index-creation/read-lock errors under sustained sequential load) — not reliably green as the exit criterion requires. Needs investigation before this phase is closed out for real. |
| 2 — Ingest, normalisation, staging | Complete, including a follow-up masking fix — with two known gaps against the build-plan bullets: only the CSV connector is implemented (JSON and generic-delimited are stubbed, not built); the ingest load path does not yet write the analytics store transactionally alongside the graph store (analytics store is populated only via test-harness wiring, per the ingest entrypoint's own docstring). |
| **3 — Conduit and the working set** | **Built and committed** (`5e0a70f`, 15 September 2026) — this table was not updated when that landed. Every build-plan bullet and exit-criterion clause is present and unit/component-tested against live ArcadeDB and Valkey: FastAPI app, JWKS-with-TTL auth, Valkey working-set store, WebSocket delta/reconnect protocol, fail-closed Postgres audit, ULID/`AuditStub` minting moved to the Conduit, real `filtered_count`, job-routed `supersede_node`. Not yet confirmed: a full live run of the end-to-end scripted-client scenario test — blocked in the last review session by a local Postgres container in a broken credential state, an environment issue rather than a code defect. Re-run with a clean Postgres volume before treating the exit criterion as fully proven. |
| 4 — The Glass, first light | **Complete and verified** (this table was not updated when it landed either). All twenty primitives, the full node-state vocabulary, semantic zoom, canvas interaction, inspector, history, and the perf/a11y/keyboard CI gates ran green live in review. |
| 5 onward | Not started |

### Phase 3 decisions already taken

- **OIDC:** JWT validation against a static JWKS fixture, no live Keycloak. The interesting logic
  is claims → `Principal` → filter injected into the traversal, and a fixture gives deterministic
  tokens for the edge cases a live IdP makes awkward. **Condition:** the JWKS source must be a
  config point from the start — a URL fetched and cached with a TTL, pointed at a local file in
  tests. Not a key hardcoded at import. Key rotation breaks first in real deployments.
- **Delivery:** build the ULID/`AuditStub` move and the Working-Set Service as one continuous
  run, then **stop and show a diff before the API surface**. Review target: the service
  interface, the delta protocol including reconnect-and-resnapshot, the `limit_exceeded` path,
  and how `filtered_count` is derived. Everything after that runs continuous.

### Phase 3 constraints issued

1. `filtered_count` is the obligation this phase discharges — a declared placeholder since
   Phase 1, and `08_ACCEPTANCE_SCENARIOS.md` depends on it.
2. The cap never truncates. Typed `limit_exceeded` with three options: branch, filter, batch.
3. ULID and Conduit-owned `AuditStub` assignment move here from the adapter.
4. The delta protocol survives a mid-stream disconnect — reconnect resnapshots, never patches.
5. Audit fails closed. The only place in the platform that does.
6. Cache by `principal_class`, never `principal_id`.
7. `services/api` gets a Dockerfile this phase, with `trivy image` in CI.
8. `make dev-up` brings up ArcadeDB, MinIO, Valkey and Postgres so the full suite runs locally.
9. Prove statelessness: kill the instance serving a session mid-investigation, analyst notices
   nothing.

---

## How the review has been run

Claude Code does the building. The reviewing session does three things:

**Reviews plans before approval.** Every phase starts in plan mode. The plan is read against the
phase's exit criteria, and amendments are sent before any code is written. This is where most
value has come from.

**Answers the questions Claude Code raises.** It surfaces genuine ambiguities in `docs/` and
waits. Those are usually real gaps, and the right response is to fix the specification rather
than to answer in chat — an answer given only in conversation is lost by the next phase.

**Runs the end-of-phase audit.** After every phase:

> Where does this diverge from `docs/`, and what did you assume that the spec does not state?
> List the assumptions explicitly — I care more about those than about the code.

This has found a real defect every single time, and roughly half have been specification defects
rather than implementation ones.

---

## Failure modes that keep recurring

Worth watching for specifically, because each has happened more than once.

**Prose surviving a change to the mechanism it justified.** A sentence written to argue for one
design stays in place after the design is amended, and now argues for something the code no
longer does. When a change alters a mechanism, check whether the surrounding prose still argues
for what the code now does.

**Invariants stated in prose that no test exercises.** `upsert_edges` never merged same-pair
edges for a whole phase while the conformance suite passed, because no case wrote the same pair
twice. When a spec sentence states an invariant, ask which test would fail if it were violated.

**Coverage that asserts on write and never reads back.** A round-trip test that checked only
`node.type` hid every property-level defect beneath it.

**Access-control tests borrowing trust from a shared helper.** Standing rule: every read path
gets its own test. A helper that looks right is not a tested helper.

**Defaults that are guesses wearing configuration's clothes.** `dayfirst=True` in a datetime
normaliser with both the UK and US in scope. The pattern: any default that silently produces a
plausible-but-wrong value rather than an error.

---

## Standing positions worth keeping

These have come up repeatedly and the answers have held.

- **Conformance suites before adapters.** An adapter written first defines the contract by
  accident.
- **Never truncate silently.** Anywhere. A slice near a result set is a defect.
- **Access control at the port, never after retrieval.** And existence must not leak through path
  length, degree count or aggregate bucket.
- **Model output is `inferred` until a human confirms it.** No automatic promotion, no threshold.
- **Entities are never merged in storage.** Scored `SAME_AS` edges, collapsed at query time.
- **No scripting language in the Ingest Studio.** It will be requested. Transforms are Knowledge
  Adapters with golden tests.
- **Geometry lives in the analytics store.** The `Location` node holds a `geometry_ref`.
- **Raw staging before normalisation.** Two Parquet datasets. Only the raw one makes
  re-normalisation possible without re-uploading.

---

## Open items not yet closed

- **The Ingest Studio prototype has had its first analyst review (15 September 2026) and passed
  — no changes requested against the synthetic fixture it currently runs on.** ADR-018 put this in
  Phase 2 precisely so it could happen early, and it has. A second review is still required once
  real data can be loaded through it, so the analyst can verify the row template and mapping
  screen against an actual live scenario rather than the synthetic fixture — do not treat this
  item as fully closed until that second pass happens.
- **`§8.1` pattern-matching binding rule is more restrictive than Phase 7 will want.** No pattern
  where a node is reachable only via a later edge. Honestly documented, fine for now, will not
  survive an analyst drawing an arbitrary pattern on a canvas. Revisit at Phase 7.
- **HMP fixture `EventRecord`s are orphaned** — no graph side. Recorded, and "give the HMP fixture
  a graph side" is in Phase 5's scope.
- **`duration_s` is unexercised** in the analytics suite because no method aggregates over it yet.
  Noted rather than forced, correctly.

---

## What changes at Phase 4

Phase 3 is the last quiet phase. From Phase 4 the platform is on screen, and the useful feedback
shifts from "does this match the spec" to "does an analyst want to use this". The specification
stops being the only reference, and the studio prototype review above becomes the thing that
feeds both Phase 4's canvas and Phase 5a.

The platform becomes demonstrable at Phase 5 — network, timeline and map cross-filtering over
real ingested data. That is the point at which showing it to a real analyst returns more than
further specification review does.
