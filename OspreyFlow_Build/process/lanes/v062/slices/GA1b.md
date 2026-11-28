# Slice GA1b · GA1 · Asking a question on the case's GOV.UK Ask page, scripts off: what the model will read said first, the question posted once, the answer shown in the case's conversation

- **Build id:** GA1 (the `ask-chat` row, `apps/pages/FUNCTIONS.yaml:237-243`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round**, a second only for the verifier's findings
- **After:** GA1a (the Ask page at `/cases/ask?case=<id>`, cut and refrozen 28 November, not merged). GR1a is merged.
  **No hold by decision 9:** the page draws nothing, and the `ask-chat` row is R5.
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. **The owner's two answers are in:** "GA1b: Editor (fix `ASK_MODEL`'s comment); Q3 (a): a front-proxy
  timeout under 16 minutes is a stop" (26 November, about 10:35 UTC). No question is left for him unless that stop is
  met.

## What

On GA1a's page, an Editor of the case who holds `ask_model` can ask the model a question with scripts off:
1. They type it and may first press *Check what will be read*.
2. They press *Ask*.
3. The page waits for the answer and returns them to the conversation, with the new answer in place.

Every answer is a model's: what it proposes stays `pending` until a person accepts it (GA1c), and accepting writes
`inferred`, never confirmed (rule 5; `services/api/questions.py:1443-1480`, `ProvenanceState.INFERRED` at :1465).
GOV.UK page only. **Who asked is left out**, as GA1a leaves it (the owner, 27 November: "there is no exception").

**The answers (each (a) unless ruled, and why):**

1. **(a) "The whole case" only:** `read_from: "case"`, sent explicitly. "Selected items" and "Everything on the graph"
   come with the live page (GG2e1, GA1e). Why (a): "everything on the graph" is the case's working set, which a GOV.UK
   reader cannot see yet, so they could not know what it would read. Leaving `read_from` out would read the selection
   or the graph (`ScopeRequest`, `questions.py:315-344`, :320).
2. **(a) Two buttons.**
   - *Check what will be read* posts the question to `POST .../questions/will-read` (`services/api/app.py:8295-8342`;
     `WillReadRequest`, `questions.py:347-351`). Nothing is sent to a model.
   - The answer is shown in words above the form, with the question kept.
   - *Ask* posts `POST .../questions`. A reader may ask without checking.
   - Why (a): the workspace's debounced will-read (`apps/workspace/src/questions/QuestionsPanel.tsx:245`) needs a
     script, and this is its form without one.
3. **Ruled (a): the post waits.**
   - The server half holds the call, up to the Conduit's own bounds: 120 seconds for a hosted engine and 900 for the
     deployment's model (`OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS`, `OSPREY_MODEL_TIMEOUT_SECONDS`,
     `harness/render.py:181-184`).
   - Then it `303`s to the conversation.
   - The button's words say before it is pressed: "The model may take up to 15 minutes to answer. Keep this page open,
     and press Ask once."
   - With no answer in 16 minutes, the page says `MODEL_DEADLINE_WORDS`
     (`packages/glass-shared/src/models/modelDeadline.ts:10-12`) and links to the conversation.
   - **That needs a per-call signal in `apps/pages/server/conduit.ts`.**
     - Today a `Call` takes no signal (:26-33), and every call gets one whole-call `AbortSignal.timeout` of the page
       service's upstream setting, 3,600 seconds by default (:70; `server/config.ts:168-190`), turned into
       `ConduitUnreachable` (:36-38, :74).
     - The ask's call gets its own 16-minute signal (`MODEL_DEADLINE_MS`, :8), and every other call is unchanged.
   - **The stop (ruled):** the builder reads every shape's front proxy and the page service's own server for a timeout
     that would cut a request under 16 minutes. These are:
     - the workspace's nginx, `proxy_read_timeout 1h` (`apps/workspace/nginx.conf.template:92-93`);
     - the cloud ingress, the same 1 h (`harness/cloud_platform/__init__.py:948-952`);
     - Caddy in the local and cluster shapes, where no timeout is written (`harness/site.py:120-144`). The builder
       reads Caddy's own default for `reverse_proxy` from the pinned version's documentation and records it;
     - the page service's Node server: `requestTimeout: 0` and `server.timeout = 0`, with a headers timeout
       (`apps/pages/server/start.ts:129-132`);
     - Helm, where no timeout is set (`deploy/helm/ospreyflow/values.yaml`).

     **If any of these cuts a request under 16 minutes, stop and bring it: a harness change is the owner's.**
4. **(a) The role's default engine**, not chosen on the page. The answer already says which engine and model answered
   (GA1a). Why (a): choosing an engine is its own slice, and the default is the one the Conduit picks.
5. **Ruled: Editor.**
   - The routes need `ASK_MODEL` and the case's Editor level (`app.py:8234-8239`, `InvestigationEditorDep`; will-read
     :8295-8300).
   - The form is offered when `GET /v1/me/rights` holds `ask_model` and the reader's level in the case is Editor or
     Author. The page reads the level as GR1a's case page reads it, from the case list (`apps/pages/server/cases.ts:8-9`).
   - A hand post otherwise is said as "You cannot ask questions in this case". The route refuses all the same.
   - **`ASK_MODEL`'s comment** (`OspreyFlow_Core/packages/schemas/rights.py:38`, today `# I7, Viewer`) **is corrected by
     GA1a** (its ruling 6; GA1a's brief names the path `services/api/rights.py`, which does not exist). If GA1a merges
     without the correction, GA1b makes it, a comment only, and says so.
6. **(a) A refusal from the model's side** (an engine down, a bound reached) is said in the error summary in the
   Conduit's own words, which are written for people (ADR-135 Amendment 13 (a)), with the question kept in the field.
   Why (a): one set of words for the same refusal in both front ends.
7. **(a) One ask per post.**
   - The `303` means a reload of the result page sends nothing.
   - A second press while the first waits is the browser's second request, which the page cannot stop with scripts
     off, so the button's words say "press Ask once".
   - Why (a): a one-time token per question form is a new anti-replay mechanism, more than this slice needs.

## What exists today (re-read at `b79164850`)

- **`POST .../questions`** (`ask_question_route`, `app.py:8234-8292`):
  - `require_right(ASK_MODEL)` (:8236) and `InvestigationEditorDep` (:8239);
  - asked inside `model_calls.attributed` (:8264-8266) and audited `ask_question` (:8282);
  - answers one `QuestionAnswer` (`questions.py:283-307`), with `author_name` resolved (:8291-8292), which the page
    leaves out.
  - **One synchronous call.** `AskRequest` (`questions.py:354-355`) is `question` (1 to 2,000 characters,
    `MAX_QUESTION_CHARS` :107) over `ScopeRequest`.
- **The anti-forgery check** covers every page `POST` (`apps/pages/server/app.ts:412`, `csrf.ts:13`). Its test is
  `apps/pages/test/server/csrf.test.ts:41-82`.
- **The write pattern:** GR1b's New case (`server/cases.ts:155-178`): a guard; one Conduit `POST`; a `303`; a one-time
  banner kept in the session (:176) and read at :231.
- **GA1a's files are not on main.** The page module, its words (`server/views/askWords.ts`, which GA1a's refreeze
  names), its template and its fixture are GA1a's. This part adds to them.

## Round 1's steps

1. Write Scenario AC's asking rows (after GA1a's) and the acceptance test first. Show them red on GA1a's page: no form,
   no `POST`.
2. Add the per-call signal to `conduit.ts`, red first: a planted whole-call timeout of 3,600 seconds still cuts the ask
   at 16 minutes in a fake clock.
3. Add `POST` to GA1a's page module, with two actions (`check` and `ask`) dispatched by the form's button, each one
   Conduit call. Add the words in `askWords.ts` and the form in the template.
4. Make the fixture Conduit refuse in the routes' order (the right, the level, the body), and fall silent when told to,
   to model a bound.
5. **Read every timeout of item 3 and record them in the report.** Stop if one is under 16 minutes.
6. Add the keyboard and scripts-off cases. Run the checks and every plant.

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/ask-post.test.ts` (new; vitest) and GA1a's
`OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py`, extended with AC's asking rows. The scenario test's
census over `AskRequest` and `WillReadRequest` names the selection, window, engine and view as left out. Both are red
on main.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | An Editor with `ask_model` asks "Who rented the unit in March?" (synthetic) | one `POST .../questions` whose body is exactly `question` and `read_from: "case"`; `303` to the conversation; the answer there | `read_from` left out (the route would read the working set) |
| 2 | *Check what will be read* | one `POST .../will-read`; its answer above the form in words; the question kept; no model call | the check sent to `POST .../questions` |
| 3 | A question of 2,001 characters, or empty | the error summary, the words kept, nothing sent | the post sent and the route's 422 shown |
| 4 | A Viewer | no form; a hand post said as "You cannot ask questions in this case" | the form drawn from `ask_model` alone |
| 5 | An Editor without `ask_model` | the same | the form drawn from the level alone |
| 6 | The engine's bound reached (the Conduit's words) | the error summary in those words; the question kept | a generic "something went wrong" |
| 7 | No answer in 16 minutes (the fixture silent, a fake clock) | `MODEL_DEADLINE_WORDS` and a link to the conversation | the call left on the upstream setting's 3,600 seconds |
| 8 | The answer's proposals | shown as GA1a shows them, "proposed by the model, not yet reviewed" | a proposal drawn as a fact (rule 5) |
| 9 | No `_csrf` | refused, nothing sent (I17) | the `POST` outside the check |
| 10 | The Conduit gives no answer, or 401 | the 502 page says the question may not have been asked and to look at the conversation first; 401 says sign in again | "Your question was asked" on a 502 |
| 11 | One question | exactly one `POST` (one model call, one audit row) | a will-read sent on every ask as well |
| 12 | Keyboard and scripts off | both buttons reachable and working; the ask completes (rule 13, I4) | a button out of the tab order |
| 13 | The fixture | refuses as the route does, in its order (the right, the level, the body) | a fixture that answers a Viewer |
| 14 | Every other Conduit call | still bounded by the upstream setting, unchanged | the 16-minute signal given to every call |
| 15 | The asker | not shown; `author` and `author_name` named as left out in the census | the answer's `author_name` printed |

## Checks

GA1a's row's refrozen checks, with `test/server/csrf.test.ts` over the new `POST`, run by the pages workspace tests.

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario AC's asking rows, after GA1a's rows** in AC (GA1a's new section). GA1c's
and GA1d's rows follow.

## Out of scope

- accepting and rejecting (GA1c);
- a view's conversation (GA1d);
- asking about a selection or the graph (GA1e, GG2e1);
- a choice of engine;
- any Conduit change;
- any harness change (a stop);
- `apps/workspace`;
- the Default tree.

## Proposed `slices.tsv` row (not added)

```
GA1b	GA1	Asking a question on GA1a's Ask page, scripts off: Check what will be read first, then one POST over the whole case (read_from "case"), waiting up to the Conduit's bounds with a 16-minute per-call signal in conduit.ts, then a 303 to the answer; Editor with ask_model only; a front-proxy timeout under 16 minutes is a stop (the owner, 26 November: Editor, Q3 (a); the rest standing (a), D274; draft drafts_2026-11-28)	GA1a	2	lane/slice-GA1b	full	OspreyFlow_Core/apps/pages/test/govuk/ask-post.test.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/ask-post.test.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1b uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1b uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1b uv run --frozen ruff check .
```
