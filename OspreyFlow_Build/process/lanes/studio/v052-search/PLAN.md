# v052-search (step 3d): the plan

The studio lane, 13 November 2026. Branch `lane/studio-search`, on `lane/deps-opensearch` (fcdfec4). ADR-149 (the
search service), ADR-059 Amendment 1 (suggestions from the index) and ADR-074 Amendment 3 (the box's scope) are
reserved for this step. The index side is the rules lane's (ADR-150, step 3c). Page A is `../SEARCH_ACCESS_DESIGN.md`.

## Order

1. **Page A** (done as a draft; the owner reads it on Mon 16). The access parts (stage 8) wait for the owner.
2. **The query builder:** `OspreyFlow_Core/services/api/search_index_query.py`. Pure functions with no client and
   no I/O, so they are tested offline:
   - `build_search_body(...)`: a search's request body;
   - `build_suggest_body(...)`: a suggestion's request body;
   - `read_search_response(...)`, `read_suggest_response(...)`: the replies read into typed results.

   The access filter is a **required** argument: a body cannot be built without one. That argument is produced by
   stage 8, after the owner reads page A. Tests: `OspreyFlow_Build/tests/services/api/test_search_index_query.py`,
   each red first.
3. **Against a real OpenSearch** (a lane stack's 1920x, after the demo, with rules' `throwaway_index`):
   - the tiers order as built;
   - typos, variants and sound-alikes are found;
   - highlights;
   - group counts;
   - suggestions.
4. **The route:** `POST /v1/search` and `POST /v1/suggest` ask the index first, then read the nodes from the graph
   (the graph stays the source of truth). The fallback goes to today's graph search, and the reply says so. The
   audit is unchanged. Rights are unchanged; `test_route_rights.py` runs live.
5. **The Glass:**
   - "search is running on the fallback" on screen;
   - results grouped with counts;
   - snippets;
   - filters by dataset and date.

   Built in three themes, with axe, and a keyboard step for each new action (rule 13). The results layout itself is
   case's 3e′, after the owner's navigation decision.
6. **Stage 8:**
   - the access filter;
   - merged entities, collapsed after the filter;
   - the leak test (page A §4), red per part.
7. **ADR-149 and the two amendments, as built,** with the test that fails for each sentence (rule 12).

## The query, as designed (stage 2)

Every scoring clause is a fixed score: `similarity: boolean` in the mapping, and `constant_score` or `dis_max` in
the query. So no score depends on another document, and the tiers are bands that cannot cross.

| Band | Clause (node documents unless stated) | Score |
| --- | --- | --- |
| Exact identifier | `terms` on `identifiers`: the text as typed, and its canonical form (ADR-128) | 3000 |
| Close name: exact | `match` on `names`: the whole text, normalised | 2900 |
| Close name: every word | `match` on `names.words`, operator and | 2500 |
| Close name: sounds like | every query word shares a Double Metaphone code with `names_phonetic` | 2300 |
| Close name: typo | `match` on `names.tri`, 60% of the query's trigrams, for a query of four letters or more | 2100 |
| Mention: phrase | `match_phrase` on `text` (text documents) | 1500 |
| Mention: every word | `match` on `text`, operator and | 1200 |
| Mention: some words | `match` on `text`: one point per word matched, under 1200 because a query over 200 characters is refused, never cut | 1–100 |

- Within a band, newest first by `date`, then by id, so the order is total and repeatable.
- Hits are collapsed on `node_id`, so a Document found both by its title and in its text appears once, in its
  higher band.
