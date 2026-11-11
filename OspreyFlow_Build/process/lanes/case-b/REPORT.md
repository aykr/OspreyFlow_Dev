# case-b · P12 part 1 · report after the orchestrator's review of a5fa3c1b, 11 November 2026 (the test server)

**Exit (part 1).** The amendment is drafted; the reservation is put back for the orchestrator to mark at merge.
- **Laurium's service, met offline only.** Another host is refused at start (`test_settings.py`) and at the call that picks it (`test_laurium_service.py::test_every_model_call_goes_to_the_gateway_and_no_other_host`, planted: `['api.openai.com'] == []`).
- **The master key never crosses into Laurium's container, met** (ADR decision 8, `keys.py`; `test_adapter.py::test_no_call_from_the_adapter_carries_the_master_key`, 4 plants red). **A credential step: two review rounds.**
- **Findings *inferred*, met through the real store's write** (`test_findings_inferred.py`, `test_laurium_findings_pending.py`, promoting plant red in both). Postgres's own acceptance of the row is not proven by them (`test_review_store.py`'s, live).
- **The suite on both engines: NOT met against a real gateway.** Laurium is registered in `MODEL_PORT_ADAPTERS`; the stand-in refusals pass on both. **The leased live run was not taken**: the lease asked for approval. Laurium has never met a real gateway or model.
- **Rule 1 not kept for the extract suite**: it was committed after `adapter.py` and `app.py` (red record).
- **Schema mapping, met** for all 33 entity types of default, fibo and niem. **No LangChain without Laurium**: the source leg is met; the image leg is carried.
- **Red record**: 53 offline and 14 in Laurium's environment, all red (`P12_RED_RECORD.md`).

**Gates at 283cfeb7** (main unmoved at 459ae1d4; run directly, not through the lease, which asked for approval; full outputs in `gates/283cfeb7.*`). make test: 4 failed / 11,033 passed. make test-js: 1 timing budget failed under server load (passes alone). make -k ci: core-check only (ESLint and trivy fs on the venv, a11y without a slot; with slot 3, 34 passed). Each is explained in SERVER_LOG "Built"; none is in a branch file.

**Left, and why.** Each needs approval this unattended session cannot give: the leased live run (the blocker), the image's start refusal, the image leg and trivy on Laurium's image (out of `P12_CI.diff`), moving the venv, a11y. Friction row `2026-11-11-case-b-server-session-cannot-lease.md`.

**Commits**: f6f85fcf…a5fa3c1b, then ca85e385…283cfeb7 and the records after, on `lane/case-b-p12`; never pushed.

**Requests**: apply both diffs at merge; ratify `factory.require` in `test_suite.py`/`test_suite_vision.py` (SERVER_LOG decision 15); move the venv; run, or allow, the leased live run (SERVER_LOG question 2 has the command).

**Questions for the owner**: the proxy hazard for part 2 (ADR decision 4). Nothing of mine is still running.
