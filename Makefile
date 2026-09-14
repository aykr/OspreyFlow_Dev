.PHONY: ci lint typecheck licence-check trivy trivy-image-ingest schemas-check conformance-guard conformance test

PY := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# Phase 0 exit criterion (docs/07_BUILD_PLAN.md): CI green; a PR adding a GPL
# dependency fails; a Pydantic model change not reflected in the generated
# TypeScript fails the build. See the Phase 0 plan for what each target proves.
ci: lint typecheck licence-check trivy trivy-image-ingest schemas-check conformance-guard

lint:
	$(RUFF) check .
	npm run lint

typecheck:
	$(MYPY) packages
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
	docker build -f services/ingest/Dockerfile -t mantisnexus/ingest:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed mantisnexus/ingest:ci

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
