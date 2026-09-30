.PHONY: ci idp-test ci-status lint typecheck licence-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness schemas-check authorized-query-check demo-guide-check demo-manifest domain-model-coverage-check route-coverage-check product-tree-link-check decision-log-publication-check conformance-guard conformance test launch refresh seed-paysim register-sign-in dev-up dev-down docker-clean test-all glass-perf glass-a11y glass-keyboard glass-map-verify glass-live exit-over-the-wire harness-keyboard harness-a11y bundle

PY := .venv/bin/python
PYTEST := .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# Phase 0 exit criterion (process/07_BUILD_PLAN.md): CI green; a PR adding a GPL
# dependency fails; a Pydantic model change not reflected in the generated
# TypeScript fails the build. See the Phase 0 plan for what each target proves.
ci: lint typecheck licence-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness schemas-check authorized-query-check demo-guide-check domain-model-coverage-check route-coverage-check product-tree-link-check decision-log-publication-check provenance-annotation-check test-file-coverage-check citation-check conformance-guard harness-a11y bundle

lint:
	$(RUFF) check .
	npm run lint

typecheck:
# `harness` joined this target on 24 September 2026 (ADR-049 Stage 2 §3/§4). It had been
# outside it since Stage 2 §1 — new Phase 8 code written under a gate that never looked at
# it — and adding it was a red-then-green, not a formality: seven real errors, every one an
# untyped `dict`/`list` crossing a boundary this harness passes parsed compose documents and
# Keycloak admin payloads across.
	$(MYPY) packages services harness
	npm run typecheck

licence-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.licence_check
	npm run licence-check
	node --test ../OspreyFlow_Build/tests/licence_check/*.test.mjs
	@echo "licence-check: see ../OspreyFlow_Build/tests/licence_check/test_gpl_rejection.py (Python half) and"
	@echo "../OspreyFlow_Build/tests/licence_check/test_licence_check_mjs.test.mjs (Node half) for the deterministic proof"

# `06_DECISIONS.md` ADR-041 (accepted, option (b)): mechanical, not documentary, control for the
# fetch-then-check authorization bug class. See ../OspreyFlow_Build/tools/authorized_query_check.py's own docstring.
authorized-query-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.authorized_query_check
	@echo "authorized-query-check: see ../OspreyFlow_Build/tests/authorized_query_check/ for the deterministic proof"

# `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry: a stand-in for ADR-035's own
# still-unbuilt fail-closed demo registry. See ../OspreyFlow_Build/tools/demo_guide_check.py's own docstring.
demo-guide-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.demo_guide_check
	@echo "demo-guide-check: see ../OspreyFlow_Build/tests/test_demo_guide_registry_check.py for the deterministic proof"

# `06_DECISIONS.md` ADR-035 §C1's own fail-closed shipped/internal registry, now built
# (scripts/demo_registry.py) — "what will ship is inspectable before shipping rather than after."
demo-manifest:
	$(PY) scripts/demo_registry.py
	@echo "demo-manifest: see ../OspreyFlow_Build/tests/demo_registry/test_fail_closed.py for the deterministic proof"

# `06_DECISIONS.md` ADR-049 Stage 2 §5b — the real `osprey bundle` command
# (../OspreyFlow_Build/tools/osprey_bundle.py). Manifest-only here (no --images): every packaging-time assertion
# (ADR-034 §B7, ADR-035 §C2, LICENSE/NOTICE, the documentation site) still runs against this
# bundle's own staged files, since none of those depend on whether images are archived.
# `--images`'s own real archive-and-install path is the exit test, run for real rather than as a
# fast CI-able target (../OspreyFlow_Build/tests/harness/test_bundle_exit_test.py, opt-in via OSPREY_TEST_DIST_BUNDLE=1 —
# it needs Docker and takes minutes).
bundle:
	PYTHONPATH=packages:../OspreyFlow_Build $(PY) -m tools.osprey_bundle --profile local-lite --out ../OspreyFlow_Build/dist
	@echo "bundle: see ../OspreyFlow_Build/tests/test_osprey_bundle.py and ../OspreyFlow_Build/tests/packaging/ for the deterministic proof,"
	@echo "and ../OspreyFlow_Build/tests/harness/test_bundle_exit_test.py for the --images/install-from-bundle exit test"

# `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry. Allowlists of current debt at
# ../OspreyFlow_Build/tests/fixtures/{domain_model_coverage,route_coverage}_allowlist.txt — see each script's own
# docstring.
domain-model-coverage-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.domain_model_coverage_check
	@echo "domain-model-coverage-check: see ../OspreyFlow_Build/tests/test_domain_model_coverage_check.py for the deterministic proof"

route-coverage-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.route_coverage_check
	@echo "route-coverage-check: see ../OspreyFlow_Build/tests/test_route_coverage_check.py for the deterministic proof"

# `06_DECISIONS.md` ADR-034 §B8. Allowlist of current debt at
# ../OspreyFlow_Build/tests/fixtures/product_tree_link_allowlist.txt — see ../OspreyFlow_Build/tools/product_tree_link_check.py's own
# docstring for why this is scoped to documentation-to-documentation references only, and how it
# differs from doc_citations_check.py, which asks whether a citation resolves rather than whether
# an Apache-scoped file cites a private one.
product-tree-link-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.product_tree_link_check
	@echo "product-tree-link-check: see ../OspreyFlow_Build/tests/test_product_tree_link_check.py for the deterministic proof"

# 07_BUILD_PLAN.md Stage 3b: no build-calendar coordinate (Phase N / Stage N / round N / "found
# during") in the Apache-scoped specification. See ../OspreyFlow_Build/tools/provenance_annotation_check.py's own
# docstring for the full reasoning and why 06_DECISIONS.md is deliberately out of its scope.
provenance-annotation-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.provenance_annotation_check
	@echo "provenance-annotation-check: see ../OspreyFlow_Build/tests/test_provenance_annotation_check.py for the deterministic proof"

# ../OspreyFlow_Build/tests/fixtures/decision_log_publication_allowlist.txt — 06_DECISIONS.md ADR-034 §B10's own filtered
# decision log, checked one level down from product-tree-link-check: does a PRODUCT ADR cite a PROCESS
# one by number. See ../OspreyFlow_Build/tools/decision_log_publication_check.py's own docstring for the full reasoning.
decision-log-publication-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.decision_log_publication_check
	@echo "decision-log-publication-check: see ../OspreyFlow_Build/tests/test_decision_log_publication_check.py for the deterministic proof"

# Every backticked repository path that names a file must name a file that is there. Added
# 25 September 2026 after three citations to files that had never existed were found by accident
# in one afternoon — a Dockerfile naming a test that was never written, and a keyboard registry
# naming a coverage script that was never written, repeated into two documents. This gate was red
# on 38 citations when it was first run, which is its red-then-green record; three were the
# originals above, corrected on sight. Of the rest, a citation of a `.gitignore`-matched path
# (`config/real_data_exceptions.yaml`) passes without an allowlist entry, and every other one was
# corrected in place — the allowlist (`../OspreyFlow_Build/tests/fixtures/citation_allowlist.txt`) is empty and absent
# on this repository today, not populated with the remainder.
citation-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.doc_citations_check
	@echo "citation-check: see ../OspreyFlow_Build/tests/test_doc_citations_check.py for the red-then-green proof"

# Found and fixed four test files running in no intended CI job — `test_pattern_store.py`,
# `test_alerts.py`, `test_change_stream.py`, `test_assessment_routes.py` — before this gate
# existed, each by accident. Found two more (`test_fixture_corp_shape.py`, `test_worker.py`) on
# this gate's own first real run. See ../OspreyFlow_Build/tools/test_file_coverage_check.py's own docstring.
test-file-coverage-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.test_file_coverage_check
	@echo "test-file-coverage-check: see ../OspreyFlow_Build/tests/test_test_file_coverage_check.py for the deterministic proof"

trivy:
	trivy fs --exit-code 1 --severity HIGH,CRITICAL --include-dev-deps --skip-dirs node_modules,.venv .

# `trivy image` per service, added in the phase that gives it a Dockerfile
# (process/07_BUILD_PLAN.md, "Standing rules for the whole build") — not
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
# recorded rule 8 repayment rather than an exception (spec/06_DECISIONS.md
# ADR-049). Same reasoning as the two above; the base is Alpine rather than
# Debian, which changes nothing about the gate.
trivy-image-workspace:
	docker build -f apps/workspace/Dockerfile -t ospreyflow/workspace:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/workspace:ci

# harness/Dockerfile — Stage 2 §5b's own bootstrap image (spec/05_DEPLOYMENT.md §2's "one Docker
# command"), paid here as a rule-8 repayment the same way apps/workspace's was at Stage 2 §5a.
trivy-image-harness:
	docker build -f harness/Dockerfile -t ospreyflow/harness:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/harness:ci

schemas-check:
	PYTHONPATH=../OspreyFlow_Build $(PY) -m tools.schemas_check

# The four guard tests from Phase 0 plan §2.A / §3.4 job 6 — one per port.
conformance-guard:
	$(PYTEST) ../OspreyFlow_Build/tests/conformance -k test_guard

# GraphPort's real conformance suite (Phase 1) and the recipe-engine
# end-to-end test (Phase 2) — both need a live ArcadeDB.
# `docker run --rm -p 2480:2480 -e JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata123" arcadedata/arcadedb:25.5.1`
conformance:
	$(PYTEST) ../OspreyFlow_Build/tests/conformance/graph_port ../OspreyFlow_Build/tests/ingest

# ModelPort's real conformance suite (Phase 6 Stage 1) — needs a live LiteLLM
# proxy in front of Ollama, both brought up by `make dev-up` (`deploy/compose/
# dev.yaml`'s `ollama`/`litellm` services, pinned per spec/06_DECISIONS.md
# ADR-020). Excludes `test_suite_vision.py` deliberately — see
# `conformance-model-vision` below.
conformance-model:
	$(PYTEST) ../OspreyFlow_Build/tests/conformance/model_port --ignore=../OspreyFlow_Build/tests/conformance/model_port/test_suite_vision.py ../OspreyFlow_Build/tests/scenarios/test_witness_statement_extraction.py

# `describe_image()`'s own conformance case, run separately from the target
# above on a slower cadence (nightly / merge-to-main, not every PR) —
# `spec/06_DECISIONS.md` ADR-020's Stage 2 addendum: a vision-language model
# is materially heavier (1.8GB) than any of the other three pinned models.
conformance-model-vision:
	$(PYTEST) ../OspreyFlow_Build/tests/conformance/model_port/test_suite_vision.py

# The golden set's precision/recall CI gate (Phase 6 Stage 3,
# spec/03_CONDUIT_MIDDLEWARE.md §5.2, standing rule 5) — needs the same live
# LiteLLM/Ollama as `conformance-model`. Twelve runs per case
# (`../OspreyFlow_Build/tests/golden/harness.py`'s own docstring has the measured reasoning), so
# this is slower per-case than the conformance suite's own single-shot checks.
golden-set:
	$(PYTEST) ../OspreyFlow_Build/tests/golden

# Kept in sync with .github/workflows/ci.yml's own `test` job ignore list — found badly out of
# sync (22 files ci.yml correctly wires into `conformance` were neither ignored here nor listed in
# `test-all` below, so `make test` would attempt them with no live service up) by
# ../OspreyFlow_Build/tools/test_file_coverage_check.py's own first real run; fixed alongside that gate landing.
test:
	$(PYTEST) --ignore=../OspreyFlow_Build/tests/conformance/graph_port --ignore=../OspreyFlow_Build/tests/conformance/model_port --ignore=../OspreyFlow_Build/tests/golden --ignore=../OspreyFlow_Build/tests/ingest --ignore=../OspreyFlow_Build/tests/scenarios/test_hmp_graph.py --ignore=../OspreyFlow_Build/tests/scenarios/test_witness_statement_extraction.py --ignore=../OspreyFlow_Build/tests/services/api/test_sites_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_tile_cache.py --ignore=../OspreyFlow_Build/tests/services/api/test_prefetch.py --ignore=../OspreyFlow_Build/tests/geocoder/test_match_live.py --ignore=../OspreyFlow_Build/tests/services/api/test_assessments.py --ignore=../OspreyFlow_Build/tests/services/api/test_suppression.py --ignore=../OspreyFlow_Build/tests/services/api/test_assessment_routes.py --ignore=../OspreyFlow_Build/tests/services/api/test_export.py --ignore=../OspreyFlow_Build/tests/services/api/test_export_routes.py --ignore=../OspreyFlow_Build/tests/services/api/test_valkey_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_ws_ticket.py --ignore=../OspreyFlow_Build/tests/services/api/test_statelessness.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase3_working_set.py --ignore=../OspreyFlow_Build/tests/services/api/test_change_stream.py --ignore=../OspreyFlow_Build/tests/services/api/test_alerts.py --ignore=../OspreyFlow_Build/tests/services/api/test_pattern_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_hotlists.py --ignore=../OspreyFlow_Build/tests/services/api/test_monitors.py --ignore=../OspreyFlow_Build/tests/services/api/test_evaluation.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase6_extraction_and_resolution.py --ignore=../OspreyFlow_Build/tests/resolve/test_projection_access_control.py --ignore=../OspreyFlow_Build/tests/resolve/test_trigger.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase6a_glass_surfaces.py --ignore=../OspreyFlow_Build/tests/services/api/test_access.py --ignore=../OspreyFlow_Build/tests/services/api/test_dossier_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/test_review.py --ignore=../OspreyFlow_Build/tests/services/api/test_review_store.py --ignore=../OspreyFlow_Build/tests/services/api/test_studio_recipes_store.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_compute_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_explain_cluster_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_manual_resolution_access_control.py --ignore=../OspreyFlow_Build/tests/services/api/working_set/test_resolution_threshold_access_control.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase7_stage6c_watch_routes.py --ignore=../OspreyFlow_Build/tests/scenarios/test_fixture_corp_shape.py --ignore=../OspreyFlow_Build/tests/services/api/test_worker.py --ignore=../OspreyFlow_Build/tests/services/api/test_worker_replicas.py --ignore=../OspreyFlow_Build/tests/services/api/test_revoked_principal_precheck.py --ignore=../OspreyFlow_Build/tests/harness/test_restore_exit_test.py --ignore=../OspreyFlow_Build/tests/harness/test_workspace_bundle.py --ignore=../OspreyFlow_Build/tests/harness/test_sustained_load.py --ignore=../OspreyFlow_Build/tests/harness/test_bundle_exit_test.py --ignore=../OspreyFlow_Build/tests/harness/test_harness_image.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase8_exit_criterion_end_to_end.py --ignore=../OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py --ignore=../OspreyFlow_Build/tests/harness/test_six_screen_live_exit.py
	npm test --workspace apps/workspace
	npm test --workspace apps/harness

# Phase 3 (process/07_BUILD_PLAN.md): "Add make dev-up bringing up ArcadeDB,
# MinIO, Valkey and Postgres so the full suite runs locally. The
# currently-skipped tests should be runnable on demand, not only in CI."
# `deploy/compose/dev.yaml`'s own header explains why this is a dev
# convenience, not the harness. `--wait` blocks until every service's
# healthcheck passes, so `make dev-up && make test-all` needs no manual
# polling.
# The one screen for starting and opening the Glass, the Ingest Studio or the Admin console
# (`scripts/launch.py`'s own docstring has why it exists and what it deliberately does not do).
# It starts an *already-rendered* deployment; the first time, `python -m harness.apply` builds one.
launch:
	PYTHONPATH=.:packages:../OspreyFlow_Build $(PY) -m scripts.launch

# Brings a running deployment up to date with this checkout: theme, image builds, up, Keycloak restart
# when its theme changed, sign-in accounts registered again. The launcher's Start runs the same thing.
refresh:
	PYTHONPATH=.:packages:../OspreyFlow_Build $(PY) -m scripts.refresh

# Loads the PaySim dataset into a named case the demo accounts can open, inside the deployment's own
# network (06_DECISIONS.md ADR-055 Amendment 2). Stops the Conduit for the run and starts it again.
seed-paysim:
	PYTHONPATH=.:packages:../OspreyFlow_Build $(PY) -m scripts.seed_internal paysim --stop-api

# Adds the launcher's sign-in (client and demo admin) to a Keycloak that is already running; a
# realm import only happens at first start (06_DECISIONS.md ADR-051). Safe to run again.
register-sign-in:
	PYTHONPATH=.:packages:../OspreyFlow_Build $(PY) -m harness.register_sign_in

dev-up:
	docker compose -f deploy/compose/dev.yaml up -d --wait

dev-down:
	docker compose -f deploy/compose/dev.yaml down -v

# The owner's own ruling, 25 September 2026: removes every OspreyFlow-owned container (any name
# containing "osprey-" — every `docker compose up` this repository's own renderer produces names
# its project `osprey-<profile>`, so this catches a rendered deployment and every exit test's own
# clone of one alike), every OspreyFlow-owned image (`osprey/*:local`, the three owned images'
# local build tags), every named volume containing "osprey", plus dangling images and the build
# cache. **Never the airbyte container or its volumes.** Neither is named or tagged `osprey*`, so
# the name/tag filters above leave them alone unasked; the final `docker volume prune -f` is the
# one step here that is not name-scoped (an exit-test deployment's own *anonymous* volumes — an
# ArcadeDB data volume among them, found here at 2.6GB — carry a random ID, not "osprey", so no
# name filter catches them), and it is still safe for the same reason `docker volume prune`
# always is: it only removes a volume attached to **no** container, so an airbyte volume mounted
# into airbyte's own always-running container is never a candidate regardless of its name.
# Repeatable: run whenever a stale exit-test deployment or dev-up stack has left this host's
# Docker Desktop VM disk short, the condition this session's own exit tests hit twice (`CLAUDE.md`
# rule 14's own worked example, and the disk-exhaustion finding recorded in `07_BUILD_PLAN.md`'s
# Stage 2 §5b entry).
docker-clean:
	@echo "docker-clean: before —"
	@docker system df
	-docker ps -aq --filter "name=osprey-" | xargs -r docker rm -f
	-docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^osprey/.*:local$$' | xargs -r docker rmi -f
	-docker volume ls -q --filter "name=osprey" | xargs -r docker volume rm
	docker image prune -f
	docker builder prune -f
	docker volume prune -f
	@echo "docker-clean: after —"
	@docker system df

# Everything `make test` skips because it needs a live store, run
# together against whatever `make dev-up` brought up. `npm run
# test:integration` (apps/workspace) is here too, not in `make test` — its
# `deltaClient.integration.test.ts` needs the same dev-up stack.
# Volumes are dropped before this target runs, from 24 September 2026 (owner's decision;
# 07_BUILD_PLAN.md Stage 2a). Measured the same day: the identical batch against an accumulated
# ArcadeDB produced 94 failed / 49 passed in 24:51, and against fresh volumes 7 failed / 136 passed
# in 6:38. Every Floor B figure taken before this change was measured against accumulated state.
# **`-v` became `rm -fsv arcadedb` on 27 September 2026 (round 13bb), and the reset it exists for
# is unchanged — proved, not assumed.** `down -v` removes *every* volume this compose project
# owns. Checked directly: the only two **named** volumes in `dev.yaml` are `ollama-models` and
# `speaches-models` — the model caches — and ArcadeDB declares none at all, so its databases live
# in **anonymous** volumes the image itself declares (`/home/arcadedb/databases`, `config`, `log`).
# `-v` therefore reset ArcadeDB (correct, and what the measurement above is about) and, as a pure
# side effect, deleted ~1.5GB of pinned models that `ollama`'s own entrypoint then had to re-pull
# before it could report healthy. On 27 September that re-pull outran its healthcheck budget and
# `up --wait` aborted the whole target — "dependency failed to start: container compose-ollama-1
# is unhealthy" — before a single test ran. A test target that downloads 1.5GB over the network
# to start is not one that produces a trustworthy figure in one pass.
#
# `rm -fsv arcadedb` stops and removes that one container *with its anonymous volumes*, which is
# exactly the reset, and `down` then clears the rest while leaving named volumes alone. Measured
# both halves: a probe database created beforehand is gone afterwards (`list databases` → `[]`),
# and both model volumes survive.
# **The ArcadeDB reset is `rm -fsv arcadedb`, not `down -v`, from 27 September 2026 (round 13bb)
# — and the reset it exists for is unchanged, proved rather than assumed.** `down -v` removes
# *every* volume this compose project owns. Checked directly: the only two **named** volumes in
# `dev.yaml` are `ollama-models` and `speaches-models` — the model caches — and ArcadeDB declares
# none at all, so its databases live in **anonymous** volumes the image itself declares
# (`/home/arcadedb/databases`, `config`, `log`). `-v` therefore reset ArcadeDB (correct, and what
# the measurement above is about) and, as a pure side effect, deleted ~1.5GB of pinned models that
# `ollama`'s own entrypoint then had to re-pull before it could report healthy. On 27 September
# that re-pull outran its healthcheck budget and `up --wait` aborted the whole target — "dependency
# failed to start: container compose-ollama-1 is unhealthy" — before a single test ran. A test
# target that downloads 1.5GB over the network to start is not one that produces a trustworthy
# figure in one pass.
#
# `rm -fsv arcadedb` stops and removes that one container *with its anonymous volumes*, which is
# exactly the reset, and `down` then clears the rest while leaving named volumes alone. Measured
# both halves: a probe database created beforehand is gone afterwards (`list databases` -> `[]`),
# and both model volumes survive.
# **The five token-exchange tests, against a real Keycloak — round 13cc.**
#
# Owner ruling R8: "the token-exchange tests that have never run are also to be made to run."
# `../OspreyFlow_Build/tests/services/api/test_revoked_principal_precheck.py` guards `PrincipalResolver`'s OAuth2
# Token Exchange and the revoked-principal precheck, and had **never executed in any tier**,
# because nothing set `OSPREY_TEST_KEYCLOAK_URL` and the realm lived in a `/tmp` script that was
# never in the tree. That is the code path `CLAUDE.md` rule 15's second worked example records as
# having shipped broken against a real IdP.
#
# **The realm is this repository's own** (`harness/realm.py` + `harness/keycloak_admin.py`, the
# same two modules `harness.apply` uses), not one built to suit the test — a fixture IdP would
# reintroduce exactly the "more permissive than the real dependency" defect ADR-043 shipped with.
#
# Port 8082, so this never collides with a rendered deployment's own Keycloak on 8081.
idp-test:
	@rm -rf .idp-test && mkdir -p .idp-test
	PYTHONPATH=.:packages:../OspreyFlow_Build $(PY) -m tools.idp_test_realm --write-realm .idp-test/realm.json
	-docker rm -f osprey-idp-test >/dev/null 2>&1
	docker run -d --name osprey-idp-test -p 8082:8080 \
	  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
	  -e KC_HEALTH_ENABLED=true \
	  -v "$$PWD/.idp-test/realm.json:/opt/keycloak/data/import/realm.json:ro" \
	  quay.io/keycloak/keycloak:26.0 start-dev --import-realm --features=token-exchange
	PYTHONPATH=.:packages:../OspreyFlow_Build $(PY) -m tools.idp_test_realm --configure --issuer http://localhost:8082
	OSPREY_TEST_KEYCLOAK_URL=http://localhost:8082 \
	  $(PYTEST) -v ../OspreyFlow_Build/tests/services/api/test_revoked_principal_precheck.py; \
	  status=$$?; docker rm -f osprey-idp-test >/dev/null 2>&1; rm -rf .idp-test; exit $$status

# **`idp-test` first, round 13cc.** Floor B used to report "5 skipped" forever: the five
# token-exchange tests were in the list below but `OSPREY_TEST_KEYCLOAK_URL` was never set, so
# they skipped in the only tier that collected them. They now run for real, against a Keycloak
# carrying this repository's own realm, and are no longer listed below — listing them here as
# well would only re-skip them and put the "5 skipped" back.
test-all: idp-test
	docker compose -f deploy/compose/dev.yaml rm -fsv arcadedb
	docker compose -f deploy/compose/dev.yaml down
	docker compose -f deploy/compose/dev.yaml up -d --wait
	$(PYTEST) ../OspreyFlow_Build/tests/conformance/graph_port ../OspreyFlow_Build/tests/conformance/model_port ../OspreyFlow_Build/tests/golden ../OspreyFlow_Build/tests/scenarios/test_witness_statement_extraction.py ../OspreyFlow_Build/tests/ingest ../OspreyFlow_Build/tests/scenarios/test_phase3_working_set.py ../OspreyFlow_Build/tests/scenarios/test_hmp_graph.py ../OspreyFlow_Build/tests/services/api/test_valkey_store.py ../OspreyFlow_Build/tests/services/api/test_statelessness.py ../OspreyFlow_Build/tests/services/api/test_sites_store.py ../OspreyFlow_Build/tests/services/api/test_tile_cache.py ../OspreyFlow_Build/tests/services/api/test_prefetch.py ../OspreyFlow_Build/tests/geocoder/test_match_live.py ../OspreyFlow_Build/tests/services/api/test_assessments.py ../OspreyFlow_Build/tests/services/api/test_suppression.py ../OspreyFlow_Build/tests/services/api/test_assessment_routes.py ../OspreyFlow_Build/tests/services/api/test_export.py ../OspreyFlow_Build/tests/services/api/test_export_routes.py ../OspreyFlow_Build/tests/services/api/test_change_stream.py ../OspreyFlow_Build/tests/services/api/test_alerts.py ../OspreyFlow_Build/tests/services/api/test_pattern_store.py ../OspreyFlow_Build/tests/services/api/test_hotlists.py ../OspreyFlow_Build/tests/services/api/test_monitors.py ../OspreyFlow_Build/tests/services/api/test_evaluation.py ../OspreyFlow_Build/tests/resolve/test_projection_access_control.py ../OspreyFlow_Build/tests/resolve/test_trigger.py ../OspreyFlow_Build/tests/scenarios/test_phase6a_glass_surfaces.py ../OspreyFlow_Build/tests/services/api/test_access.py ../OspreyFlow_Build/tests/services/api/test_dossier_access_control.py ../OspreyFlow_Build/tests/services/api/test_review.py ../OspreyFlow_Build/tests/services/api/test_review_store.py ../OspreyFlow_Build/tests/services/api/test_studio_recipes_store.py ../OspreyFlow_Build/tests/services/api/working_set/test_compute_access_control.py ../OspreyFlow_Build/tests/services/api/working_set/test_explain_cluster_access_control.py ../OspreyFlow_Build/tests/services/api/working_set/test_manual_resolution_access_control.py ../OspreyFlow_Build/tests/services/api/working_set/test_resolution_threshold_access_control.py ../OspreyFlow_Build/tests/scenarios/test_phase7_stage6c_watch_routes.py ../OspreyFlow_Build/tests/scenarios/test_fixture_corp_shape.py ../OspreyFlow_Build/tests/services/api/test_worker.py ../OspreyFlow_Build/tests/services/api/test_worker_replicas.py
	npm run test:integration --workspace apps/workspace

# `spec/02_GLASS_FRONTEND.md` §5's performance budget, as a CI gate
# (`apps/workspace/perf/perf.spec.ts`'s own docstring: a software-WebGL
# regression proxy, not the literal hardware numbers). Needs a Chromium
# binary: `npx playwright install chromium --with-deps` once per machine.
glass-perf:
	npm run test:perf --workspace apps/workspace

# `spec/02_GLASS_FRONTEND.md` §6's contrast floor, as a CI gate, both
# themes (`apps/workspace/a11y/a11y.spec.ts`).
glass-a11y:
	npm run test:a11y --workspace apps/workspace

# `process/07_BUILD_PLAN.md` Phase 4's "keyboard navigation reaches every
# canvas action" exit clause, as a CI gate, not an assertion in prose
# (`apps/workspace/keyboard/keyboard.spec.ts`) — a scripted walkthrough
# that never calls `page.mouse`/`.click()`.
glass-keyboard:
	npm run test:keyboard --workspace apps/workspace

# `spec/00_ARCHITECTURE.md` §1.2.1's Verify contrast-floor check — a
# rendered-pixel/reference-image comparison of a fixture graph over the
# basemap's own chrome colours (`apps/workspace/map-verify/contrast.spec.ts`),
# genuinely different from `glass-a11y`'s axe-core DOM-rule check. Dark
# theme only for now — see `map-verify/showcase.tsx`'s own docstring.
glass-map-verify:
	npm run test:map-verify --workspace apps/workspace

# **The live tier — the Glass against a stack somebody brought up by hand**
# (`DEMO_GUIDE.md` §3), never against a showcase page or a mocked API.
# Deliberately NOT in `ci:` and never will be: it needs real containers, real
# seeded fixtures and a real basemap build, which is the same reasoning
# `../OspreyFlow_Build/tests/harness/test_six_screen_live_exit.py` and `test_sustained_load.py`
# already use for their own opt-in gates. Skips itself with a named reason
# unless `OSPREY_TEST_LIVE_GLASS=1`, so running it with no stack up is a skip,
# not a failure. `apps/workspace/live/playwright.config.ts` has the full
# account of why the other four Playwright projects here cannot cover this.
glass-live:
	npm run test:live --workspace apps/workspace

# **Owner ruling R5's own closing-pass proof** — both acceptance scenarios against a rendered
# `local-lite` deployment, through the analyst's own door: real Keycloak sign-in (authorization
# code with PKCE, as the `--demo-analyst` subject), every call through the workspace's nginx, no
# store port and no in-process app. Deliberately NOT in `ci:`, for the same reason `glass-live`
# and the other exit tests are not — it needs a real, applied deployment — and it has its own
# `ci.yml` job (`over-the-wire-exit-test`) that applies one.
#
# `OSPREY_LIVE_INVESTIGATION_ID` is required and is the id `harness.apply` prints; opted in and
# missing, the test **fails** rather than skipping, which is the point. Run it against a freshly
# seeded deployment — the test's own docstring says which two rows make assertions that cannot be
# taken back, and why that is correct behaviour rather than a defect in them.
exit-over-the-wire:
	OSPREY_TEST_OVER_THE_WIRE=1 $(PYTEST) -p no:randomly \
	  ../OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py

# `06_DECISIONS.md` ADR-049 Stage 2 §6 amendment 21's own keyboard-driven surface
# (`apps/harness/keyboard/setup-screens.spec.ts`) — the setup screens' own "Save" actions,
# reached by keyboard only, against a real `harness.webapp` server this spec's own
# `playwright.config.ts` starts. Not chained into `ci:` above, the same disclosed
# `make ci`/`ci.yml` divergence `glass-perf`/`glass-a11y`/`glass-keyboard` already have
# (07_BUILD_PLAN.md Stage 6) — it has its own `ci.yml` job instead.
harness-keyboard:
	npm run test:keyboard --workspace apps/harness

# `spec/02_GLASS_FRONTEND.md` §6 / amendment 24, ruling 6 — Stage 2 §6 part C
# (`apps/harness/a11y/a11y.spec.ts`). Against the real `App` from `apps/harness/src` served by a
# real `harness.webapp`, never a showcase page — `glass-a11y`'s own Stage 6 finding named exactly
# that gap for the Glass, and this file's own docstring has the reason it is not reproduced here.
# **In `ci:`'s own target list, unlike `glass-a11y`/`glass-keyboard`/`harness-keyboard`** — that
# divergence between `make ci` and `ci.yml` is `07_BUILD_PLAN.md` Stage 6's own disclosed gap, not
# repeated for a third surface (Stage 2 §6 part C's own brief). `ci.yml`'s own job runs this as a
# second step of `harness-keyboard-a11y`, not a separate job — it drives the same real `App`
# against the same real `harness.webapp` that job's own `harness-keyboard` step already starts.
harness-a11y:
	npm run test:a11y --workspace apps/harness

# **`make ci-status` — round 13cg, after finding `ci.yml` has never once completed a run on this
# repository** (`../OspreyFlow_Build/tools/ci_status_check.py`'s own docstring has the investigation; round 13ce's
# "silent since 22 September" undersold it — `gh api repos/{owner}/{repo}/actions/runs` reports
# `total_count: 0`, always, against hundreds of pushes to `main`). Not in `ci:`'s own list: it
# needs network access and a token with Actions-read scope, and checking "is CI green" from inside
# the very CI run that just started cannot answer anything. `release.yml`'s own `ci-status-gate`
# job runs this against the tagged commit with `GITHUB_TOKEN`, which every job in that workflow
# already gets; this target is the same check for a developer or the checker to run by hand,
# against `GH_TOKEN`/`GITHUB_TOKEN` or a `gh`-authenticated token, most usefully right after a push
# — which is exactly the moment `07_BUILD_PLAN.md` this round's own finding says nobody was
# checking.
ci-status:
	PYTHONPATH=.:packages:../OspreyFlow_Build $(PY) -m tools.ci_status_check
