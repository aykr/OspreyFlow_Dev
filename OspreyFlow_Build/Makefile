# The gates, the test suites and the release steps (`spec/06_DECISIONS.md` ADR-114 Amendment 2,
# the owner's ruling "New Makefile in Build"). They moved here from `OspreyFlow_Core/Makefile` so
# the product folder stands on its own. Each recipe runs in the product folder, as it always did,
# with this folder on `PYTHONPATH` — so every command and every relative path in it is unchanged.
# The reasoning each target used to carry in Core's Makefile is in git history (`git log -p
# OspreyFlow_Core/Makefile`) and in each tool's own docstring.
.PHONY: publish-user-repo ci core-check lint-tools licence-check design-check schemas-check authorized-query-check demo-guide-check demo-manifest domain-model-coverage-check route-coverage-check product-tree-link-check provenance-annotation-check decision-log-publication-check citation-check test-file-coverage-check conformance-guard conformance conformance-model conformance-model-vision golden-set test test-all idp-test exit-over-the-wire ci-status bundle seed-enron

CORE := ../OspreyFlow_Core
BUILD := $(CURDIR)
PY := .venv/bin/python
PYTEST := .venv/bin/pytest -c $(BUILD)/pytest.ini
IN_CORE := cd $(CORE) &&
TOOLS := PYTHONPATH=$(BUILD)

# Phase 0's exit criterion: CI green; a GPL dependency fails; a schema drift fails. Core's own
# gates first (lint, type check, image scans, the harness's accessibility suite), then these.
ci: core-check lint-tools licence-check design-check schemas-check authorized-query-check demo-guide-check domain-model-coverage-check route-coverage-check product-tree-link-check decision-log-publication-check provenance-annotation-check test-file-coverage-check citation-check conformance-guard bundle

core-check:
	$(MAKE) -C $(CORE) check

# This folder's own Node checks, linted with the product's ESLint configuration.
lint-tools:
	$(CORE)/node_modules/.bin/eslint -c $(CORE)/eslint.config.js tools

licence-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.licence_check
	$(IN_CORE) node $(BUILD)/tools/licence_check.mjs
	$(IN_CORE) node --test $(BUILD)/tests/licence_check/*.test.mjs
	@echo "licence-check: tests/licence_check/test_gpl_rejection.py and test_licence_check_mjs.test.mjs hold the proof"

# ADR-115 (E1): the design detector against DESIGN.md §9, Core's DESIGN.md held to the contract, and
# no colour literal in the Glass that DESIGN.md does not hold. tests/test_design_check.py and
# tests/test_colour_drift_check.py hold the proof that each can fail.
design-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.design_check
	$(IN_CORE) $(TOOLS) $(PY) -m tools.colour_drift_check

# ADR-041: mechanical control for the fetch-then-check authorization bug class.
authorized-query-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.authorized_query_check

demo-guide-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.demo_guide_check

demo-manifest:
	$(IN_CORE) $(PY) scripts/demo_registry.py
	$(IN_CORE) PYTHONPATH=. $(PY) -m scripts.demo_packs

# ADR-049 Stage 2 §5b: the bundle, manifest only (no --images); every packaging-time assertion runs
# against its staged files. `tests/harness/test_bundle_exit_test.py` is the opt-in exit test.
bundle:
	$(IN_CORE) PYTHONPATH=packages:$(BUILD) $(PY) -m tools.osprey_bundle --profile local-lite --out $(BUILD)/dist

domain-model-coverage-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.domain_model_coverage_check

route-coverage-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.route_coverage_check

# ADR-034 §B8: documentation-to-documentation references only.
product-tree-link-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.product_tree_link_check

provenance-annotation-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.provenance_annotation_check

decision-log-publication-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.decision_log_publication_check

citation-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.doc_citations_check

test-file-coverage-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.test_file_coverage_check

schemas-check:
	$(IN_CORE) $(TOOLS) $(PY) -m tools.schemas_check

# The four guard tests, one per port.
conformance-guard:
	$(IN_CORE) $(PYTEST) ../OspreyFlow_Build/tests/conformance -k test_guard

# GraphPort's suite and the recipe engine end to end — both need a live ArcadeDB:
# `docker run --rm -p 2480:2480 -e JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata123 -Darcadedb.gremlin.engine=groovy" arcadedata/arcadedb:26.10.1`
conformance:
	$(IN_CORE) $(PYTEST) ../OspreyFlow_Build/tests/conformance/graph_port ../OspreyFlow_Build/tests/ingest

# ModelPort's suite — needs LiteLLM in front of Ollama (`make -C ../OspreyFlow_Core dev-up`).
conformance-model:
	$(IN_CORE) $(PYTEST) ../OspreyFlow_Build/tests/conformance/model_port --ignore=../OspreyFlow_Build/tests/conformance/model_port/test_suite_vision.py ../OspreyFlow_Build/tests/scenarios/test_witness_statement_extraction.py

# `describe_image()` alone, on a slower cadence (ADR-020's Stage 2 addendum: a 1.8 GB model).
conformance-model-vision:
	$(IN_CORE) $(PYTEST) ../OspreyFlow_Build/tests/conformance/model_port/test_suite_vision.py

# The golden set's precision/recall gate — the same live LiteLLM/Ollama.
golden-set:
	$(IN_CORE) $(PYTEST) ../OspreyFlow_Build/tests/golden

# Kept in sync with `ci.yml`'s `test` job ignore list by `test-file-coverage-check`.
test:
	$(IN_CORE) $(PYTEST) --ignore=../OspreyFlow_Build/tests/conformance/graph_port --ignore=../OspreyFlow_Build/tests/conformance/model_port --ignore=../OspreyFlow_Build/tests/golden --ignore=../OspreyFlow_Build/tests/ingest --ignore=../OspreyFlow_Build/tests/scenarios/test_hmp_graph.py --ignore=../OspreyFlow_Build/tests/scenarios/test_witness_statement_extraction.py --ignore=../OspreyFlow_Build/tests/services/api/test_sites_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_tile_cache.py --ignore=../OspreyFlow_Build/tests/services/api/test_prefetch.py --ignore=../OspreyFlow_Build/tests/geocoder/test_match_live.py --ignore=../OspreyFlow_Build/tests/services/api/test_assessments.py --ignore=../OspreyFlow_Build/tests/test_case_seed.py --ignore=../OspreyFlow_Build/tests/services/api/test_investigation_access_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_link_notes_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_link_changes_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_entity_pictures.py --ignore=../OspreyFlow_Build/tests/services/api/test_link_type_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_suppression.py --ignore=../OspreyFlow_Build/tests/services/api/test_assessment_routes.py --ignore=../OspreyFlow_Build/tests/services/api/test_export.py --ignore=../OspreyFlow_Build/tests/services/api/test_export_routes.py --ignore=../OspreyFlow_Build/tests/services/api/test_valkey_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_ws_ticket.py --ignore=../OspreyFlow_Build/tests/services/api/test_statelessness.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase3_working_set.py --ignore=../OspreyFlow_Build/tests/services/api/test_change_stream.py --ignore=../OspreyFlow_Build/tests/services/api/test_alerts.py --ignore=../OspreyFlow_Build/tests/services/api/test_pattern_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_hotlists.py --ignore=../OspreyFlow_Build/tests/services/api/test_monitors.py --ignore=../OspreyFlow_Build/tests/services/api/test_evaluation.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase6_extraction_and_resolution.py --ignore=../OspreyFlow_Build/tests/resolve/test_projection_access_control.py --ignore=../OspreyFlow_Build/tests/resolve/test_trigger.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase6a_glass_surfaces.py --ignore=../OspreyFlow_Build/tests/services/api/test_access.py --ignore=../OspreyFlow_Build/tests/services/api/test_dossier_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/test_review.py --ignore=../OspreyFlow_Build/tests/services/api/test_review_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_studio_recipes_store.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_compute_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_explain_cluster_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_manual_resolution_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_resolution_threshold_access_control.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase7_stage6c_watch_routes.py --ignore=../OspreyFlow_Build/tests/scenarios/test_fixture_corp_shape.py --ignore=../OspreyFlow_Build/tests/services/api/test_worker.py --ignore=../OspreyFlow_Build/tests/services/api/test_worker_replicas.py --ignore=../OspreyFlow_Build/tests/services/api/test_revoked_principal_precheck.py --ignore=../OspreyFlow_Build/tests/harness/test_restore_exit_test.py --ignore=../OspreyFlow_Build/tests/harness/test_workspace_bundle.py --ignore=../OspreyFlow_Build/tests/harness/test_sustained_load.py --ignore=../OspreyFlow_Build/tests/harness/test_bundle_exit_test.py --ignore=../OspreyFlow_Build/tests/harness/test_harness_image.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase8_exit_criterion_end_to_end.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py --ignore=../OspreyFlow_Build/tests/harness/test_six_screen_live_exit.py
	$(MAKE) -C $(CORE) test-js

# The five token-exchange tests against a real Keycloak carrying this repository's own realm
# (owner ruling R8). Port 8082, so it never collides with a deployment's Keycloak on 8081.
idp-test:
	@$(IN_CORE) rm -rf .idp-test && mkdir -p .idp-test
	$(IN_CORE) PYTHONPATH=.:packages:$(BUILD) $(PY) -m tools.idp_test_realm --write-realm .idp-test/realm.json
	-docker rm -f osprey-idp-test >/dev/null 2>&1
	$(IN_CORE) docker run -d --name osprey-idp-test -p 8082:8080 \
	  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
	  -e KC_HEALTH_ENABLED=true \
	  -v "$$PWD/.idp-test/realm.json:/opt/keycloak/data/import/realm.json:ro" \
	  quay.io/keycloak/keycloak:26.0 start-dev --import-realm --features=token-exchange
	$(IN_CORE) PYTHONPATH=.:packages:$(BUILD) $(PY) -m tools.idp_test_realm --configure --issuer http://localhost:8082
	$(IN_CORE) OSPREY_TEST_KEYCLOAK_URL=http://localhost:8082 \
	  $(PYTEST) -v ../OspreyFlow_Build/tests/services/api/test_revoked_principal_precheck.py; \
	  status=$$?; docker rm -f osprey-idp-test >/dev/null 2>&1; rm -rf .idp-test; exit $$status

# Everything `make test` skips because it needs a live store, against a fresh `dev-up` ArcadeDB
# (`rm -fsv arcadedb` resets it without deleting the model caches; measured 27 September 2026).
test-all: idp-test
	$(IN_CORE) docker compose -f deploy/compose/dev.yaml rm -fsv arcadedb
	$(IN_CORE) docker compose -f deploy/compose/dev.yaml down
	$(IN_CORE) docker compose -f deploy/compose/dev.yaml up -d --wait
	$(IN_CORE) $(PYTEST) ../OspreyFlow_Build/tests/conformance/graph_port ../OspreyFlow_Build/tests/conformance/model_port ../OspreyFlow_Build/tests/golden ../OspreyFlow_Build/tests/scenarios/test_witness_statement_extraction.py ../OspreyFlow_Build/tests/ingest ../OspreyFlow_Build/tests/scenarios/test_phase3_working_set.py ../OspreyFlow_Build/tests/scenarios/test_hmp_graph.py ../OspreyFlow_Build/tests/services/api/test_valkey_store.py ../OspreyFlow_Build/tests/services/api/test_statelessness.py ../OspreyFlow_Build/tests/services/api/test_sites_store.py ../OspreyFlow_Build/tests/services/api/test_tile_cache.py ../OspreyFlow_Build/tests/services/api/test_prefetch.py ../OspreyFlow_Build/tests/geocoder/test_match_live.py ../OspreyFlow_Build/tests/services/api/test_assessments.py ../OspreyFlow_Build/tests/test_case_seed.py ../OspreyFlow_Build/tests/services/api/test_investigation_access_store.py ../OspreyFlow_Build/tests/services/api/test_link_notes_store.py ../OspreyFlow_Build/tests/services/api/test_link_changes_store.py ../OspreyFlow_Build/tests/services/api/test_entity_pictures.py ../OspreyFlow_Build/tests/services/api/test_link_type_store.py ../OspreyFlow_Build/tests/services/api/test_suppression.py ../OspreyFlow_Build/tests/services/api/test_assessment_routes.py ../OspreyFlow_Build/tests/services/api/test_export.py ../OspreyFlow_Build/tests/services/api/test_export_routes.py ../OspreyFlow_Build/tests/services/api/test_change_stream.py ../OspreyFlow_Build/tests/services/api/test_alerts.py ../OspreyFlow_Build/tests/services/api/test_pattern_store.py ../OspreyFlow_Build/tests/services/api/test_hotlists.py ../OspreyFlow_Build/tests/services/api/test_monitors.py ../OspreyFlow_Build/tests/services/api/test_evaluation.py ../OspreyFlow_Build/tests/resolve/test_projection_access_control.py ../OspreyFlow_Build/tests/resolve/test_trigger.py ../OspreyFlow_Build/tests/scenarios/test_phase6a_glass_surfaces.py ../OspreyFlow_Build/tests/services/api/test_access.py ../OspreyFlow_Build/tests/services/api/test_dossier_access_control.py ../OspreyFlow_Build/tests/services/api/test_review.py ../OspreyFlow_Build/tests/services/api/test_review_store.py ../OspreyFlow_Build/tests/services/api/test_studio_recipes_store.py ../OspreyFlow_Build/tests/services/api/working_set/test_compute_access_control.py ../OspreyFlow_Build/tests/services/api/working_set/test_explain_cluster_access_control.py ../OspreyFlow_Build/tests/services/api/working_set/test_manual_resolution_access_control.py ../OspreyFlow_Build/tests/services/api/working_set/test_resolution_threshold_access_control.py ../OspreyFlow_Build/tests/scenarios/test_phase7_stage6c_watch_routes.py ../OspreyFlow_Build/tests/scenarios/test_fixture_corp_shape.py ../OspreyFlow_Build/tests/services/api/test_worker.py ../OspreyFlow_Build/tests/services/api/test_worker_replicas.py
	$(IN_CORE) npm run test:integration --workspace apps/workspace

# Owner ruling R5's closing-pass proof against a rendered deployment; never in `ci`.
exit-over-the-wire:
	$(IN_CORE) OSPREY_TEST_OVER_THE_WIRE=1 $(PYTEST) -p no:randomly \
	  ../OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py

# Is CI green on the pushed commit — needs network access and an Actions-read token.
ci-status:
	$(IN_CORE) PYTHONPATH=.:packages:$(BUILD) $(PY) -m tools.ci_status_check

# REAL data, this machine only (ADR-053): refuses without the local exceptions entry.
seed-enron:
	$(IN_CORE) PYTHONPATH=.:packages:$(BUILD) $(PY) -m internal_demos.seed enron --stop-api

# The user repository (ADR-114 Amendment 2): Core exactly as committed at COMMIT, into the empty
# folder OUT outside this repository — or nothing, naming each file that must not leave. Pushing is
# the owner's. Example: make publish-user-repo COMMIT=HEAD OUT=../../ospreyflow-user
COMMIT ?= HEAD
publish-user-repo:
	@test -n "$(OUT)" || { echo "publish-user-repo: say where, e.g. OUT=../../ospreyflow-user"; exit 2; }
	$(IN_CORE) PYTHONPATH=.:packages:$(BUILD) $(PY) -m tools.publish_user_repo $(COMMIT) $(abspath $(OUT))
