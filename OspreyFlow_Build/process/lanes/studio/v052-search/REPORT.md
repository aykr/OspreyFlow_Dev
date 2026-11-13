# v052-search (step 3d): report

In progress. The studio lane, from 13 November 2026. The plan is `PLAN.md`; the red record is `RED_RECORD.txt`.

## Decisions taken (overrule here)

- **(a) Ranking is strict, and goes to the owner as their choice (page A §3).**
  - Options: OpenSearch's default relevance (word rarity, fuzzy and prefix expansion); or fixed-score bands with
    no expansion.
  - Took the strict one, as the brief asks for access. Hidden records can change the order of visible ones through
    word rarity, and can push visible hits out through expansion. Page A has two worked examples.
- **(b) Sound-alike codes are computed in Python, on every shape.**
  - Options: OpenSearch's analysis-phonetic plugin; or Double Metaphone in the Conduit and the indexer.
  - Took Python. The stock `opensearchproject/opensearch:2.17.1` image does not bundle the plugin (its build
    manifest, checked 13 Nov), so Lite and Small would need a derived image. `phonetics` (MIT) was already a
    dependency.
  - Beider–Morse is left out: abydos, its usual package, is GPL.
- **(c) A Document's text is its own index document, limited to the unit that may read it today.**
  - Options: text on the node's document; or text on a document of its own.
  - Took its own. `get_document_text` reads only within the extracting unit, which is narrower than the node's
    handling, and a highlight cannot be turned off per document. Rules agreed and built it.
- **(d) Groups count records, with documents' text matches apart as "Mentioned in documents".**
  - Options: count merged entities; or count records.
  - Took records. Exact counts of merged entities would need the graph for every match, not only the page shown.
    It is page A's question 2 to the owner.
- **(e) A group narrows the list as a `post_filter`; the access filter is never one.** Every group's count stays
  whole, and access limits counts and list alike.
- **(f) Results are listed at most 1,000 deep, and a deeper page is refused with words** (rule 2). The cap keeps
  clear of OpenSearch's own 10,000 window.
- **(g) lane/studio-search is stacked on lane/rules-v052-index (bdfb4e5).**
  - Options: wait for rules to merge; or stack.
  - Took stack. The route needs rules' client, `phonetic_codes` and `throwaway_index`. Merge order: rules first.
    Told the orchestrator.
- **(h) Until stage 8's access filter exists, the route answers through today's search, saying it is limited.** No
  index query is ever built without the filter (`build_search_body` refuses).
- **(i) The owner ruled on page A on 13 Nov (about 22:40):** strict ranking as recommended, and groups count
  records, with the screen saying "records". The response shape is frozen at ee7a16d.
- **(j) Merged entities are merged within one page of visible hits.**
  - Options: merge across all matches; or merge within the page.
  - Took the page. It is how case views merge today (`case_views._collapsed`, among the shown nodes). It reads
    links only among hits already shown to be visible, and it needs no graph read per match. A member on a later
    page is listed there separately.
- **(k) The search access filter refuses a principal with no case limit.** `datasets is None` is the Conduit's
  background work, never a reader's search.
- **(l) The fallback lists at most 100 deep,** the most today's search returns. Its counts are never shown as exact.
- **(m) Only an index that cannot answer falls back** (unreachable, timed out, 404 for an unbuilt alias, 429 or
  5xx). A query OpenSearch refuses (400) is our defect, so it is raised, not hidden behind "results limited".
- **(n) Highlight marks are private-use characters** (U+E000, U+E001), not control characters. OpenSearch trims a
  fragment's edges of everything up to U+0020 (found live).
- **(o) Two index defects in rules' files are fixed as a diff, not committed** (`rules_index_fixes.diff`): the
  trigram analyser's positions, and a text document's date. They were found live by the bands test, and 61 live
  cases pass with the diff applied. Rules' session was gone, so the diff went to the orchestrator.
- **(p) Removal plants are not in the leak test.** It cannot plant reverted, withdrawn or superseded records,
  because `throwaway_index` indexes live nodes only. Rules' `test_feed_live.py` shows each such event leaving the
  index.
- **(q) The index answers every "starts with" suggestion, and narrows a case-sensitive one.** The box asks
  case-sensitively by default, but the index's stored prefixes ignore case.
  - Options:
    - answer from the index only when ignore case is on, leaving the default box on the graph's prefix scan,
      which is the one that is slow at tens of millions;
    - answer case-insensitively and so change what the box finds;
    - ask the index for up to four times the page and keep only the matches in the typed case.
  - Took the third. `more` is set whenever the index had more than it was asked (rule 2). "Contains" and
    "exact" stay on the graph.
