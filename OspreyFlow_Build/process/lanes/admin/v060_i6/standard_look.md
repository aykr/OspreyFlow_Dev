# The standard look, before and after #6

The orchestrator asked for the standard look's heading changes on record. `GOVUK_PASS_LIST=1 GOVUK_PASS_LOOK=standard`
runs the same pass with no brand, listing only.

- **Before:** 376c52b, with no type fixes. **435** findings.
- **After:** a346002 and later, with every fix, h5 and h6 included. **0** findings.

What changes in the standard look, by element and its size before. Each size after is its token's:

- h1 23px, h2 19px, h3 and h4 16px, h5 and h6 12px;
- a control the page's 13px;
- the Studio's 11px and 14px;
- a mono value now classed `.value`, with no visual change.

| Findings | Before | Element | Pages |
|---:|---|---|---|
| 155 | 15.21px | `h3` | monitoring, alert-figures, boards, strength, views … |
| 117 | 19.5px | `h2` | models, maps, monitoring, strength, alert-figures … |
| 55 | 13.3333px | `span` | ingest-studio, metrics-panel, places, shell, case-screen-options … |
| 27 | mono, not a value to copy | `div` | ingest-studio |
| 27 | 11.05px | `div` | ingest-studio |
| 17 | 10.79px | `h5` | drawn-merge, promotions |
| 11 | 13.3333px | `button` | metrics-panel, harness.html, ingest-studio, checks-on-load |
| 8 | 14.3px | `h1` | ingest-studio, checks-on-load |
| 7 | mono, not a value to copy | `span` | alert-figures, start, harness.html |
| 6 | 26px | `h1` | search-results, answers |
| 2 | mono, not a value to copy | `li` | checks-on-load, ingest-studio |
| 2 | mono, not a value to copy | `textarea` | ingest-studio |
| 1 | 11.05px | `span` | ingest-studio |
