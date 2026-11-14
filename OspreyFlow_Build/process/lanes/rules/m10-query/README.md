# M10's hidden words: the query's own dropped, the record's others kept (`scripts.client_size_leaks`)

## Why

M10's turn on stack d after the subject and visible-word fixes (14 November 2026, run tree ca012bf,
main 8347d28 plus platform's a28f93e, the rules lane's lease of 2026-11-14T03:27:42Z) found
never-join met and leaks not met: 500 of 500 leak cases failed on "the hidden record's words … are in
the answer", with no hidden id in any answer. `probe_answer.py` (`probe_answer.d.txt`, run
20261114T205000Z-011af7e0) showed where: each visible result's `match.why`, "Spelt like '<the query
sent>'". A leak case asks the hidden document's own title, so every explanation quoting the query
quotes the title. Not a leak, and not the product: the reader's own input, a third echo after the
answer's `query` and the visible texts.

## The fix, as the orchestrator ruled (stricter than first proposed)

- A case's `never_text` drops a hidden word its own query holds (any answer may quote the query), as
  it drops a word visible in its own right; the checks refuse either.
- A leak case's hidden words are every string its hidden record could show, not its title alone:
  the title, its other string properties, and each distinct word of four or more letters in its own
  document text (`hidden_words`), less both drops.
- Each case's count of words left is written (`words_checked`); a case with none is
  words-indeterminate (its ids still checked); the words half is measured only where at least 90% of
  the cases keep one (`counts.json`'s `leaks_words`).
- Red first: `plants.py` here, Q1 to Q4, each red alone, built and restored green
  (`PLANTS_RECORD.offline.txt`).

## M10, as step 4's gate (stack d, the rules lane's lease)

| File | Run | Reached | Verdict |
| --- | --- | --- | --- |
| `leaks.jsonl` | 20261114T205703Z-af53b1e6 (run tree 496e714: main 8347d28, platform a28f93e, this branch at d50eaf3) | 500 of 500 | **met**: no hidden id; words checked in 500 of 500 cases, none found |
| `never_join.jsonl` | the run before (ca012bf), at the visible-word fix | 450 of 500 (90.0%), 50 indeterminate | **met** |

- **The words half is thin, said plainly.** Every leak case's one remaining word is its hidden
  report's exact `sent_at` (494 of 500 keep only that; 6 also keep a text word, misspelt name forms).
  B's generated report texts share nearly all their vocabulary with visible reports, so the body
  words drop as visible. 73,191 candidate words were dropped in all.
- **It can fire** (rule 15, the orchestrator's positive control): `positive_control.py`
  (`positive_control.d.txt`, run 20261114T210353Z-80a82366) searched 5 hidden reports' own titles as
  their cleared control: each report came back first, and `measure_leaks`' words check fired on its
  `sent_at` in all 5, at `.nodes[0].properties.sent_at`. The result row's own `date` is the day alone,
  so a leak of a result row without its node shows only the day; the ids check catches that one.
- Never-join's run checked a superset of today's words (only the words its own query holds have
  dropped since, 90 in all), so its verdict stands.
