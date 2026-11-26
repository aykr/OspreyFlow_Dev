# SE8g, round 1 (continued): the owner's (a) (26 November 2026, 14:55 UTC)

Your guard names four helpers beyond `test_reports.py`. **The owner's ruling: (a).** Add
`await client.create_database_if_absent()` before the first write in each: `test_assessment_routes.py` `_write_node`,
`test_export_routes.py` `_write_node` and `_write_nodes`, and `test_statelessness.py` `_write_people`. Test setup only:
no assertion, marker, fixture value or test is loosened or skipped, and no exception is added to the guard. Your scan row
is on main (`5278f2b`).

| # | Do | Done when |
| --- | --- | --- |
| 1 | The four create lines, as above, each awaited before the helper's first write, not inside an `if`, loop or `except`. | The guard green on the real folder; each of the four files collects (`pytest --collect-only`); your frozen checks green. |
