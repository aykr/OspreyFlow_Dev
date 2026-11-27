# Slice GG3d2 · GG3 · The inspector's writes: a link's notes added, changed and removed as forms, and a link changed with a reason by the module (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** The second half of the plan's GG3d (`slices/drafts_2026-11-26/CHAIN_PLAN.md:76`); its notes follow GG3d1
and GG4c's write pattern (a page `POST` with the anti-forgery token, the Conduit called by the server half, a `303` to a
`GET`); its link change cannot, for the reason question 2 gives.

**Where it comes from.** ADR-075 (notes on links: "only its author changes or removes it"), ADR-080 (a link changed with a
required reason, a supersede kept in the link's history), ADR-102 (the link's handling: raised by an Editor, lowered
only by an Author with a confirmation), ADR-143 decision 5 and C15 (a drawn link is changed on its board, not here).
`FUNCTIONS.yaml` row `inspector` (:213-219: "Inspector (link change, notes, events, risk)"). **Its host is GG2e's live
graph page, so it merges after WS4b** (decision 9), as GG3d1.

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The notes routes** (`services/api/app.py`), each `require_right(EDIT_GRAPH)` and the case **Editor** gate:
  `POST .../links/{edge_id}/notes` (:8749-8769, 201, `LinkNoteBody` `{body}`, `services/api/link_notes.py:89-93`),
  `PUT .../notes/{note_id}` (:8773-8793), `DELETE .../notes/{note_id}` (:8797-8817, 204). Each audited. A note is at
  most 4,000 characters and never empty (`MAX_NOTE_CHARS`, `link_notes.py:51`; :243-245), refused as **422
  `invalid_note`** with the service's sentence (handler `app.py:3589-3593`). Another's note: **403 `note_not_yours`**,
  "Only the person who wrote a note can change or remove it." (:3578-3585); a note not there: **404 `note_not_found`**
  (:3573-3575). A link outside the working set or hidden: **404 `link_not_found`** on every path (`link_notes.py:7-23`).
- **The change route.** `POST .../links/{edge_id}/change` (`change_link_route`, `app.py:7497-7536`):
  `require_right(EDIT_GRAPH)`, the Editor gate, and a second read of whether the caller is the case's **Author**
  (:7516-7520). `LinkChangeRequest` (`services/api/link_changes.py:153-171`, `extra="forbid"`): `reason` (required, at
  most 1,000, :89), and optionally `type`, `properties`, `interval` (`None` on purpose clears it, told apart by
  `model_fields_set`), `occurrences`, `basis`, `handling`, `confirm_lower`. **A change makes a new link**: "The old link
  is kept in the store and replaced in the working set; its notes move to the new one" (:7511-7512); the answer's
  `edge.id` is the new id (`LinkChangeResponse`, `link_changes.py:195-200`), and the delta is published to the stream
  (:7523).
- **Its refusals**, in the order the service checks (`link_changes.py:376-449`, :540-557): `link_not_found` 404; a drawn
  link, **409 `drawn_on_its_board`** (:377-379, handler `app.py:3220-3225`); a case reading a composite, **409
  `composite_read_only`** (`services/api/dataset_scope.py:200-207`, handler `app.py:3768-3776`); no reason or one too
  long, a type not offered, bad properties, **422 `invalid_link_change`** with a sentence (:3539-3543); a same-as link,
  **422 `resolution_link`** (:3555-3559); nothing would change, **422 `nothing_changed`** (:3547-3551); lowering by a
  non-Author, **403 `lowering_needs_author`** (:3519-3525); lowering without the confirmation, **409
  `confirm_lower_handling`** (:3529-3535).
- **What the form's choices come from.** The case's link types: `GET .../link-types` (`case_link_types_route`,
  `app.py:7543-7560`, not audited); the deployment's handling scheme: `GET /v1/handling-scheme` (:13127-13134).
  Which types a link may take between its two ends: `typesFor`, `basisChoicesFor`, `initialDraft`, `toChangeInput` in
  `apps/workspace/src/inspector/linkChangeForm.ts` (React-side, plain functions).
- **The shared clients** are in `packages/glass-shared/src/inspector/`: `linkNotesApi.ts` and `linkChangeApi.ts`
  (`changeLink` :124). **`linkChangeApi.ts`'s `refusal` (:89-114) has no kind for `drawn_on_its_board` or
  `composite_read_only`**: both 409s become "failed" with "request failed: 409". The React inspector shows the generic
  failure today.
- **What a change form needs to know, and where it is.** The link's type and its two ends' types (which types it may
  take, `typesFor`), its marking (which choices lower it), whether it was drawn (`provenance.drawn`, refused here) and
  whether it is a same-as link (refused here). **All are in the working set, which has no HTTP read** (GG3d1's
  question 4): the module holds them in its store; the page service's server half does not. A note needs only the
  link's id.
- **Keyboard.** `LINK_NOTES_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:385-392`, six ids) and
  `LINK_CHANGE_ACTIONS` (:1292-1301, seven ids), with `lower-a-links-handling-with-a-confirmation-by-keyboard` in
  `INSPECTOR_ACTIONS` (:867).
- **Scenario B11** (`spec/08_ACCEPTANCE_SCENARIOS.md:562`): "A `SAME_AS` with score 1.0, provenance `asserted`,
  attributed to the analyst". That is a same-as link, which this route refuses (`resolution_link`); B11 is the link
  menu's, not this slice's.

## Acceptance (red before, green after)

Scenario IN's write rows (GG3d1's scenario), written first, and `apps/pages/test/govuk/inspector-write.test.ts`, red on
GG3d1's page, green after; GG3d1's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **A note added, changed and removed (one's own); a link's type, properties, validity period,
   occurrences, basis and handling changed with a reason.** Not *Define a new type…* (ADR-090's proposal, a later
   slice), not same-as links (the link menu's), not a drawn link (its board's, GG4d). (b) Notes only.
2. **Who draws and sends each write.** (a) **Notes are server forms; the link change is the module's.** A note's form
   posts to GG2e's page path with the anti-forgery token; the server half calls the route; a `303` returns to
   `/cases/graph?case=…&link=<id>`, where GG3d1's server half draws the inspector's id-read parts. **The change form is
   drawn by the module from its store** (type, ends, marking, drawn, same-as) and sent through the `/v1` forwarder with
   `X-CSRF-Token` by the shared `changeLink`; the module then selects the new link (`edge.id`) when the replace delta
   arrives, and says "The link was changed. Its notes moved with it." With scripts off there is no change form, which is
   GG2e's parity line already ("the live working set needs scripts"). (b) **Every write a server form, the change form
   drawn by the server: this needs a Conduit read of one link by id, GG3d1's question 4 (b), the owner's amendment, and
   waits on it.** (c) Notes by the module too: not proposed, since a note needs nothing the server lacks.
3. **Who is offered the forms.** (a) **Offered from `GET /v1/me/rights` and the case's level, as GG4c**: notes and
   change to an Editor holding `EDIT_GRAPH`; a note's change and remove only where `mine`; the handling's lower choices
   only to the case's Author. A hand-sent post is still refused by the route and said in words. (b) Offered to every
   reader, refused after.
4. **Lowering a link's handling.** (a) **Two steps in the module's form: a lower choice shows a confirmation ("This
   lowers the link's marking from … to …. Readers cleared only for the lower marking will see it.") with its own button,
   which sends `confirm_lower: true`.** It names only the link's own marking (from the store) and the chosen one, both
   of which the reader already sees. (b) A checkbox on the form.
5. **The change form's fields.** (a) **Only the fields the link's type has, from the case's link types; a type change
   is two steps in the module's form (choose the type, then its fields), as GG4d's item form; the `PATCH`-like rule kept: only what the person
   changed is sent** (`LinkChangeRequest` treats a field left out as left alone, and `interval: null` as "clear it").
   `typesFor` and `toChangeInput` move to `glass-shared` first (I11), re-imported by the workspace. (b) Every field sent
   each time.
6. **Refusals in words.** (a) **One sentence per code, in `inspectorWords.ts`: the route's own `detail` where it sends a
   sentence meant for a person (`invalid_link_change`, `invalid_note`, `nothing_changed`), and the page's own words for
   the rest** ("This link was drawn on a board: change it there", "This case reads a combined dataset, which cannot be
   changed yet", "Only the person who wrote a note can change or remove it"). The person's text is kept in the form.
   An unknown code is "The link could not be changed. Nothing was saved." **The two 409s the shared client calls
   "failed" get kinds of their own** (`linkChangeApi.ts:89-114`), which the module's change form says, and so does the
   React inspector, whose `LinkChange.tsx` gains the two sentences. (b) Words in the page only, the React inspector
   unchanged.
7. **Removing a note.** (a) **A confirmation page ("Remove this note? It cannot be put back.") then the `DELETE`, then a
   `303` with "The note was removed."** (b) One press.
8. **A note's text and the link's marking.** `link_notes.py:24-28`: a note has no marking of its own and "the Glass says
   so beside the box". (a) **The form says, beside the box, "Anyone who can see this link can read this note. Do not
   write anything marked higher than the link."** (b) Nothing.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Add a note (synthetic text) | one `POST .../notes` with `{body}` only; `303` to `&link=<id>`; the note listed, "you" | `_csrf` passed through in the body |
| 2 | An empty note, and one of 4,001 characters | the route's sentence; the text kept | the 422 shown raw |
| 3 | Change one's own note | one `PUT`; the new text, "changed" with its time | the `PUT` sent to another's note id |
| 4 | Another's note: no change or remove offered; a hand post | refused with "Only the person who wrote…" | the form offered where `mine` is false |
| 5 | Remove, after the confirmation | one `DELETE`; the banner | a remove sent from the first press |
| 6 | Change the type, with a reason | the module's type step, then its fields; one `POST /v1/.../change` through the forwarder with `X-CSRF-Token`, `reason` and `type` only; the **new** link selected when its delta arrives | the old edge id kept as the selection (the next read is 404) |
| 7 | No reason | refused by the module before any call, said in the form | the request sent and the 422 shown raw |
| 8 | Clear the validity period | `interval: null` sent; left out when untouched | `interval` always sent as `null` (every period cleared) |
| 9 | Raise the handling | sent without `confirm_lower`; changed | `confirm_lower: true` always sent |
| 10 | Lower the handling as the Author | the module's confirmation, then `confirm_lower: true` | the lower choice sent at once |
| 11 | Lower choices for an Editor who is not the Author | not offered; a hand post's 403 `lowering_needs_author` said | the lower choices offered to every Editor |
| 12 | A drawn link (no change form drawn: the store's `provenance.drawn`), a hand-sent change, and a case reading a composite | no form for the drawn link; "change it on its board" for the hand send; the composite sentence | either 409 said as "could not be changed" (the shared client's "failed") |
| 13 | A same-as link | no change form offered; a hand post's `resolution_link` said | the form offered for `SAME_AS` |
| 14 | A Viewer, or no `EDIT_GRAPH` | no form; a hand-sent note post said as GR1a's 404 page, a hand-sent change said in the module | the 403 said in words |
| 15 | No `_csrf` on a note post, no `X-CSRF-Token` on a change | refused by the page service, nothing sent (I17) | the route outside the check |
| 16 | The fixture | refuses each code where and in the order the service checks (link, drawn, composite, reason, resolution, nothing changed, lowering) | a fixture that accepts a lowered handling without `confirm_lower` |
| 17 | Keyboard | every `LINK_NOTES_ACTIONS` and `LINK_CHANGE_ACTIONS` id offered here, and the lowering, proven end to end in `keyboard/inspector.spec.ts`; *Define a new type…* listed as later | a step out of the tab order |

## Waits on

GG3d1 (its page parts and the `&link=` read), so GG2e, PL8b and GG3b beneath it; merges only after WS4b (decision 9).
With question 2 (b), also the owner's amendment of GG3d1's question 4 (b).

## Files touched

`spec/08` (IN's write rows); `apps/pages/server/` (GG2e's page: the note post handlers), `server/views/inspectorWords.ts`;
`tree-govuk/` (the note and its remove-confirmation templates); `apps/pages/modules/graph/` (the change form, on the
inspector's attach); `packages/glass-shared/src/inspector/linkChangeApi.ts`
(the two 409 kinds) and `linkChangeForm` helpers moved there (I11), re-imported by `apps/workspace/src/inspector/`; `apps/workspace/src/inspector/LinkChange.tsx` (the two new kinds' sentences);
`test/govuk/inspector-write.test.ts`, `inspectorConduit.ts`, `keyboard/inspector.spec.ts`,
`scripts-off/inspector.spec.ts`; the scenario test's census of `LinkChangeRequest` and `LinkNote`.

## Checks (frozen when cut)

GG3d1's list.

## Out of scope

*Define a new type…* (ADR-090); same-as confirmation (the link menu); a drawn link (GG4d); extraction from an email;
any Conduit change; `apps/workspace` beyond re-imports and `LinkChange.tsx`'s two sentences.
