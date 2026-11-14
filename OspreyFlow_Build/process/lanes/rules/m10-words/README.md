# M10's hidden words, checked only where the reader could not see them (`scripts.client_size_leaks`)

Step 4's second M10 run on stack d (14 November 2026, the subjects of their case's unit, every case
reaching its record; leaks run 20261114T155917Z-7f9f194b and never-join after it) found no hidden id in
any of 1,000 answers. Every failure was a hidden *word* that the answer showed for a reason other than
a leak:

- **the echoed query** (`SearchPageResponse.query`), which `measure_leaks` read as part of the answer:
  each leak case asks the hidden document's own title. Platform's to fix, done at 2aa40e3 on
  `lane/platform-v052-step4record` (the top-level `query` is left out when it is the query sent);
- **words visible in their own right**, this branch's to fix: a hidden partner's number inside the
  visible record's own `+44…` (47 cs-calls cases), a hidden spelling of a name in a visible report
  (18 cs-nominals and cs-covert cases). B's files checked a hidden word only against the visible
  records' names and titles, by equality.

## The fix (Prompt L: the strict option, listed to overrule)

- A case's `never_text` keeps a hidden record's word only where nothing `m10-part` may read in the
  measure case holds it: no visible record's property (`_strings` of its props) and no visible
  document's text, as a substring, lower-cased, as `measure_leaks` compares (`visible_corpus`, `seen`).
- The ids are checked whatever the words: a case with no word left still fails on any hidden id in
  the answer, and still needs its control to reach the record.
- `check_leaks` and `check_never_join` refuse a hidden word that is visible ("… is in what m10-part
  may read, so finding it in an answer would be no leak").
- `counts.json`'s `never_text_dropped` counts the words cut, by file.
- The words are cut after the sample is drawn, so the cases chosen, their queries and their controls
  are the second run's: the share reached (450 of 500 for never-join, the orchestrator's 90% floor)
  does not move.

## Red first

`plants.py` here: W1 to W5, each red alone, built and restored green (`PLANTS_RECORD.offline.txt`).
W1 is red at the build: the check refuses the generator's old cases before anything is written.
