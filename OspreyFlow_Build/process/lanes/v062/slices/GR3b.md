# Slice GR3b · GR3 · The GOV.UK pages' fixture Conduit answers from the real routes (DRAFT for the owner's rulings; no row)

**Status: a draft, written 25 November 2026 on the owner's (B) (`RULINGS.md`, "GR3a's structural fix").** No row in
`slices.tsv` and not started until the owner rules on the open questions below and a scout has answered "what exists
today". Then the conductor cuts it (it may become two parts).

## Why

GR3a ran six rounds; in five of them the verifier found the page disagreeing with what the real Conduit route sends,
and each time the hand-written fixture Conduit (`apps/pages/test/support/fakeReportConduit.ts`, `fakeConduit.ts`) was
narrower or more lenient than the real route, so no test could turn red (rule 15: a fixture models the dependency's
refusals and its real shapes, not our hopes). AD3a's fixture had the same fault twice (a 405 the real route does not
send, an invite body the real route refuses). RM1a uses the same pattern.

## What (for the owner to rule on; my proposal first in each)

1. **The answers come from the real route.** A Python test runs each real Conduit route the GOV.UK pages read (the
   report route GR3a reads, the admin people and roles routes AD3a reads, the alert queue RM1a reads) in-process,
   over the same synthetic worlds the page tests use, with the stores at the conformance suites' fakes, and writes each
   answer as golden JSON under the pages' test folder. The page tests serve the goldens through the fixture Conduit.
   **A test fails when a golden differs from what the route answers now**, so the fixture cannot drift from the route.
2. **Refusals too.** Each route's refusals (401, 403 or 404 for a missing right, 409 limits by `cap_kind`, 422 for a
   bad body, 405 only where the real route sends it) are goldens as well, made by the same route.
3. **The worlds** are written once, in Python, as data the route reads (synthetic, in-repo: rule 9), and the page
   tests name a world by id. Two readers of different clearance per world where a figure is per-reader (rule 7).
4. **The hand-written fixtures go**, route by route, as each golden set lands; none is left half-hand-written.

## The owner's rulings on the open questions (25 November 2026): (a) one part per route, the report route first (this part), then AD3b and RM1b; (b) GR3a merges first; (c) the drift check runs in `make test` on every merge, and regenerating the goldens is a separate target a builder runs on purpose, never automatic. Cut after GR3a merges.

- **(a) Scope:** all three pages' routes in one part, or one part per route (GR3b report, AD3b admin, RM1b queue)?
  My proposal: one part for the report route first (GR3a's), then the others as each page's next part.
- **(b) Order against GR3a:** GR3a merges on its round-7 strict reader and field census first, then GR3b moves its
  tests onto goldens; or GR3a waits for GR3b. My proposal: GR3a first.
- **(c) Where the goldens are made:** in `make test` (pure, stores at fakes) on every merge, or a separate target
  run when a route changes. My proposal: in `make test`, so a route change that alters an answer fails at once.

## Acceptance test, checks, out of scope

Written when the part is cut, after the rulings and the scout.
