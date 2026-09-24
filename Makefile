.PHONY: ci lint typecheck licence-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace schemas-check authorized-query-check demo-guide-check domain-model-coverage-check route-coverage-check product-tree-link-check decision-log-publication-check conformance-guard conformance test dev-up dev-down test-all glass-perf glass-a11y glass-keyboard glass-map-verify

PY := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# Phase 0 exit criterion (docs/07_BUILD_PLAN.md): CI green; a PR adding a GPL
# dependency fails; a Pydantic model change not reflected in the generated
# TypeScript fails the build. See the Phase 0 plan for what each target proves.
ci: lint typecheck licence-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace schemas-check authorized-query-check demo-guide-check domain-model-coverage-check route-coverage-check product-tree-link-check decision-log-publication-check test-file-coverage-check conformance-guard

lint:
	$(RUFF) check .
	npm run lint

typecheck:
	$(MYPY) packages services
	npm run typecheck

licence-check:
	$(PY) scripts/licence_check.py
	npm run licence-check
	node --test tests/licence_check/*.test.mjs
	@echo "licence-check: see tests/licence_check/test_gpl_rejection.py (Python half) and"
	@echo "tests/licence_check/test_licence_check_mjs.test.mjs (Node half) for the deterministic proof"

# `06_DECISIONS.md` ADR-041 (accepted, option (b)): mechanical, not documentary, control for the
# fetch-then-check authorization bug class. See scripts/authorized_query_check.py's own docstring.
authorized-query-check:
	$(PY) scripts/authorized_query_check.py
	@echo "authorized-query-check: see tests/authorized_query_check/ for the deterministic proof"

# `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry: a stand-in for ADR-035's own
# still-unbuilt fail-closed demo registry. See scripts/demo_guide_check.py's own docstring.
demo-guide-check:
	$(PY) scripts/demo_guide_check.py
	@echo "demo-guide-check: see tests/test_demo_guide_registry_check.py for the deterministic proof"

# `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry. Allowlists of current debt at
# tests/fixtures/{domain_model_coverage,route_coverage}_allowlist.txt — see each script's own
# docstring.
domain-model-coverage-check:
	$(PY) scripts/domain_model_coverage_check.py
	@echo "domain-model-coverage-check: see tests/test_domain_model_coverage_check.py for the deterministic proof"

route-coverage-check:
	$(PY) scripts/route_coverage_check.py
	@echo "route-coverage-check: see tests/test_route_coverage_check.py for the deterministic proof"

# `06_DECISIONS.md` ADR-034 §B8. Allowlist of current debt at
# tests/fixtures/product_tree_link_allowlist.txt — see scripts/product_tree_link_check.py's own
# docstring for why this is scoped to documentation-to-documentation references only, and how it
# differs from the still-open doc_citations_check.py question.
product-tree-link-check:
	$(PY) scripts/product_tree_link_check.py
	@echo "product-tree-link-check: see tests/test_product_tree_link_check.py for the deterministic proof"

# tests/fixtures/decision_log_publication_allowlist.txt — 06_DECISIONS.md ADR-034 §B10's own filtered
# decision log, checked one level down from product-tree-link-check: does a PRODUCT ADR cite a PROCESS
# one by number. See scripts/decision_log_publication_check.py's own docstring for the full reasoning.
decision-log-publication-check:
	$(PY) scripts/decision_log_publication_check.py
	@echo "decision-log-publication-check: see tests/test_decision_log_publication_check.py for the deterministic proof"

# Found and fixed four test files running in no intended CI job — `test_pattern_store.py`,
# `test_alerts.py`, `test_change_stream.py`, `test_assessment_routes.py` — before this gate
# existed, each by accident. Found two more (`test_fixture_corp_shape.py`, `test_worker.py`) on
# this gate's own first real run. See scripts/test_file_coverage_check.py's own docstring.
test-file-coverage-check:
	$(PY) scripts/test_file_coverage_check.py
	@echo "test-file-coverage-check: see tests/test_test_file_coverage_check.py for the deterministic proof"

trivy:
	trivy fs --exit-code 1 --severity HIGH,CRITICAL --include-dev-deps --skip-dirs node_modules,.venv .

# `trivy image` per service, added in the phase that gives it a Dockerfile
# (docs/07_BUILD_PLAN.md, "Standing rules for the whole build") — not
# batched into Phase 8. `--ignore-unfixed`: unlike the fs scan above, an
# image scan turns up base-OS packages this service never touches (login,
# mount, ncurses) with no upstream fix yet; failing CI on those forever is
# noise, not a gate. A vulnerability in a package we actually chose — a
# Python dependency, or an OS package with a fix available — still fails.
trivy-image-ingest:
	docker build -f services/ingest/Dockerfile -t ospreyflow/ingest:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/ingest:ci

# services/api's Dockerfile, Phase 3's own — same reasoning as
# trivy-image-ingest above.
trivy-image-api:
	docker build -f services/api/Dockerfile -t ospreyflow/api:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/api:ci

# apps/workspace's Dockerfile — Phase 4's own, paid at Stage 2 §5a as a
# recorded rule 8 repayment rather than an exception (docs/06_DECISIONS.md
# ADR-049). Same reasoning as the two above; the base is Alpine rather than
# Debian, which changes nothing about the gate.
trivy-image-workspace:
	docker build -f apps/workspace/Dockerfile -t ospreyflow/workspace:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/workspace:ci

schemas-check:
	$(PY) scripts/schemas_check.py

# The four guard tests from Phase 0 plan §2.A / §3.4 job 6 — one per port.
conformance-guard:
	$(PYTEST) tests/conformance -k test_guard

# GraphPort's real conformance suite (Phase 1) and the recipe-engine
# end-to-end test (Phase 2) — both need a live ArcadeDB.
# `docker run --rm -p 2480:2480 -e JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata123" arcadedata/arcadedb:24.11.1`
conformance:
	$(PYTEST) tests/conformance/graph_port tests/ingest

# ModelPort's real conformance suite (Phase 6 Stage 1) — needs a live LiteLLM
# proxy in front of Ollama, both brought up by `make dev-up` (`deploy/compose/
# dev.yaml`'s `ollama`/`litellm` services, pinned per docs/06_DECISIONS.md
# ADR-020). Excludes `test_suite_vision.py` deliberately — see
# `conformance-model-vision` below.
conformance-model:
	$(PYTEST) tests/conformance/model_port --ignore=tests/conformance/model_port/test_suite_vision.py tests/scenarios/test_witness_statement_extraction.py

# `describe_image()`'s own conformance case, run separately from the target
# above on a slower cadence (nightly / merge-to-main, not every PR) —
# `docs/06_DECISIONS.md` ADR-020's Stage 2 addendum: a vision-language model
# is materially heavier (1.8GB) than any of the other three pinned models.
conformance-model-vision:
	$(PYTEST) tests/conformance/model_port/test_suite_vision.py

# The golden set's precision/recall CI gate (Phase 6 Stage 3,
# docs/03_CONDUIT_MIDDLEWARE.md §5.2, standing rule 5) — needs the same live
# LiteLLM/Ollama as `conformance-model`. Twelve runs per case
# (`tests/golden/harness.py`'s own docstring has the measured reasoning), so
# this is slower per-case than the conformance suite's own single-shot checks.
golden-set:
	$(PYTEST) tests/golden

# Kept in sync with .github/workflows/ci.yml's own `test` job ignore list — found badly out of
# sync (22 files ci.yml correctly wires into `conformance` were neither ignored here nor listed in
# `test-all` below, so `make test` would attempt them with no live service up) by
# scripts/test_file_coverage_check.py's own first real run; fixed alongside that gate landing.
test:
	$(PYTEST) --ignore=tests/conformance/graph_port --ignore=tests/conformance/model_port --ignore=tests/golden --ignore=tests/ingest --ignore=tests/scenarios/test_hmp_graph.py --ignore=tests/scenarios/test_witness_statement_extraction.py --ignore=tests/services/api/test_sites_store.py --ignore=tests/services/api/test_tile_cache.py --ignore=tests/services/api/test_prefetch.py --ignore=tests/geocoder/test_match_live.py --ignore=tests/services/api/test_assessments.py --ignore=tests/services/api/test_assessment_routes.py --ignore=tests/services/api/test_export.py --ignore=tests/services/api/test_export_routes.py --ignore=tests/services/api/test_valkey_store.py --ignore=tests/services/api/test_statelessness.py --ignore=tests/scenarios/test_phase3_working_set.py --ignore=tests/services/api/test_change_stream.py --ignore=tests/services/api/test_alerts.py --ignore=tests/services/api/test_pattern_store.py --ignore=tests/services/api/test_hotlists.py --ignore=tests/services/api/test_monitors.py --ignore=tests/services/api/test_evaluation.py --ignore=tests/scenarios/test_phase6_extraction_and_resolution.py --ignore=tests/resolve/test_projection_access_control.py --ignore=tests/resolve/test_trigger.py --ignore=tests/scenarios/test_phase6a_glass_surfaces.py --ignore=tests/services/api/test_access.py --ignore=tests/services/api/test_dossier_access_control.py --ignore=tests/services/api/test_review.py --ignore=tests/services/api/test_review_store.py --ignore=tests/services/api/test_studio_recipes_store.py --ignore=tests/services/api/working_set/test_compute_access_control.py --ignore=tests/services/api/working_set/test_explain_cluster_access_control.py --ignore=tests/services/api/working_set/test_manual_resolution_access_control.py --ignore=tests/services/api/working_set/test_resolution_threshold_access_control.py --ignore=tests/scenarios/test_phase7_stage6c_watch_routes.py --ignore=tests/scenarios/test_fixture_corp_shape.py --ignore=tests/services/api/test_worker.py --ignore=tests/services/api/test_worker_replicas.py --ignore=tests/services/api/test_revoked_principal_precheck.py
	npm test --workspace apps/workspace

# Phase 3 (docs/07_BUILD_PLAN.md): "Add make dev-up bringing up ArcadeDB,
# MinIO, Valkey and Postgres so the full suite runs locally. The
# currently-skipped tests should be runnable on demand, not only in CI."
# `deploy/compose/dev.yaml`'s own header explains why this is a dev
# convenience, not the harness. `--wait` blocks until every service's
# healthcheck passes, so `make dev-up && make test-all` needs no manual
# polling.
dev-up:
	docker compose -f deploy/compose/dev.yaml up -d --wait

dev-down:
	docker compose -f deploy/compose/dev.yaml down -v

# Everything `make test` skips because it needs a live store, run
# together against whatever `make dev-up` brought up. `npm run
# test:integration` (apps/workspace) is here too, not in `make test` — its
# `deltaClient.integration.test.ts` needs the same dev-up stack.
# Volumes are dropped before this target runs, from 24 September 2026 (owner's decision;
# 07_BUILD_PLAN.md Stage 2a). Measured the same day: the identical batch against an accumulated
# ArcadeDB produced 94 failed / 49 passed in 24:51, and against fresh volumes 7 failed / 136 passed
# in 6:38. Every Floor B figure taken before this change was measured against accumulated state.
test-all:
	docker compose -f deploy/compose/dev.yaml down -v
	docker compose -f deploy/compose/dev.yaml up -d --wait
	$(PYTEST) tests/conformance/graph_port tests/conformance/model_port tests/golden tests/scenarios/test_witness_statement_extraction.py tests/ingest tests/scenarios/test_phase3_working_set.py tests/scenarios/test_hmp_graph.py tests/services/api/test_valkey_store.py tests/services/api/test_statelessness.py tests/services/api/test_sites_store.py tests/services/api/test_tile_cache.py tests/services/api/test_prefetch.py tests/geocoder/test_match_live.py tests/services/api/test_assessments.py tests/services/api/test_assessment_routes.py tests/services/api/test_export.py tests/services/api/test_export_routes.py tests/services/api/test_change_stream.py tests/services/api/test_alerts.py tests/services/api/test_pattern_store.py tests/services/api/test_hotlists.py tests/services/api/test_monitors.py tests/services/api/test_evaluation.py tests/resolve/test_projection_access_control.py tests/resolve/test_trigger.py tests/scenarios/test_phase6a_glass_surfaces.py tests/services/api/test_access.py tests/services/api/test_dossier_access_control.py tests/services/api/test_review.py tests/services/api/test_review_store.py tests/services/api/test_studio_recipes_store.py tests/services/api/working_set/test_compute_access_control.py tests/services/api/working_set/test_explain_cluster_access_control.py tests/services/api/working_set/test_manual_resolution_access_control.py tests/services/api/working_set/test_resolution_threshold_access_control.py tests/scenarios/test_phase7_stage6c_watch_routes.py tests/scenarios/test_fixture_corp_shape.py tests/services/api/test_worker.py tests/services/api/test_worker_replicas.py tests/services/api/test_revoked_principal_precheck.py
	npm run test:integration --workspace apps/workspace

# `docs/02_GLASS_FRONTEND.md` §5's performance budget, as a CI gate
# (`apps/workspace/perf/perf.spec.ts`'s own docstring: a software-WebGL
# regression proxy, not the literal hardware numbers). Needs a Chromium
# binary: `npx playwright install chromium --with-deps` once per machine.
glass-perf:
	npm run test:perf --workspace apps/workspace

# `docs/02_GLASS_FRONTEND.md` §6's contrast floor, as a CI gate, both
# themes (`apps/workspace/a11y/a11y.spec.ts`).
glass-a11y:
	npm run test:a11y --workspace apps/workspace

# `docs/07_BUILD_PLAN.md` Phase 4's "keyboard navigation reaches every
# canvas action" exit clause, as a CI gate, not an assertion in prose
# (`apps/workspace/keyboard/keyboard.spec.ts`) — a scripted walkthrough
# that never calls `page.mouse`/`.click()`.
glass-keyboard:
	npm run test:keyboard --workspace apps/workspace

# `docs/00_ARCHITECTURE.md` §1.2.1's Verify contrast-floor check — a
# rendered-pixel/reference-image comparison of a fixture graph over the
# basemap's own chrome colours (`apps/workspace/map-verify/contrast.spec.ts`),
# genuinely different from `glass-a11y`'s axe-core DOM-rule check. Dark
# theme only for now — see `map-verify/showcase.tsx`'s own docstring.
glass-map-verify:
	npm run test:map-verify --workspace apps/workspace
