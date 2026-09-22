.PHONY: ci lint typecheck licence-check trivy trivy-image-ingest trivy-image-api schemas-check authorized-query-check demo-guide-check domain-model-coverage-check route-coverage-check conformance-guard conformance test dev-up dev-down test-all glass-perf glass-a11y glass-keyboard glass-map-verify

PY := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# Phase 0 exit criterion (docs/07_BUILD_PLAN.md): CI green; a PR adding a GPL
# dependency fails; a Pydantic model change not reflected in the generated
# TypeScript fails the build. See the Phase 0 plan for what each target proves.
ci: lint typecheck licence-check trivy trivy-image-ingest trivy-image-api schemas-check authorized-query-check demo-guide-check domain-model-coverage-check route-coverage-check conformance-guard

lint:
	$(RUFF) check .
	npm run lint

typecheck:
	$(MYPY) packages services
	npm run typecheck

licence-check:
	$(PY) scripts/licence_check.py
	npm run licence-check
	@echo "licence-check: see tests/licence_check/test_gpl_rejection.py for the deterministic proof"

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

test:
	$(PYTEST) --ignore=tests/conformance/graph_port --ignore=tests/conformance/model_port --ignore=tests/golden --ignore=tests/ingest --ignore=tests/scenarios/test_hmp_graph.py --ignore=tests/scenarios/test_witness_statement_extraction.py --ignore=tests/services/api/test_sites_store.py --ignore=tests/services/api/test_tile_cache.py --ignore=tests/services/api/test_prefetch.py --ignore=tests/geocoder/test_match_live.py --ignore=tests/services/api/test_assessments.py
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
test-all:
	$(PYTEST) tests/conformance/graph_port tests/conformance/model_port tests/golden tests/scenarios/test_witness_statement_extraction.py tests/ingest tests/scenarios/test_phase3_working_set.py tests/scenarios/test_hmp_graph.py tests/services/api/test_valkey_store.py tests/services/api/test_statelessness.py tests/services/api/test_sites_store.py tests/services/api/test_tile_cache.py tests/services/api/test_prefetch.py tests/geocoder/test_match_live.py tests/services/api/test_assessments.py
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
