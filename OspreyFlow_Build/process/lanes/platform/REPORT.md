# Platform lane · P2 · report (8 November 2026)

Settled by the orchestrator (ADR-135 Amendment 3): limits per engine, budgets in tokens, no usage per person; measured first on the pinned LiteLLM 1.101.0. Two lane-reviewer rounds (2 blockers and 9 must-fixes, then 3 must-fixes and 4 nits) and two gate findings, all fixed; every new test shown red (`P2_RED_RECORD.md`).
- **Figures equal a planted gateway record, every page read:** `test_model_usage_and_limits.py::test_the_figures_equal_a_planted_gateway_record`, `…every_page…`. Met.
- **Every route refuses without `manage_models` (11):** `test_model_admin_routes.py::test_every_models_route_refuses…`, the gateway seeing nothing. Met.
- **A limit stops the next request, in words:** `…request_rate_set_stops…`, `…token_budget…`, and through the analyst's route `…told_so_in_words_through_their_own_route`. Met.
- **Nothing identifying leaks:** `…no_prompt_answer_key_or_source_id…`, `…asking_person_s_id` (body and headers), `…no_engine_key…_log_record`, `test_gateway_backup.py::…no_engine_key…`. Met.
- **Keyboard and axe:** 11 keyboard cases, 28 axe scans (dark, light, GOV.UK). **Live:** 3 passed, platform lease on stack a taken 19:19:40. Met.
- **Gates** at `58ee62c` (tree `204d685b…`), main `1122bfa`: `make -k ci` green; `make test` 8660 passed, its 4 failures and 2 errors not the branch's (`gates/README.md`). Met.
- **Decisions taken:** an HMAC engine key per engine, never stored; hosted entries priced 1 a token; calls tagged `osprey:<engine>/<job>`; start retried with backoff.
- **Left:** per-team limits (L2.5's teams reached main as P2 closed: a further amendment); fallbacks; transcriptions and embeddings uncounted (tagging unmeasured); an old engine key outlives a changed master key.
- **Commits:** `56539af` (schemas) to `58ee62c`, then the gates and this report.
- **Requests:** commit `ff1da5e`'s two `MODELS_ACTIONS` ids from its diff. Ratify `packages/schemas`, `app.py` (the model routes and handler), `harness/backup.py` and `shell/placesByRole.json` (the rules lane's). Ratify `a11y/every-harness.spec.ts`, and `spec/00`, `spec/03` and `spec/04`. Ask the owner of `patterns/api.ts` to show `model_limit_reached`'s words.
- **Questions:** none. **Running:** nothing; no stack held.
