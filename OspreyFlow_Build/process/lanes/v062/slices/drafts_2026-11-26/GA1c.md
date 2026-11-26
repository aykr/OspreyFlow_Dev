# Slice GA1c · GA1 · Accepting or rejecting a model's proposal on the GOV.UK Ask page, scripts off: accepted is inferred, never confirmed (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **Size S.**

**Where it comes from.** GA1a (drafted 25 November) shows each answer's proposals "in words with its state" and put
"accept and reject … a form each in a later slice, with the anti-forgery token. Accepting writes `inferred`, never
confirmed (rule 5), and the words say so" (its question 5). This is that slice. **Rule 5 holds already in the
Conduit** (`services/api/questions.py:1443-1480`: an accepted proposal is written as `ProvenanceState.INFERRED`); the
page must say it as truly as the Conduit does it.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The routes** (`services/api/app.py`):
  - `POST .../questions/candidates/{candidate_id}/accept` (:8376-8404): `require_right(EXTRACT_FILES)` and the case's
    **Editor** gate; `view_id` as a query field, "found only with that view named, for a reader who may see it"
    (:8391-8394). "Accepts one of the model's proposals: **an inferred node linked to its Document**." Publishes the
    delta to the case's stream; audited `accept_question_candidate`. Answers `QuestionAccepted` (`node_id`, `delta`,
    `questions.py:310-312`).
  - `POST .../questions/candidates/{candidate_id}/reject` (:8407-8432): the same right and gate; "nothing is written";
    audited `reject_question_candidate`; answers `RejectedResponse`.
- **Refusals.** A candidate reviewed already: `CandidateNotPendingError`, **409 `candidate_not_pending`** ("a candidate
  is reviewed exactly once", `services/api/review.py:121-123`; handler `app.py:3917-3923`). A candidate of another unit
  or none: `ExtractionCandidateNotFoundError`, "deliberately, not a 403", the same as missing (`review.py:115-118`;
  handler `app.py:3739`).
- **What the page has.** GA1a's `QuestionAnswer.candidates`: "the proposals of the reader's unit, each an
  `ExtractionCandidateRecord` whose `status` is `pending`, `accepted` or `rejected`" (`review.py:110-112`, :183-188).

## Acceptance (red before, green after)

Scenario AC's review rows, written first, and `apps/pages/test/govuk/ask-review.test.ts`, red on GA1a's page, green after.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Accept and reject, one candidate at a time, on the case's own conversation**; a view's conversation
   (`view_id`) comes with GA1d. (b) Several at once: no route takes several.
2. **When the buttons are offered.** (a) **Only on a `pending` proposal, and only when `GET /v1/me/rights` holds
   `extract_files` and the reader's level in the case is Editor or Author**; a hand post otherwise is said as "You
   cannot review the model's proposals in this case". (b) Always, the refusal after.
3. **The words.** (a) **Accept says what it does before it is pressed: "Accept as inferred: it is added to the case
   marked as the model's, until a person confirms it"**; after it, the proposal reads "accepted, inferred". Reject:
   "Reject: nothing is added". Never "confirm" for accept (rule 5). (b) Your words.
4. **A proposal reviewed already, by someone else meanwhile** (409 `candidate_not_pending`). (a) **"Someone has
   already reviewed this proposal", and the conversation re-read to show its state now.** (b) The 409 as an error.
5. **After a review.** (a) **`303` back to the conversation at that answer** (`#answer-<n>`, a position, not an id),
   with a banner. (b) To the top.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | An Editor with `extract_files` accepts a pending proposal | one `POST .../accept`; `303`; the proposal now "accepted, inferred" | the words "confirmed" (rule 5) |
| 2 | Reject | one `POST .../reject`; "rejected"; nothing added | the accept route called |
| 3 | An accepted or rejected proposal | no buttons | buttons drawn whatever the status |
| 4 | Reviewed meanwhile (the fixture answers 409 `candidate_not_pending`) | the sentence of question 4 and the state now | the 409's body shown |
| 5 | Another unit's candidate, posted by hand | the same 404 page as a missing one | "You cannot review this" (an oracle) |
| 6 | A Viewer, or no `extract_files` | no buttons; a hand post said in words | the buttons drawn from one of the two |
| 7 | No `_csrf` | refused, nothing sent (I17) | the route outside the check |
| 8 | The Conduit gives no answer, or 401 | the 502 page says the review may not have been made and to look again; 401 says to sign in again | "Accepted" on a 502 |
| 9 | One review | exactly one `POST` (one audit row) | a second post on reload (no `303`) |
| 10 | No candidate id in text | the id only in the form's action path | an id printed |
| 11 | Keyboard and scripts off | each button reachable and working (rule 13, I4) | a button out of the tab order |
| 12 | The fixture | refuses in the route's order: the right, the level, the candidate (404), then not pending (409) | a fixture that lets a second review through |

## Files touched

`spec/08` (AC's review rows); `apps/pages/server/ask.ts` (the review `POST`), `server/views/askWords.ts`;
`tree-govuk/ask.njk`; `test/govuk/ask-review.test.ts`, `askConduit.ts`, `keyboard/ask.spec.ts`, `scripts-off/ask.spec.ts`.

## Checks (frozen when cut)

GA1a's list, with `csrf.test.ts` (I17) over the new `POST`.

## Out of scope

A view's proposals (GA1d); a document's own candidates (`.../documents/{id}/candidates`, GG3's); confirming an inferred
node (the inspector's, GG3d); any Conduit change.
