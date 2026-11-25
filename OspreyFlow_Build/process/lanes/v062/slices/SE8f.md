# Slice SE8f · SE8 · Two store tests SE8b left behind, made true to the code and the spec (a test-only part; the owner, 25 November 2026, for RL2's GitHub green)

- **Build id:** SE8 (the export ledger) · **Dial setting:** balanced · **Rounds limit:** 6 · **After:** nothing
- **Test-only:** no product file changes. Every access assertion stays (rule 4); none is loosened.

## Why they fail on GitHub and pass on the Mac (found by the conductor, 25 November 2026)

**Neither is the environment, ordering or a flake.** Both need a live store, and **the Mac's merge gate runs offline**
(its log: "port guard: on (ports 2480, 5432, 80, 8080 and 8081 on this machine are refused)", "no stores made
(offline)"), so the Mac never runs them; GitHub's `conformance` job does, and has failed them on every run on main since
at least 10:23 on 25 November (runs on 4f77858, 6d821f4, 4a9820a). **Both went stale with SE8b (23 November)**:

1. `tests/services/api/test_investigation_access_store.py::test_a_dashboard_reads_the_case_it_was_granted_and_no_other`
   stands in for `app._case_report` with `_figures`, which returns a bare `ReportFigures`. Since SE8b (`eb7865d`)
   `_case_report` returns `tuple[ReportFigures, bool]` and `read_report_feed` unpacks `figures, withheld = ...`
   (`services/api/app.py:15064`); iterating the pydantic model yields its fields, hence
   `ValueError: too many values to unpack (expected 2)`, and the feed read answers 500 where the test expects 200.
2. `tests/services/api/test_reports.py::test_the_view_and_the_feed_agree_and_the_feed_is_recorded` asserts the ledger
   holds exactly the two `report_feed` rows, "the view is not". Since SE8b (`b4d761f`) the Reports view's figures write
   a `case_report` row, **as `spec/03_CONDUIT_MIDDLEWARE.md` (about line 1683) requires** ("for every export the Conduit
   makes: ... the report feed, the Reports view's figures"). The test is stale; the code is right.

## Round 1

1. **The dashboard test's stand-in returns the real shape:** `(ReportFigures(...), False)`, typed as `_case_report`
   is (`tuple[ReportFigures, bool]`), so a later change of shape fails type checking, not only at run time. Every
   access assertion in it is kept as written (A listed alone; A's feed 200; B's and an absent case's alike 404; the
   ungated route 403).
2. **The feed test asserts what the spec says:** the case's ledger rows are the view's `case_report` and the two
   `report_feed` reads, each the Viewer's, and nothing else (compare as a multiset or in the ledger's own order, said
   which); reword its message to the spec's.
3. **Red first, and the plant:** (a) both tests are red on main against a store, as GitHub shows: cite the run and the
   two error lines; (b) `plants/SE8f.patch` (product only) drops the Reports view's ledger write; the fixed feed test
   must fail under it (it would have passed under the old assertion only by accident of the count).
4. **A guard so it does not recur unseen (rule 12):** a pure test (no store) that `_case_report`'s return annotation
   and every stand-in for it in `tests/` agree, by reading the annotation; red with a stand-in returning the bare model.

## How it is judged

The frozen checks below are pure (the Mac is offline). **The two store tests are judged by the server's early-warning
run before the merge and by GitHub after it**; the builder shows their red on main from the GitHub run and says so.

## Checks

The new guard test; `pytest --collect-only` on the two store files (they import and collect); `test_doc_citations_check.py`;
`ruff check .`.
