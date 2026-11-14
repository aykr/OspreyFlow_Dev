# rules-b · v052D(iii) · *Whole case* through the search service · plan (14 November 2026)

Prepared offline while studio's search (`lane/studio-search`, ADR-149) waits for main. It is built when that lands.
The code is written against the frozen shape (`process/lanes/studio/SEARCH_RESPONSE_SHAPE.md`, frozen at ee7a16d,
note 5) and `packages/schemas/search.py` as built on studio's branch (47e9213). Nothing here imports studio's
modules until they are on main.

Brief (`BRIEF_v052D.md` § D(iii)):
1. Call the search service with the question's words.
2. Take the top results the person may see as numbered sources, and cite each one (a new citation kind).
3. Say in one line that it finds things by names and words.
4. Extend studio's leak test to Ask's sources.

If it cannot be ready by the freeze (Tue 24 Nov), tell the orchestrator. The owner decides before it is shown as
unavailable.

## How it reads

- **The same service, in-process, not a second route** (shape note 5). `questions.py` takes a `CaseSearch`
  callable, built in `app.py` from the dependencies `search_route` already uses (`SearchIndexDep`,
  `SearchPendingDep`, `SearchWorkingSetDep`, `DatasetsDep`) and `search_service.search_page`. It is called as
  the asker's own principal, so the access filter goes into the index query (rule 3). A hidden record is never
  counted, read or cited, because it never comes back.
- **The request**: `query` is the question's text, with `group: null`, `page: 1` and `page_size: 50` (the shape's
  ceiling for Ask), and no filters. *Everything on the graph*'s timeline window is not applied: Whole case is the
  case, not the canvas.
- **Too long a question**: the search takes 1–200 characters and a question 1–2,000. Over 200 characters, Whole
  case is refused in words: "Whole case searches with your question's own words, at most 200 characters. Shorten
  the question, or choose Everything on the graph." The question is never cut (rule 2). *Strict option, logged.*
- **Sources**:
  - Results with `is_document` become the numbered documents `[n]`, as today. Each document's full text is read
    through the existing document reader, which checks access again (note 5), inside the same character
    allowance as the other read-froms. Past it: `limit_exceeded`, never trimmed.
  - Every other result is a numbered **search source `[S-n]`**, the new citation kind. It gives the record's
    canvas label (`canvas_label`), its type and the Conduit's `match.why` ("Sounds like 'Kestrel'"), and stands
    for its `node_ids` (a merged entity's visible members only).
  - A cited `[S-n]` the brief does not hold is dropped and counted, like an unplaced `[G-n]`.
- **The one line**, on the panel under *Whole case* and on the read line of an answer read that way: "Whole case
  finds things by their names and words, not by what they mean."
- **On the fallback** (`source: "fallback"`), the search's `limited_reason` is shown as given, and the read
  summary carries it. "Counts may be incomplete" when `counts_exact` is false.
- **No results**: refused as `nothing_to_read`: "Nothing in the case matches your question's words. Try names or
  words the records hold, or choose Everything on the graph."

## What changes

| Where | Change |
| --- | --- |
| `packages/schemas/questions.py` (shared commit, last) | `ReadSummary.read_from` gains `"case"`; it adds `found: int` (the search results read), `limited_reason: str \| None` and `counts_exact: bool`. All of them are required, as before. A new `SearchCitation`: `n`, `node_ids`, `label`, `type`, `why`. |
| `services/api/questions.py` | `ReadFrom` adds `"case"`, through `_gather_case`. `ReadFromUnavailableError` stays, for a deployment where search is not wired, as "Whole case is not available on this deployment". The brief section "Records found by search" is numbered `[S-n]`; `search_citations` go on the entry and the answer, with an `ALTER TABLE … ADD COLUMN IF NOT EXISTS search_citations JSONB NOT NULL DEFAULT '[]'`. |
| `services/api/app.py` | `CaseSearch` is wired from the search dependencies. Ask and will-read are audited as now; the search itself writes no second `search` audit row, since the question's own row records `read_from: case`. |
| Glass, `src/questions/**` | *Whole case* is enabled. The one line goes under it, the read line shows the fallback reason, and `[S-n]` buttons select the result's `node_ids` on the canvas, as `[G-n]` does (seeding them through `POST /seed` if they are not on the canvas). |
| Keyboard | `questions.spec.ts`: Whole case chosen by arrow keys, and an `[S-n]` activated by Enter, selecting its records. One new id, `select-a-search-source-from-an-answer-by-keyboard`, sent in `registry-v052Diii.patch`. |

## Tests, red first (each planted at its real call site, with a fresh `PYTHONPYCACHEPREFIX`)

- **Offline** (`test_questions_whole_case.py`). The fake `CaseSearch` refuses what `search_page` refuses: over
  200 characters, `page_size` over 50 and a dataset outside the case, each with a 422 (rule 15's refusals). The
  cases:
  - the question's words are sent unchanged;
  - an over-long question is refused in words, not cut;
  - only the results that come back are read, counted and cited;
  - a document result is read through the reader, and a document the reader refuses is not read;
  - `[S-n]` carries `node_ids`, and an `[S-n]` the brief lacks is dropped;
  - the fallback's words reach the read summary;
  - no results is refused in words;
  - will-read counts what ask then reads;
  - the read summary is kept and read back.
- **Rule 4, live** (`tests/services/search_index/test_ask_whole_case_leak_live.py`, a new file reusing studio's
  worlds; studio's own file is not edited). A reader asks the same question with the hidden records present and
  absent. The brief sent to the model, the read summary and the citations must be identical. It is red with the
  access filter dropped from Ask's call.
- **The route's rights**: will-read and ask with `read_from: case` keep `ASK_MODEL` and Editor. They are refused
  in a private view to another member, as now.
- **Axe**: the panel with Whole case chosen and the fallback line showing, in dark, light and GOV.UK.

## Amendments to reserve (asked of the orchestrator)

- **ADR-098 Amendment 9**: Whole case reads the case through the search service, with the question's words. The
  200-character limit refuses, and never cuts.
- **ADR-129 Amendment 5**: the brief's search sources `[S-n]`; the read summary's `found`, `limited_reason` and
  `counts_exact`.
- **ADR-149**: an amendment, or a line of studio's, that Ask is a caller of `search_page` (note 5) and that its
  leak test covers Ask's sources.

## Decisions taken (Prompt L: the recommended option, the strict one for access)

1. **The question is sent whole as the query, and refused over 200 characters**, never cut and never reduced to
   keywords by the Conduit. Picking words would be a model-free guess at meaning, which the one line says the
   search does not do.
2. **One page of up to 50 results**, never a second page. If `more` is true, the read summary says "the first
   50 matches", and the answer says it read only those (rule 2).
3. **In-process, not over HTTP**: one access filter, the asker's own, and no second route (note 5).
4. **No timeline window for Whole case.**
5. **The fallback answers, saying so**, as the search box does, rather than refusing.
