# Search on OpenSearch: the access design (page A, v0.5.2 step 3d)

Draft by the studio lane, 13 November 2026, with the rules lane's index side (to be confirmed). For the orchestrator
by Sun 15 Nov, then the owner on Mon 16. Nothing below about access is built until the owner has read it.

**The principle.** The index holds the same access facts as the graph and applies them **inside every query**, using
the rule the graph store uses today (`packages/adapters/graph_arcadedb/access_filter.py`). The test is a stronger
one: **what a reader gets back is identical whether or not the records they may not see are in the index at all.**

## 1. How dataset access and handling codes are held in the index

- **One index document per graph node, keyed by the node's id.** Never one per file: a file is stored once however
  many Document nodes name it, and two of those nodes can carry different handling. Never one per merged entity:
  storage is never merged (rule 6).
- **Each document carries the node's own access facts, copied as they are:** classification, handling code, owning
  unit, originator, and its datasets (ADR-099). A reverted, withdrawn or superseded node is removed from the index,
  not flagged. The graph stays the source of truth; the rules lane's drift check reports any difference (step 3c).
- **Only what the Glass may already show is searchable:** a node's displayed properties, and a Document's text.
  Source-system identifiers are never indexed (rule 7). A gazetteer place is searchable by its name alone (ADR-147).
- **The filter in every query** has three parts, the same three as the graph's:
  1. the record's classification is no higher than the reader's clearance; an unknown clearance sees nothing;
  2. its handling code is unrestricted, or the reader may receive that restricted code and belongs to the
     record's owning or originating unit;
  3. it is in one of the datasets of the reader's case; outside a case, nothing.

  It is built by one function on the Conduit, sits in the query's filter (never applied to results afterwards), and
  covers searches, group counts and suggestions alike. The Glass never talks to OpenSearch.

## 2. A merged entity built from datasets with different access

Merging stays a view (01 §4). Each record is its own document with its own access, so a search finds only the
records the reader may see. The Conduit then joins the hits into one entity using the same-as links the reader's case
reads from the graph, at the reader's own resolution threshold, through the graph's own filter. A record the reader
may not see adds **nothing** to the merged entity: no name, alias, snippet, count, rank or "also known as". The
reader cannot tell that a merged entity has a member they cannot see. A same-as link that crosses datasets is in no
case already (ADR-099 Amendment 2), so a search never joins across cases.

## 3. How counts, suggestions and snippets are limited

- **Counts** (the result groups by type, the dataset and date filters, the total) are computed by the same filtered
  query, so they count only visible records. They count records, and the screen says "records", because merged
  entities are counted only on the page shown. A total is exact; where a limit applies, the screen says so (rule 2).
- **Suggestions** use the same filter, with prefix matches held as edge n-grams in each document. OpenSearch's
  completion suggester is not used: it cannot apply the filter.
- **Snippets** are highlighted passages from the matching document itself, and only from its searchable fields. A
  snippet is therefore always a passage of a record the reader may see.
- **Ranking and fuzzy matching, the subtle part.** Two standard OpenSearch features would let hidden records change
  what a reader sees, even with the filter in place:
  - **Scores use word rarity across the whole index.** A hidden record can change the order of two visible ones.
  - **Fuzzy and prefix queries expand against the index's word list, up to a fixed number of words.** Words found
    only in hidden records can use up that number and push a visible hit out.

  **Recommended (strict):** no word-rarity scoring and no expansion.
  - Ranking is by tier, as the owner asked: exact identifier, then close name, then mention. Within a tier, a record
    is ranked by how well it matches, not by how rare its words are.
  - Typos are caught by three-letter fragments, prefixes by stored prefixes, and sound-alikes by a phonetic key
    computed by the Conduit (Double Metaphone).
  - **The phonetic key is computed by the Conduit on every shape**, because the plugin is not on every shape
    (checked 13 November):
    - **Lite and Small** run `opensearchproject/opensearch:2.17.1`. Its build manifest (`opensearch-build`,
      `legacy-manifests/2.17.1/opensearch-2.17.1.yml`) bundles 24 components and neither analysis-phonetic nor
      analysis-icu. OpenSearch's 2.17 documentation lists both as additional plugins, installed with
      `opensearch-plugin install`, which means a derived image.
    - **Amazon OpenSearch Service** lists ICU Analysis as "Included on all domains". Phonetic Analysis is in the
      same table of pre-installed plugins, not among the optional ones, but its row does not say "all domains".
    - To be seen with `GET _cat/plugins` on a lane stack and on the poc domain (step 3a) once the demo is over.

  **What strict costs against the owner's scope:**

  | Scope | Strict | Cost |
  | --- | --- | --- |
  | Typos | Met: a name matches on shared three-letter fragments ("Jonathon" finds "Jonathan") | Weak on names of three letters or fewer, which fall back to the phonetic key and the exact match. Graded overlap, not "one edit away". |
  | Spelling variants and sounds-like | Met: by a Double Metaphone key from `phonetics` 1.0.5 (MIT), already a dependency through resolution. Run on 13 Nov, "Mohammed", "Muhammad" and "Mohamad" all give `MHMT`; "Smyth", "Smythe" and "Smith" all give `SM0`/`XMT`; "Jonathan" and "Jonathon" give `JN0N` | Double Metaphone suits English spellings best. Beider–Morse, which handles surnames from more languages, is to be added if a permissive implementation exists. The plugin's options would be no wider. |
  | Exact identifier, then close names, then mentions | Met in full: each tier is a fixed band of score, so no record crosses tiers | None. |
  | Order within the mentions tier | Phrase matches first, then by how many of the query's words match, then newest first | A match on a common word counts as much as a match on a rare one. This is the main loss against OpenSearch's default. |

  **Two worked examples (synthetic) of what default relevance leaks:**
  1. **Word rarity.** An analyst may see two reports. Report A mentions "Kestrel" once; report B mentions "invoice"
     three times. A search for "Kestrel invoice" puts B first. Then 400 records above the analyst's clearance are
     loaded, all mentioning "invoice". "Invoice" is now a common word, so it scores less, and A moves above B.
     **Nothing the analyst may see has changed, yet the order has**, telling them that a body of hidden material about
     invoices arrived. Under strict ranking the order stays as it was.
  2. **Expansion.** An analyst may see a person record "Smythe". A fuzzy search for "Smyth" expands to at most 50 words
     from the index's word list, and 60 hidden records hold names one letter from "Smyth". The 50 words can be used
     up before "smythe" is reached, so the visible "Smythe" record is not returned. **A visible record going missing
     tells the analyst that many hidden near-names exist.** Under strict matching nothing is expanded: "Smythe" is
     found by its fragments and its key, whatever else the index holds.

  **This is the owner's choice;** the strict option is what will be built unless the owner rules otherwise.

## 4. What the leak test asserts (the owner's requirement a)

One test, against a real OpenSearch on a lane stack, on synthetic data:

- **Plants.** Hidden records are made to look as much like visible ones as possible: the same names, the same
  sound-alikes, the same words in document text, and same-as links to visible records. The hidden set covers each
  way a record can be hidden:
  - above the reader's clearance;
  - a restricted code the reader cannot receive;
  - a restricted code they can receive, but owned by another unit;
  - a dataset outside the reader's case;
  - reverted, withdrawn and superseded records.
- **Assertion.** For a set of queries (exact identifier, misspelt name, sound-alike, prefix suggestion, full-text
  phrase, filtered by dataset and by date), the reader's whole response is identical with the hidden records in the
  index and with them removed. "Whole response" covers result ids and their order, merged entities and their names,
  snippets, every group count and total, suggestions and the "more" flag.
- **It is shown red first** (rule 15), once per filter part and once for each of ranking and expansion. For each, the
  test is rerun with that part removed, or with OpenSearch's default scoring and fuzzy expansion, and must fail for
  that reason.
- **Fallback.** When OpenSearch is unreachable, the bar falls back to today's search, which keeps its own existing
  access tests. The same test is not repeated there.

## Questions for the owner

1. Strict ranking without word rarity or fuzzy expansion (recommended), or OpenSearch's default relevance with a
   known, narrow inference channel?
2. Should groups count records (recommended, exact and cheap) rather than merged entities (only possible on the page
   shown)?
