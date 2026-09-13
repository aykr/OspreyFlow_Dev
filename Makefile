.PHONY: ci lint typecheck licence-check trivy schemas-check conformance-guard conformance test

PY := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# Phase 0 exit criterion (docs/07_BUILD_PLAN.md): CI green; a PR adding a GPL
# dependency fails; a Pydantic model change not reflected in the generated
# TypeScript fails the build. See the Phase 0 plan for what each target proves.
ci: lint typecheck licence-check trivy schemas-check conformance-guard

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

schemas-check:
	$(PY) scripts/schemas_check.py

# The four guard tests from Phase 0 plan §2.A / §3.4 job 6 — one per port.
conformance-guard:
	$(PYTEST) tests/conformance -k test_guard

# GraphPort's real conformance suite (Phase 1) — needs a live ArcadeDB.
# `docker run --rm -p 2480:2480 -e JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata123" arcadedata/arcadedb:24.11.1`
conformance:
	$(PYTEST) tests/conformance/graph_port

test:
	$(PYTEST) --ignore=tests/conformance/graph_port
