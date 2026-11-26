# Slice GA1b · GA1 · Asking a question on the GOV.UK page, scripts off: what the model will read said first, the question posted once, the answer shown in the case's conversation (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** GA1a (drafted 25 November, not ruled) shows the case's conversation read-only at
`/cases/{case_id}/ask`; its question 1 put asking in GA1b. `spec/02_GLASS_FRONTEND.md` §2.0d, the Ask & Chat drawer and
page (about lines 776 to 856). **Every answer is a model's: what it proposes is `pending` until a person accepts it, and
accepting writes `inferred`, never confirmed (rule 5; `services/api/questions.py:1443-1480`).**

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The routes** (`services/api/app.py`):
  - `POST .../questions` (`ask_question_route`, :8224-8282): `require_right(ASK_MODEL)` and the case's **Editor** gate
    (:8229). Body `AskRequest` (`services/api/questions.py:354-355`): `question` (1 to 2,000 characters,
    `MAX_QUESTION_CHARS` :107) over a `ScopeRequest` (:315-344): `read_from` (`selection`, `graph` or `case`; "none is the
    selection when there is one, else the graph"), `selected_node_ids`, `selected_link_ids`, `window`, `engine` (`local`
    or an enabled provider's name; "none is the role's default"), `view_id`. Asked inside `model_calls.attributed`
    (SE8a); audited `ask_question`; answers one `QuestionAnswer` with `author_name` resolved (:8280-8281). **One
    synchronous call.**
  - `POST .../questions/will-read` (:8285-8300): the same right and gate, `WillReadRequest` (the scope, and the question
    as typed so far under *Whole case*, ADR-098 Amendment 9); nothing is sent to a model.
- **The bounds.** "The Conduit stops a hosted engine at its own bound (120 seconds by default) and the deployment's own
  model at 900, each said in words"; the Glass's backstop is 16 minutes with the words "No answer came back within 16
  minutes, so this stopped waiting. The server may still finish: look again in a moment before asking again."
  (`packages/glass-shared/src/models/modelDeadline.ts:1-12`). The page service's upstream timeout is 3,600 seconds by
  default (`apps/pages/server/config.ts:168-189`). In the forwarder it is a timeout for silence (`config.ts:73`), but the
  **server half's own client gives each call a whole-call `AbortSignal.timeout`** (`apps/pages/server/conduit.ts:70`),
  turned into `ConduitUnreachable` (a 502), and a `Call` takes no signal of its own (:26-33). So it does not cut a
  900-second call, but **the 16-minute deadline of question 3 needs a change to `conduit.ts`** (a signal per call).
- **"Everything on the graph" is the case's working set**, which the Conduit keeps once per case, shared by the case's
  members and projected for each reader through their own access (`services/api/working_set/service.py:1-30`), and
  which the React canvas fills. A GOV.UK reader with no canvas page cannot see what that set holds, so cannot know what
  "Everything on the graph" would read.
- **The right's comment.** `packages/schemas/rights.py:38`: `ASK_MODEL = "ask_model"  # I7, Viewer`, while both routes
  need the Editor level (GA1a's question 6).
- **The React form.** `apps/workspace/src/questions/QuestionsPanel.tsx`: *will read* debounced after each change
  (`WILL_READ_DEBOUNCE_MS` :245; :252, :271, :532), "Working out what will be read…" (:471), "Will read: …" (:477),
  "Asking…" while in flight (:543); `ask()` (:254-277).

## Acceptance (red before, green after)

Scenario AC's asking rows (after GA1a's), written first, and `apps/pages/test/govuk/ask-post.test.ts`, red on GA1a's
page, green after; GA1a's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **What the reader may ask over, with no canvas.** (a) **"The whole case" only** (`read_from: "case"`), sent
   explicitly; "Selected items" and "Everything on the graph" are offered once GG2e puts the working set on a page.
   (b) All three, "Everything on the graph" meaning the working set the person last had in the React workspace. **Not
   proposed:** a GOV.UK reader cannot see that set.
2. **Will read, scripts off.** (a) **Two steps: "Check what will be read" posts the question to `will-read` and shows
   the answer above the form with the question kept; "Ask" posts the question.** A reader may ask without checking.
   (b) Ask only.
3. **The wait.** (a) **The form's post waits for the answer** (the server half holds the call, up to the Conduit's own
   bounds), then `303`s to the conversation with the new answer in place; **the button's words say before it is
   pressed: "The model may take up to 15 minutes to answer. Keep this page open."** If no answer comes in 16 minutes,
   the page says `MODEL_DEADLINE_WORDS` and links to the conversation. The builder reads the front proxy's own timeouts
   in each shape; **if any cuts a request under 16 minutes, that is a stop** (a harness change, the owner's). (b) An
   asynchronous ask: a Conduit change (decision 11), not proposed.
4. **The engine.** (a) **The role's default, not chosen on the page in GA1b**; the answer already says which engine and
   model answered (GA1a). A choice of engine (`GET /v1/models/engines` for the case) is a later slice. (b) A choice now.
5. **The right.** (a) **The Editor level, as the routes are; the form is offered when `GET /v1/me/rights` holds
   `ask_model` and the reader's level in the case (GR1a's case page reads it) is Editor or Author**, and
   `rights.py:38`'s comment is corrected by the orchestrator (shared `packages/schemas`), not by this lane. (b) Viewers may ask: a Conduit change. **Your
   word, since GA1a's question 6 asks it.**
6. **A refusal from the model's side** (an engine down, a bound reached, the Conduit's words). (a) **Said in the error
   summary in the Conduit's own words, which are already written for people** (ADR-135 Amendment 13 (a)), the question
   kept in the field. (b) The page's own words.
7. **Twice.** (a) **One ask per post, and a reload of the result page sends nothing** (`303`); a second press while the
   first is waiting is the browser's second request, which the page cannot stop with scripts off, so the button's words
   say "Press once". (b) A one-time token per question form, refused the second time.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | An Editor asks "Who rented the unit in March?" (synthetic) | one `POST .../questions` with `question` and `read_from: "case"` only; `303` to the conversation; the answer there | `read_from` left out (the route then reads the working set) |
| 2 | Check what will be read first | one `POST .../will-read`; its answer above the form in words; the question kept | the check sent to `POST .../questions` |
| 3 | A question of 2,001 characters, or empty | the error summary, the words kept, nothing sent | the post sent and the 422 shown |
| 4 | A Viewer | no form; a hand post said as "You cannot ask questions in this case" | the form drawn from `ask_model` alone |
| 5 | A reader without `ask_model` | the same | the form drawn from the level alone |
| 6 | The engine's bound reached (the Conduit's words) | the error summary in those words; the question kept | a generic "something went wrong" |
| 7 | No answer in 16 minutes (the fixture silent) | `MODEL_DEADLINE_WORDS` and a link to the conversation | the page left waiting |
| 8 | The answer's proposals | shown as GA1a shows them, "proposed by the model, not yet reviewed" | a proposal drawn as a fact (rule 5) |
| 9 | No `_csrf` | refused, nothing sent (I17) | the route outside the check |
| 10 | The Conduit gives no answer, or 401 | the 502 page says the question may not have been asked, and to look at the conversation first; 401 says to sign in again | "Your question was asked" on a 502 |
| 11 | One question | exactly one `POST` (one model call, one audit row) | a will-read sent on every ask as well |
| 12 | Keyboard and scripts off | both buttons reachable and working; the ask completes (rule 13, I4) | a button out of the tab order |
| 13 | The fixture | refuses as the route does, in its order (the right, the level, the body), and is silent when told, to model a bound | a fixture that answers a Viewer |

## Files touched

`spec/08` (AC's asking rows); `apps/pages/server/ask.ts` (GA1a's, the `POST` half), `server/views/askWords.ts`;
`tree-govuk/ask.njk`; `test/govuk/ask-post.test.ts`, `askConduit.ts`, `keyboard/ask.spec.ts`, `scripts-off/ask.spec.ts`;
the scenario test's census of `AskRequest` and `WillReadRequest` (the selection, window, engine and view named as left
out); `apps/pages/server/conduit.ts` (a per-call signal, for question 3's deadline). **`packages/schemas/rights.py`'s
comment is code in the shared schemas package, which goes through the orchestrator, not this lane**: question 5 (a) asks
the orchestrator to correct it.

## Checks (frozen when cut)

GA1a's list, with `csrf.test.ts` (I17) over the new `POST`; the harness's proxy timeouts read in each shape (question
3), reported, not changed.

## Out of scope

Accepting and rejecting proposals (GA1c); a view's conversation (GA1d); asking about a selection (GG2e); a choice of
engine; any Conduit change; `apps/workspace`.
