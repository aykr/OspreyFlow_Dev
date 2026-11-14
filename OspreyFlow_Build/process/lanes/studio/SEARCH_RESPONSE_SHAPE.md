# The search service's request and response (v0.5.2 step 3d, for the case lane's 3e′)

**Frozen at ee7a16d, 13 November 2026, after the owner read page A (about 22:40).** A change from here goes through
the orchestrator to the case lane. **The owner's ruling:**
- groups count records, and the screen says "records";
- ranking is strict: exact identifier, then close name, then mention, with no word-rarity scoring and no fuzzy or
  prefix expansion.

Draft by the studio lane, 13 November 2026. It goes with the access design page (`SEARCH_ACCESS_DESIGN.md`) and **is
frozen once the owner has read that page**. Until then it may change only by a message to the case lane. The
Pydantic models in `packages/schemas` (generated to TypeScript) become the source of truth when they land. They
will match this.

**One route, `POST /v1/investigations/{id}/search`.** It is extended, not replaced, as `search.py` always said. It
keeps the same right (Investigate), the same case-viewer check and the same audit. The new request fields are
optional, and the response keeps `nodes`, so today's callers and access tests read it unchanged. Suggestions stay
on `…/suggest`, with their response unchanged (ADR-059 Amendment 1).

## Request

```jsonc
{
  "query": "Kestrel invoice",        // 1–200 characters; a longer one is refused (422), never cut
  "limit": 20,                       // today's field, kept; ignored when page_size is given
  "group": null,                     // null = All; an entity type name ("Person"); or "mentions"
  "filters": {
    "datasets": ["ds-…"],            // optional; only the case's own; another is refused (422)
    "date_from": "2026-01-01",       // optional, inclusive
    "date_to": "2026-02-01"          // optional, inclusive
  },
  "page": 1,                         // 1-based
  "page_size": 20                    // 1–50
}
```

## Response

```jsonc
{
  "query": "Kestrel invoice",
  "source": "index",                 // "index" | "fallback"
  "limited": false,                  // true on the fallback: the screen says results are limited
  "limited_reason": null,            // the words to show when limited, written by the Conduit
  "total": 57,                       // matches across all groups (see note 1)
  "counts_exact": true,              // false: the screen says counts may be higher (rule 2)
  "groups": [
    {"key": "Person", "label": "People", "count": 12},
    {"key": "Document", "label": "Documents", "count": 3},
    {"key": "mentions", "label": "Mentioned in documents", "count": 42}
  ],
  "filters": {
    "datasets": [{"id": "ds-…", "name": "Fixture Corp", "count": 40}],
    "dates": {"earliest": "2025-03-02", "latest": "2026-10-30"}   // over the matches; null if none dated
  },
  "page": 1,
  "page_size": 20,
  "more": true,                      // another page exists
  "nodes": [ /* Node records, today's shape, read from the graph: every node any result names */ ],
  "results": [
    {
      "node_ids": ["01J…", "01J…"],  // every visible record this result stands for (a merged entity: see note 2)
      "type": "Person",              // the label is the Glass's own nodeLabel(nodes[…]), as everywhere else
      "match": {
        "band": "name_sounds",       // identifier | name_exact | name_words | name_sounds | name_typo |
                                     // mention_phrase | mention_words | mention_some
        "why": "Sounds like 'Kestrel'",   // the Conduit's words, ready to show
        "field": "Name"              // the property it matched, by its display name; null for a mention
      },
      "passage": [                   // documents' text matches only; otherwise []
        {"text": "paid ", "match": false},
        {"text": "Kestrel", "match": true},
        {"text": " for the invoice", "match": false}
      ],
      "date": "2026-10-30",          // the date the date filter uses; null if none
      "datasets": ["ds-…"],          // the record's datasets within the case
      "is_document": false           // true: "Open" opens the document reader with node_ids[0]
    }
  ]
}
```

**Show on graph:** seed the case with `node_ids`, through the existing `POST /seed`. Nothing else is needed. Every id
is one the reader may see.

## Notes

1. **What the counts count.** A group counts records, and `mentions` counts documents whose text matched. A Document
   found by its title and in its text counts once in Documents and once in Mentions. It is listed once under All, in
   its better band. `total` is the sum of the groups. Page A's second question asks the owner to confirm this.
2. **A merged entity** is one result. Its `node_ids` are its visible members only, and `nodes` holds only those.
   A member the reader may not see adds nothing. It is grouped and counted under its best member's type, once.
3. **The fallback** (OpenSearch unreachable) is today's exact search:
   - `source: "fallback"` and `limited: true`;
   - groups are counted from the returned records, so `counts_exact` is false;
   - no passages;
   - `filters.datasets` lists the case's datasets without counts, and `dates` is null;
   - `match.band` is `identifier`.
4. **Paging:** `page × page_size` is capped at 1,000. Past the cap the request is refused (422), and the error
   says to narrow the search. It is never cut silently.
5. **Ask & Chat's "Whole case"** (Part D, if the owner approves it): it calls this route with `page_size` up to 50.
   It cites `node_ids` and the `passage`, and reads a cited document's full text through the existing reader, which
   checks access again. No other route is added for it.
6. **Never in a response:** OpenSearch's own scores, index names, source-system identifiers, or any count that
   includes a record the reader may not see.

## As built, after the reviews of d2b207a (13 November 2026, through the orchestrator)

The models are `packages/schemas/search.py`, generated to TypeScript (`SearchPageRequest`, `SearchPageResponse` and
their parts, in `packages/schemas/generated`). The case lane builds against those. Read alongside the example above:

- **`groups[].label`** is the plural the screen shows ("People", "Documents", "Organisations"), as the example
  says. `key` stays the type's name.
- **`match.field`** is the property's display name ("Family name", "Nino"), never one the index does not search.
  It is `null` for a mention, as before, **and for a typo** (`band: "name_typo"`): a typo is graded over the
  trigrams of every name, not matched in one property. That is meant, not a gap.
- **`limited_reason`** is one of three, by why the fallback answered:
  - "…this deployment has no search index";
  - "…the search index cannot be reached";
  - "…the search index is catching up with recent changes".

  On the fallback, "The date filter is not applied." is added when a date filter was asked.
- **`counts_exact`** is also false while nodes the index has not caught up with are left out (ADR-149 decision 2).
  Say "counts may be incomplete".
- **`limit`** (today's field) may still be up to 100 when `page_size` is not given; `page_size` is 1–50.
- **Dates** are days in UTC (`YYYY-MM-DD`). A date filter that ends before it starts is refused (422).
- **`/suggest`'s response** gains `source` (`"index"` or `"graph"`) and `limited`. The bar's line is this step's
  (ADR-059 Amendment 1). The lines touched in `GlobalSearch.tsx` are `LIMITED_SUGGESTIONS`, the `limited` state,
  the reply's type in `ask`, and the status element.
