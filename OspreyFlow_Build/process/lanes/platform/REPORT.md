# Platform lane · P2 · report (8 November 2026)

Settled by the orchestrator (owner away), in ADR-135 Amendment 3: limits are per engine; a budget is in tokens; no usage per person. Measured first on the pinned LiteLLM 1.101.0. Two rounds of the lane-reviewer: round one found 2 blockers and 9 must-fixes, round two found 3 must-fixes and 4 nits, all fixed; the gates then found two more (a usage file's place, a lint line), fixed; each new test was shown red (`P2_RED_RECORD.md`).

**Exit criteria, all met:**
- **Figures equal a planted gateway record**, every page read, nothing cut short: `test_model_usage_and_limits.py::test_the_figures_equal_a_planted_gateway_record`, `…every_page…`, `…counted_by_engine_and_job`.
- **Every route refuses without `manage_models`**: the eleven-route walk in `test_model_admin_routes.py::test_every_models_route_refuses…`, which also asserts the gateway saw nothing.
- **A limit stops the next request through the real routing path**, in words, never the gateway's: `…request_rate_set_stops…`, `…token_budget_set_stops…`, and through the analyst's own route `…told_so_in_words_through_their_own_route`.
- **No prompt, answer, key, source id or person's id leaks**: `…no_prompt_answer_key_or_source_id…`, `…carries_the_asking_person_s_id`, `…no_engine_key_or_master_key_reaches_any_log_record`, and `test_gateway_backup.py::…no_engine_key…`.
- **Keyboard and axe:** 2 new keyboard cases (11 in all); 28 axe scans in dark, light and GOV.UK, on a server of the lane's own (studio's Vite held 5185).
- **Live** (`test_model_gateway_live.py`) under platform leases on stack a: 3 passed, 140 s, lease taken 19:19:40. Gates at `58ee62c` (tree `204d685b…`) on main `1122bfa`: `make -k ci` green whole; `make test` 8660 passed, the 4 failures and 2 errors not the branch's (`gates/README.md`).

**Decisions taken:**
- Each engine's gateway key is an HMAC of its name under the master key.
- Every hosted entry is priced at 1 unit a token, so the gateway's spend is the tokens used.
- Calls are tagged `osprey:<engine>/<job>`.
- A start that cannot reach the gateway keeps retrying.

**Left:**
- **Per-team limits:** settled per engine while teams were unbuilt; L2.5's teams reached main as P2 closed, so a team's limits are a further amendment.
- **Fallbacks:** not in this step's row.
- **Transcriptions and embeddings are not counted:** tagging them was not measured.
- **An old engine key outlives a changed master key:** no verb changes the master key.

**Requests to the orchestrator:**
- Commit `ff1da5e`'s registry ids as a diff: `set-a-model-engines-limits-by-keyboard` and `choose-the-model-usage-period-by-keyboard` in `MODELS_ACTIONS`.
- Ratify these files outside the lane's map:
  - `packages/schemas` (the step's head commit);
  - `services/api/app.py` (the model routes, the limit's handler and `model_admin.close`);
  - `harness/backup.py` (the key table);
  - `shell/placesByRole.json` (rules');
  - `a11y/every-harness.spec.ts`;
  - `spec/00`, `03` and `04`.
- Ask the owner of `apps/workspace/src/patterns/api.ts` (Ask to search) to show `model_limit_reached`'s words, as it already shows `engine_refused`.

**Questions:** none. **Running:** nothing; no stack is held.
