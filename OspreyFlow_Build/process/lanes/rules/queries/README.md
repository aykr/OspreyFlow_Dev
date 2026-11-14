# Step 4's query set (`scripts.client_size_queries`)

Built by the rules lane on 14 November 2026, on the orchestrator's assignment, to the runner's contract
platform sent (the fields `scripts.measure_search` and `tests/perf/test_search_budget_live.py` read:
`class`, `query`, and by class `expect_first` or `filters`). Platform reviews it before it is used.

## The set on stack d's host

`python -m scripts.client_size_queries --from ~/osprey-load/b-1.0 --out ~/osprey-load/step4` (run with
`PYTHONPATH=.:packages` from `OspreyFlow_Core`, at f86eb16, 3.3 s, 289 MB), from B's files (manifest
SHA-256 `7f8244cf…e1450`):

| Class | Rows | Eligible records |
| --- | --- | --- |
| suggest (M1) | 200 | 30,000 people |
| names (M3) | 200 (67 slip, 67 sound-alike, 66 variant) | 30,000 people |
| fulltext (M4) | 200 | 27,874 OS/C documents of 40,000 |
| exact (M5) | 200 | 8,000 numbers |

`queries.jsonl` SHA-256 `59f7913c…59e10f`; `counts.json` beside it.

## Decisions taken (Prompt L: the recommended option, listed to overrule)

- **The seed is 4**, the default, written in `counts.json`.
- **A "spelling variant" (M3)** is the name as a register writes it, the family name first and in
  capitals ("MORLOW Stephen"). The slip and the sound-alike are the generator's own
  (`client_size_plan.slip`, `client_size_plan.sound_alike`), so they are the kinds of difference the
  sources hold. A sound-alike changes the family name where a rule applies to it, else the given name.
  The three changes are taken in turn, so they are a third each; a person whose name the turn's change
  leaves as it is gives no row.
- **M4's dates** reach 0 to 30 days either side of the document's day, chosen by the seed. A phrase
  has at least one word of four or more letters, since a phrase of short words alone ("of the") finds
  nearly every document.
- **M5's numbers** are the intelligence reports' own numbers (`cs-intel-number-<n>`), in their
  `value_raw` or E.164 form. A number is used only where no other record m10-measure reads holds
  either form. The text of an OS/C document can name the same number; whether the number's own node
  ranks first over such a document is what M5 measures.

## Red first

`plants.py` here: Q1 to Q7, each red alone, built and restored green
(`PLANTS_RECORD.offline.txt`).
