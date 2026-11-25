# GR3a, round 8: one row (the conductor, 25 November 2026, 11:47 UTC; the owner's send-back: an access rule is not accepted narrower)

GR3a was verified at `63c2d5689c` and accepted narrower on the standing line with one gap in a test (backlog row 36).
**The owner sent it back for that row alone (25 November, about 11:45 UTC): an access rule is not accepted narrower.**
This round is that row and nothing else. It is the last round under the dial.

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **ADR-152 invariant I15 names `test_the_dashboard_page_answers_a_reader_without_read_reports_as_a_missing_report` (the owner's approved correction `ADR152_I15_ROW`), and no file has a test by that name.** The behaviour is right and tested under another name; your round-6 and round-7 tables asked for the exact name, but the line's round-table fault showed those rounds round 5's table. | the page's Python scenario test (`OspreyFlow_Build/tests/glass_trees/test_govuk_alert_monitoring_scenario.py`) or its node test: wherever the existing 404 case lives | **A test under exactly that name**: a reader without `read_reports` gets the same 404 page, words and status, as a report that does not exist, and nothing on it tells the two apart. Rename the existing case to it if it already proves exactly that (say so); otherwise add it. Red first against a page that answers 403 or names the right. **And the scenario file's own check of I15's tests (about lines 653 to 656, which checks only the first name) checks both names exist**, red with the second one renamed away. Nothing else changes. |
