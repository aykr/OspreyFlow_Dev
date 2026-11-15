# The standard look, before and after #6

The orchestrator asked for the standard look's heading changes on record. `GOVUK_PASS_LIST=1 GOVUK_PASS_LOOK=standard`
runs the same pass with no brand, listing only, over the 44 harness pages that apply the brand, in every state.

- **Before:** main 582bab2's code. **503** findings, raw in `standard_before.jsonl`.
- **After:** 1494913. **0** findings.

Each size after is its token's:

- h1 23px, h2 19px, h3 and h4 16px, h5 and h6 12px;
- a label heading 13px;
- a control the page's 13px;
- the Studio's 11px and 14px;
- a name in the page's face, and a value classed `.value`;
- code in the design's mono.

| Findings | Before | Element | Pages |
|---:|---|---|---|
| 179 | 15.21px | `h3` | alert-figures, boards, drawn-watch-alert, ingest-studio, monitoring, operations-figures, rules-place, strength, views |
| 118 | 19.5px | `h2` | alert-figures, maps, models, monitoring, operations-figures, rules-place, strength |
| 55 | 13.3333px | `span` | admin, case-screen-options, frame, ingest-studio, matrix, metrics-panel, places, shell, top-bar |
| 35 | a value to copy, not in mono | `code` | admin, ingest-studio, promotions |
| 27 | mono, not a value to copy | `div` | ingest-studio |
| 27 | 11.05px | `div` | ingest-studio |
| 17 | 10.79px | `h5` | drawn-merge, promotions |
| 15 | 13.3333px | `button` | boards, checks-on-load, harness.html, ingest-studio, metrics-panel |
| 8 | 14.3px | `h1` | checks-on-load, ingest-studio |
| 7 | mono, not a value to copy | `span` | alert-figures, harness.html, start |
| 6 | 26px | `h1` | answers, search-results |
| 4 | a value to copy, not in mono | `pre` | ingest-studio |
| 2 | mono, not a value to copy | `li` | checks-on-load, ingest-studio |
| 2 | mono, not a value to copy | `textarea` | ingest-studio |
| 1 | 11.05px | `span` | ingest-studio |
