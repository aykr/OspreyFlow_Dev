# Slice GG4h · GG4 · The Ownership view on the GOV.UK pages: who ultimately owns or controls an entity, and its due diligence, read-only, scripts off (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** **The Matrix is not here**: the owner ruled it GG2d's (26 November, about 10:35 UTC, `RULINGS.md` :68).

**Where it comes from.** `FUNCTIONS.yaml` row `matrix-ownership` ("Matrix and Ownership views",
`apps/pages/FUNCTIONS.yaml:268-274`, slice R6, no scenario). ADR-109 phase C (ownership) and phase F (due diligence),
`spec/06_DECISIONS.md` :11170 onward; `spec/02_GLASS_FRONTEND.md` :1654-1668, which words the whole place: found by name
"(the case's own suggest)", "a line naming the beneficial owners at the threshold (25% unless changed …)", "a warning for
each circle of cross-holdings ('traced once, not round and round')", "a table of every party with a chain to the entity
… its chains, each in words, owner first, with every link's percentage ('share not stated', 'controls') and the chain's
product", "*Show the structure on the canvas* … (Editor)", "**Nothing it shows is written to the graph.**" Scenario C5
(`spec/08` :683).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py:14799-14957`), **each behind `TRACE_OWNERSHIP` alone**
  (:14804, :14831, :14873, :14900), not `INVESTIGATE` (a right of the Analyst's set, "L7, Viewer",
  `packages/schemas/rights.py:55`, :113; **the Data Engineer's set does not hold it**, :116-123):
  - `GET .../ownership/{node_id}?threshold=` (`trace_ownership_route`, :14802-14826), Viewer gate, `threshold` above 0
    and at most 100, default 25: `OwnershipView` (`packages/schemas/compute.py:189-196`): `trace` (`OwnershipTrace`:
    `target`, `threshold`, `owners` largest known share first, `cycles`), `nodes`, `edges`. Each `OwnerTrace`
    (:166-178): `node_id`, `node_type`, `cumulative_percent` ("a lower bound when `share_unknown`"), `share_unknown`,
    `controls`, `paths` (`OwnershipPath`: `link_ids`, `kind` ownership, unknown or control, `share`), `beneficial_owner`,
    `possible_beneficial_owner`. Audited `trace_ownership`.
  - `POST .../ownership/{node_id}/canvas` (:14829-14868), **Editor**: seeds the working set (`working_set.seed`,
    `publish_delta`, a history step). **A write.**
  - `GET .../kyc/{node_id}` (:14871-14895), Viewer gate: `KycStatus` (`packages/schemas/domain.py:1958-1971`): `name`,
    `status`, `documents` (`KycDocument`: `node_id`, `title`, `document_kind`, `expires_on`, `state`), `risk_score`,
    `risk_band`, `factors` (`RiskFactor`: `factor`, `weight`, `words`), `assessed_on`; "computed at each read, as the
    reader reads the graph, never stored". 422 `kyc_not_applicable` for another type (:14943-14948).
  - `GET .../risk/{node_id}` (neighbourhood risk, :14898-14931): the inspector's, not this place's.
- **How the trace reads** (`services/api/ownership.py`): up from the target over `BENEFICIAL_OWNER_OF` and `CONTROLS`
  with `GraphPort.expand`, "the access step in every traversal: a party or link the reader may not see is not in the
  structure, and the trace is exactly what it would be were they absent" (:3-6); one layer more than `max_depth` so a
  deeper chain is refused whole, "never traced in part" (:56-58); **more than `MAX_PARTIES = 500` parties, or deeper
  than ten layers, is 409 `ownership_too_complex`** in words (:76-80, `app.py:14951-14957`); a target the reader cannot
  see is 404 `node_not_found` (`ownership.py:50-52`; `app.py:6436-6440`). The principal is scoped to the case's datasets
  (`services/api/dataset_scope.py:3-6`).
- **Finding the entity.** The React place finds it by name with `POST .../suggest`
  (`packages/glass-shared/src/ownership/api.ts:37-44`; `app.py:6743-6789`, which needs `INVESTIGATE`), traces anything
  but a Person, and asks KYC for a Person or an Organisation
  (`apps/workspace/src/ownership/OwnershipPlace.tsx:66-88`). Its words: `describeChain` ("Petrov → Aegean Fiduciary
  Trust (60%) → …", :27-40), `ownerNotes` ("Beneficial owner", "Possible beneficial owner — share partly unknown",
  "Controls", "Share partly unknown", :42-49), "Nothing by that name in this case.", "No natural person reaches the
  {threshold} threshold or holds control, in what you can see.", "A circle of cross-holdings: … — traced once, not round
  and round." Its keyboard cases: `apps/workspace/keyboard/ownership.spec.ts`, registry `OWNERSHIP_ACTIONS`.
- **The page service already reads the reader's rights**: the Studio's frame reads `GET /v1/me/rights`
  (`apps/pages/server/studio.ts:207`; `app.py:20664`), the pattern question 3 follows.

## Acceptance (red before, green after)

A new scenario, **OW** ("Who owns an entity, and its due diligence, as a GOV.UK page, read-only"), written first in
`spec/08`, and `apps/pages/test/govuk/ownership.test.ts`, red before the page exists, green after.

## Questions for the owner (the proposal first)

0. **Starting before GG2e.** The plan's row says GG4h needs GG2e, for the canvas action alone. (a) **Read-only, drawing
   nothing, it starts after GR1a**, the canvas action coming with GG2f. (b) Wait for GG2e.
0b. **Merging before WS4b** **(owner: decision 9).** CHAIN_PLAN (:108-109) counts GG4g to GG4i among the slices decision 9
   holds. This page draws nothing with Sigma and its row is R6, not R4, but whether decision 9 holds it is the owner's
   reading. (a) **It merges when ready, before WS4b**, by the owner's word. (b) It waits for WS4b, as the plan counted it.
1. **Scope.** (a) **Find by name, the ownership trace and the due diligence, read-only**, as `spec/02` words them. *Show
   the structure on the canvas* waits for GG2f (it writes the working set). Neighbourhood risk is the inspector's (GG3d).
   (b) The trace only.
2. **Where it sits.** One page per `FUNCTIONS.yaml` row. (a) **`/cases/ownership?case=<id>` (find) and
   `&node=<id>&threshold=<n>` (the trace), under a new row `ownership`; `matrix-ownership` narrows to the Matrix
   (GG2d's)**, as GR4a's board page was given its own row; whichever of GG2d and GG4h merges second takes both sides. (b)
   One row, the Matrix and Ownership as two parts of one page.
3. **Offered to whom.** The routes ask `trace_ownership`, which a Data Engineer does not hold. (a) **The case's page links
   to Ownership only when `GET /v1/me/rights` holds `trace_ownership`** (the pattern `studio.ts:207` already follows), and the routes' refusal is GR1a's
   404 page. (b) Always linked; refused after.
4. **Which entities are traced.** (a) **As the React place: a Person gets its due diligence and no trace; an
   Organisation both; any other type (an account) the trace alone**; `kyc_not_applicable` is never asked for. (b) Every
   type traced, a Person's trace said empty.
5. **The threshold.** (a) **A number field, 25 by default; a value outside above 0 to 100 is refused on the page in the
   React place's words ("The threshold is a percentage above 0 and at most 100.") before any read**, kept in the address
   for a reload. (b) Fixed at 25.
6. **The owners table.** (a) **One row per `OwnerTrace` in the route's order: the party's name (from `nodes`), its type,
   its cumulative share ("at least 37.5%" when `share_unknown`), its notes (`ownerNotes`' words), and its chains in words
   (`describeChain`'s), each a list item**; the beneficial-owners line above it; each cycle's warning. `describeChain` and
   `ownerNotes` move to `glass-shared` first (I11: the words are not written again), unchanged, the React suite as the
   gate. (b) Written again in the page.
7. **Due diligence.** (a) **A summary list: verified or not, the risk band and score, each factor's words and weight,
   each verifying document by its title, kind, expiry and state; never a document's `node_id`.** (b) The status alone.
8. **Too complex.** (a) **The route's 409 `ownership_too_complex` said in its own words ("more than 500 parties own or
   control this entity; the structure is not traced in part"), with no table and no first part** (rule 2). (b) A page
   sentence of its own.
9. **Ids.** (a) **The target's id only in the trace link's query and the threshold form's hidden field; no party's or
   link's id on the page** (rule 7; GG4a's rule for ids in a link). (b) Your words.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Find "Aegean" (synthetic) | one `POST .../suggest`; each match a link to its trace; "Nothing by that name in this case." when none | the matches drawn with their ids |
| 2 | An organisation owned 60% by a trust owned 100% by a person | "Beneficial owners at 25%: A. Petrov"; the person's row "60%", "Beneficial owner", the chain "A. Petrov → Aegean Fiduciary Trust (100%) → Halcyon Shipping (60%)" | the share recomputed in the page rather than read from `cumulative_percent` |
| 3 | A link with no stated percentage | "at least 30%", "Possible beneficial owner — share partly unknown", "share not stated" in the chain | `share_unknown` read and dropped |
| 4 | A control link | "Controls"; "controls" in the chain; counted as a beneficial owner whatever the share | control said as a share |
| 5 | A circle of cross-holdings | the warning naming its parties, "traced once, not round and round" | the cycle drawn twice in the chains |
| 6 | A party the reader may not see (the fixture leaves it out of the structure, as the route does) | the trace as if it were absent: no row, no gap, no "hidden" line, no count | a placeholder row for a party named in `link_ids` but missing from `nodes` (a body like that is "could not be read", never a gap) |
| 7 | The threshold 40 | one `GET .../ownership/{id}?threshold=40`; the line says 40% | the threshold kept at 25 |
| 8 | The threshold 0 or 150 | the React sentence; nothing asked | the 422 shown raw |
| 9 | 409 `ownership_too_complex` | its words; no table | a first part of the structure drawn |
| 10 | A Person | its due diligence; no trace asked | a trace asked for the Person |
| 11 | Due diligence of an organisation | status, band, score, each factor and each document's title, kind, expiry and state | a document's `node_id` printed |
| 12 | A reader without `trace_ownership` | no link on the case's page; the page's routes' 403 is GR1a's 404 page | the 403 said in words |
| 13 | A target the reader cannot see (404 `node_not_found`) | GR1a's 404 page | "not found" said differently from a missing case |
| 14 | One render | one `GET` of the trace and at most one of KYC | a read per owner |
| 15 | A body missing a field `OwnershipView`, `OwnershipTrace`, `OwnerTrace`, `OwnershipPath`, `KycStatus`, `KycDocument` or `RiskFactor` requires; a path naming a link not in `edges` | "could not be read" | each required field removed in turn |
| 16 | The moved words | the React Ownership place's suite green, unchanged, after `describeChain` and `ownerNotes` move | a word changed in the move |
| 17 | Keyboard and scripts off | the find form, each trace link and the threshold form reachable and working (rule 13), the page whole with scripts off (I4) | a link out of the tab order |

## Waits on

GR1a merged (the case's page); GG2d, which also changes the `matrix-ownership` row (question 2: whichever merges second
takes both sides); question 0b for the merge before WS4b.

## Files touched

`spec/08` (scenario OW); `packages/glass-shared/src/ownership/` (`describeChain`, `ownerNotes` moved, with their tests),
`apps/workspace/src/ownership/OwnershipPlace.tsx` (imports only); `apps/pages/server/ownership.ts` (new),
`server/pageList.ts`, `server/views/ownershipWords.ts`; `tree-govuk/ownership.njk`, `routes.yaml`, `cases.njk` (the
link); `apps/pages/FUNCTIONS.yaml` (the new `ownership` row; `matrix-ownership` narrowed); `test/govuk/ownership.test.ts`,
`ownershipConduit.ts`, `keyboard/ownership.spec.ts`, `scripts-off/ownership.spec.ts`;
`tests/harness/test_pages_setting.py`'s route list; a scenario census test in `OspreyFlow_Build/tests/glass_trees/`.

## Checks (frozen when cut)

GR1a's list, and the React workspace's suite for the moved words (I11).

## Out of scope

*Show the structure on the canvas* (with GG2f); neighbourhood risk (GG3d's); the Matrix (GG2d's); the KYC rules (the
alerts row's); any Conduit change.
