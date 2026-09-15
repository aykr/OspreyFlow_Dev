.PHONY: ci lint typecheck licence-check trivy trivy-image-ingest trivy-image-api schemas-check conformance-guard conformance test dev-up dev-down test-all glass-perf glass-a11y glass-keyboard

PY := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# Phase 0 exit criterion (docs/07_BUILD_PLAN.md): CI green; a PR adding a GPL
# dependency fails; a Pydantic model change not reflected in the generated
# TypeScript fails the build. See the Phase 0 plan for what each target proves.
ci: lint typecheck licence-check trivy trivy-image-ingest trivy-image-api schemas-check conformance-guard

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

test:
	$(PYTEST) --ignore=tests/conformance/graph_port --ignore=tests/ingest
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
	$(PYTEST) tests/conformance/graph_port tests/ingest tests/scenarios/test_phase3_working_set.py tests/services/api/test_valkey_store.py tests/services/api/test_statelessness.py
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
