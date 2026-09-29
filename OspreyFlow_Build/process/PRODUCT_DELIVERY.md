# Product delivery — not part of the build

**This document is not part of the build.** `07_BUILD_PLAN.md` answers one question: what gets
built, in what order, and the test that proves each part works. This document answers a different
one: how the product reaches people once it is built. Nothing here gates a build step, a stage, or
a phase's own exit criterion — every item below is either a distribution decision already made
(with its reasoning) or an owner action still outstanding, and none is a substitute for, or a
precondition of, anything `07_BUILD_PLAN.md` itself requires.

Extracted 22 September 2026, when `07_BUILD_PLAN.md` was restructured to read as construction
only. Nothing below is new; every item already existed, either woven into the build plan's own
stage prose or recorded in `06_DECISIONS.md`. This document consolidates it in one place a reader
can find without hunting across decision records, and removes it from the document whose own job
is a different question. **Excluded from the Apache-scoped documentation set** (`06_DECISIONS.md`
ADR-034 §B2), the same "excluded and private" treatment `06_DECISIONS.md`/`07_BUILD_PLAN.md`
already carry.

## The alpha gate

**Decision and full reasoning: `06_DECISIONS.md` ADR-042, not duplicated here.** In one sentence:
testers receive a build only after Phase 8's own full exit criterion is green — both acceptance
scenarios passing unchanged on `local-lite` — not after the harness alone or the product-feature
core alone. ADR-042's own reasoning (a tester evaluates a product, not a component) and its
"Consequence, stated rather than left implicit" paragraph (no external feedback reaches the
product before it is complete) are the source; this document only points to it.

**Build-plan-specific facts about the gate, extracted from `07_BUILD_PLAN.md` rather than
restated there:**
- B21 (Phase 8 Stage 4g) is part of Scenario B's own full form as of 22 September 2026, so it is
  part of what the alpha gate now requires green — a real cost of accepting B21, not merely a
  record of it. `07_BUILD_PLAN.md`'s own pathfinder decision entry (its "Legacy disclosures"
  section) has the reasoning for *why* B21 was added; this is only the distribution-readiness
  consequence of that decision.

## The analyst review

**Decision: `06_DECISIONS.md` ADR-042, "The analyst review is decoupled from alpha, and not
blocked by it."** It needs a running dev instance, not a packaged, tester-safe artefact, so it can
run as soon as there is enough of the product for an analyst to usefully react to — the only
external input this build receives before Phase 8's own full completion. **Fixture Corp**
(`07_BUILD_PLAN.md` Stage 4a) is what that review runs against — the only demo both shippable and
deterministic enough to put in front of a reviewer (`06_DECISIONS.md` ADR-035 §C5). **Scheduling
and running the review is an owner action**, lead time measured in weeks, not a build-plan stage —
nothing in `07_BUILD_PLAN.md` produces or consumes it.

## Packaging's own artefact-hygiene properties — not tester-conditional

`06_DECISIONS.md` ADR-034 §B7 states two assertions the packaging pipeline (`07_BUILD_PLAN.md`'s
own harness/packaging stage) must satisfy as a property of *producing an artefact at all*: no file
originating in the private build tree appears in the built artefact, and no identifier from the
authorship record (ADR-034 §B5) appears in it either, including in build-time version metadata.
**These are packaging correctness properties, not a gate on who receives one** — a leaking
artefact is wrong whether it is ever distributed to anyone or not, the same way an access-control
bug is wrong whether or not an unauthorised principal ever actually exploits it. `07_BUILD_PLAN.md`
now states and tests them that way, against the packaging stage itself. **What belongs here
instead, because it *is* about audience:** no artefact is handed to a third party — alpha or beta
tester, or anyone else — before these two properties are proven true of it; that handover
condition is a distribution decision, not a packaging requirement, and lives in this document.

## Legal advice, real data, and the Enron-corpus request — not a build gate

`06_DECISIONS.md` ADR-035 §C3 records a declined request: `internal`-distribution use of the real
Enron corpus for local development and scale/realism testing, permitted narrowly (never the
repository, CI, or any demo — standing rule 3 and `CLAUDE.md` rule 9 are unamended). **Checked
directly: nothing in `07_BUILD_PLAN.md` references this item at all — it does not gate any build
step.** It is also, on its own text, not really a *demonstration* question either — the demo
permission was the part declined; what remains open is whether even development/testing-only use
of real data requires a documented lawful basis and retention period under UK GDPR, recorded in
ADR-035 §C3 as "requiring legal advice." **Owner action, outstanding, gating nothing in this
build.**

## Owner actions with no build-plan dependency

Each of the following is recorded in `06_DECISIONS.md`, verified here to gate no build step
(checked directly against `07_BUILD_PLAN.md`, not assumed), and listed so a reader has one place
to find every outstanding distribution/legal/administrative action without searching the decision
log phase by phase.

- **IPO trademark search.** `06_DECISIONS.md` (ADR-034's own naming discussion): "Osprey Flow" was
  checked against Companies House availability only; the IPO register is a separate check, an
  owner action with months of lead time, not addressed in that record. Gates nothing in
  `07_BUILD_PLAN.md`.
- **DCO versus CLA.** `06_DECISIONS.md` ADR-034 §B6: recorded as an open item for the owner,
  deliberately not decided in that record. Gates nothing in `07_BUILD_PLAN.md`.
- **Archiving the old repository.** `06_DECISIONS.md` (ADR-031/034's own repository-split
  discussion): an administrative step attached to Trigger B (publication), not to Trigger A (the
  restructure `07_BUILD_PLAN.md`'s own documentation-refresh stage performs) or to any earlier
  build step.
- **Entity and copyright decisions.** `06_DECISIONS.md` ADR-034 §B3/§B4 (destination account,
  reserved repository name — "record, do not build") and §B6 (copyright holder name decided now;
  copyright *year* deferred to Trigger B, being the year of first publication). Recorded, not
  built, and gates nothing in `07_BUILD_PLAN.md`.

**Verification method, stated once rather than per item:** each item above was checked directly
against `07_BUILD_PLAN.md`'s own text (`grep` for the item's own name or a close synonym across
the stage list) rather than assumed absent. None appeared as a condition on any stage's own exit
criterion.

## What Trigger A and B actually are — pointers only

`06_DECISIONS.md` ADR-031/034 have the full record. In brief, so this document is a complete map
without duplicating either: **Trigger A** (files move, `docs/` → `spec/`+`process/`,
`LICENSE`/`NOTICE` created) fires at `07_BUILD_PLAN.md`'s own documentation-refresh stage close —
a real build step, still in the build plan, just moved to run after the milestone rather than
before it. **Trigger B** (publication — a new, seeded, neutral-identity repository made public) is
owner-instructed only, once Trigger A, publication readiness and the Trigger B rehearsal are done
and §B4's own open items are decided. **Owner ruling, 28 September 2026: alpha and beta testing
follow Trigger B, not precede it** — this corrects this document's own prior ordering, which had
it backwards. Trigger B is not scheduled by any stage in `07_BUILD_PLAN.md` at all.
