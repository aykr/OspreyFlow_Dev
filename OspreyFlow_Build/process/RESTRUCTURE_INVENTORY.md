# Restructure inventory (ADR-054, step 1)

Every place that names a path the move changes, found by search on 29 September 2026 against commit
`e40b89b`. No file was changed to produce it. It is the work list for steps 2 to 6.

Baseline for proving nothing else changed: 1,561 tests collected, 34 files that cannot be collected in
the sandbox (Python 3.14), and on the fast subset (`harness`, `demo_registry`, `packaging`,
`licence_check`, `authorized_query_check`, `ontology`, `schemas`, top-level `test_*.py`) 822 passed,
7 failed for sandbox reasons, 36 skipped. The full suite and Docker-backed tests are run on the owner's machine.

Citations of `spec/`, `process/` and `CLAUDE.md` in prose and docstrings (131 files cite `process/` or `CLAUDE.md`) stay as they are: they become logical names that the checks map to the new location. They are counted, not listed, below the first 400.

### Code and build files that name `spec/` (logical citation or real path) (18)

- `.github/workflows/ci.yml`
- `.gitignore`
- `Makefile`
- `apps/workspace/Dockerfile`
- `apps/workspace/src/color/tokens.test.ts`
- `config/real_data_exceptions.example.yaml`
- `harness/apply.py`
- `packages/adapters/graph_arcadedb/builders.py`
- `packages/ontology/default.yaml`
- `packages/ontology/handling/uk-le.yaml`
- `packages/ontology/handling/us-criminal-intelligence.yaml`
- `scripts/decision_log_publication_check.py`
- `scripts/doc_citations_check.py`
- `scripts/domain_model_coverage_check.py`
- `scripts/licence_check.mjs`
- `scripts/licence_check.py`
- `scripts/publish_seed.py`
- `scripts/route_coverage_check.py`

### Code and build files that name `tests/` (14)

- `.github/workflows/ci.yml`
- `Makefile`
- `scripts/build_local_basemap.py`
- `scripts/decision_log_publication_check.py`
- `scripts/demo_registry.py`
- `scripts/doc_citations_check.py`
- `scripts/domain_model_coverage_check.py`
- `scripts/packaging_gate.py`
- `scripts/product_tree_link_check.py`
- `scripts/provenance_annotation_check.py`
- `scripts/route_coverage_check.py`
- `scripts/seed_ingest_folder.py`
- `scripts/test_file_coverage_check.py`
- `scripts/update_golden_baseline.py`

### Code and build files that name `process/` (11)

- `.github/workflows/ci.yml`
- `.gitignore`
- `deploy/compose/dev.yaml`
- `eslint.config.js`
- `scripts/ci_status_check.py`
- `scripts/doc_citations_check.py`
- `scripts/doc_site.py`
- `scripts/product_tree_link_check.py`
- `services/api/Dockerfile`
- `services/api/app.py`
- `services/ingest/Dockerfile`

### Code that finds the repository root from its own location (outside tests) (34)

- `apps/workspace/test/glass_test_server.py`
- `harness/backup.py`
- `harness/preflight/context.py`
- `harness/render.py`
- `harness/service_inventory.py`
- `harness/webapp.py`
- `packages/adapters/compute_graphology_tier1/adapter.py`
- `packages/ontology/handling.py`
- `packages/ontology/loader.py`
- `packages/ontology/yardstick.py`
- `packages/schemas/generate_ts.py`
- `scripts/authorized_query_check.py`
- `scripts/build_local_basemap.py`
- `scripts/ci_status_check.py`
- `scripts/decision_log_publication_check.py`
- `scripts/demo_guide_check.py`
- `scripts/demo_registry.py`
- `scripts/doc_citations_check.py`
- `scripts/doc_site.py`
- `scripts/domain_model_coverage_check.py`
- `scripts/launch.py`
- `scripts/licence_check.py`
- `scripts/osprey_bundle.py`
- `scripts/packaging_gate.py`
- `scripts/product_tree_link_check.py`
- `scripts/provenance_annotation_check.py`
- `scripts/publish_seed.py`
- `scripts/real_data_exceptions.py`
- `scripts/route_coverage_check.py`
- `scripts/schemas_check.py`
- `scripts/test_file_coverage_check.py`
- `scripts/update_golden_baseline.py`
- `services/api/app.py`
- `services/api/studio_publish.py`

### Tests that find the repository root from their own location (45)

- `tests/authorized_query_check/test_principal_predicate_required.py`
- `tests/harness/test_bundle_exit_test.py`
- `tests/harness/test_deployment_schema.py`
- `tests/harness/test_dev_compose_arcadedb_heap.py`
- `tests/harness/test_geospatial_packaging_boundary.py`
- `tests/harness/test_harness_image.py`
- `tests/harness/test_keycloak_theme.py`
- `tests/harness/test_render.py`
- `tests/harness/test_six_screen_live_exit.py`
- `tests/harness/test_sustained_load.py`
- `tests/harness/test_workspace_bundle.py`
- `tests/ingest/test_crs_reprojection.py`
- `tests/ingest/test_osm_gazetteer_recipe_end_to_end.py`
- `tests/ingest/test_recipe_engine_end_to_end.py`
- `tests/ingest/test_remaining_gazetteers.py`
- `tests/ingest/test_site_grid_recipe_end_to_end.py`
- `tests/ingest/test_verify_dry_run.py`
- `tests/licence_check/test_gpl_rejection.py`
- `tests/licence_check/test_own_licence_and_notice.py`
- `tests/scenarios/fixtures/test_scenario_cohorts.py`
- `tests/scenarios/test_phase8_exit_over_the_wire.py`
- `tests/schemas/test_drift_gate.py`
- `tests/services/api/test_mapconfig_loader.py`
- `tests/services/api/test_statelessness.py`
- `tests/services/api/test_tier4_registration.py`
- `tests/test_connector_profile_settings_reach_the_recipe.py`
- `tests/test_connectors_are_carried_into_the_image.py`
- `tests/test_demo_guide_registry_check.py`
- `tests/test_demo_osprey_config_is_tier_1_only.py`
- `tests/test_doc_site.py`
- `tests/test_dockerignore.py`
- `tests/test_domain_model_coverage_check.py`
- `tests/test_image_imports_are_carried.py`
- `tests/test_launch.py`
- `tests/test_launch_sign_in.py`
- `tests/test_osprey_bundle.py`
- `tests/test_product_tree_link_check.py`
- `tests/test_provenance_annotation_check.py`
- `tests/test_publish_seed.py`
- `tests/test_real_data_exceptions.py`
- `tests/test_route_coverage_check.py`
- `tests/test_seed_ingest_folder.py`
- `tests/test_shipped_provider_profiles.py`
- `tests/test_simple_markdown.py`
- `tests/test_test_file_coverage_check.py`

### Non-test Python that imports from `tests` (7)

- `process/prototypes/ingest-map/generate_data.py`
- `scripts/mint_dev_token.py`
- `scripts/seed_fixture_corp.py`
- `scripts/seed_hmp_fixture.py`
- `scripts/seed_ingest_folder.py`
- `scripts/seed_scenarios.py`
- `scripts/update_golden_baseline.py`

### Docs and other files that cite `process/` or `CLAUDE.md` (kept as logical names) (131)

- `.claude/commands/phase.md`
- `.dockerignore`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `.gitignore`
- `CLAUDE.md`
- `Makefile`
- `README.md`
- `apps/harness/keyboard/playwright.config.ts`
- `apps/harness/src/api/types.ts`
- `apps/harness/src/app.css`
- `apps/harness/src/screens/GovernanceScreen.tsx`
- `apps/workspace/Dockerfile`
- `apps/workspace/keyboard/actionRegistry.ts`
- `apps/workspace/keyboard/keyboard.spec.ts`
- `apps/workspace/live/basemap.spec.ts`
- `apps/workspace/live/ingest-folder.spec.ts`
- `apps/workspace/live/live.ts`
- `apps/workspace/live/scenario-a-a12-a15.spec.ts`
- `apps/workspace/src/auth/oidcConfig.ts`
- `apps/workspace/src/canvas/GlassCanvas.tsx`
- `apps/workspace/src/canvas/edgeTypeMenu.test.ts`
- `apps/workspace/src/design/primitives.css`
- `apps/workspace/src/export/pngMark.ts`
- `apps/workspace/src/map/pmtilesAuth.test.ts`
- `apps/workspace/vite.config.ts`
- `deploy/compose/dev.yaml`
- `eslint.config.js`
- `harness/__init__.py`
- `harness/__main__.py`
- `harness/compare.py`
- `harness/geospatial.py`
- `harness/preflight/oidc_audience.py`
- `harness/render.py`
- `harness/restore.py`
- `harness/verify.py`
- `harness/webapp.py`
- `harness/webapp_auth.py`
- `packages/adapters/graph_arcadedb/testing.py`
- `packages/schemas/analytics.py`
- `packages/schemas/deployment.py`
- `packages/schemas/generate_ts.py`
- `packages/schemas/generated/GovernanceConfig.ts`
- `packages/schemas/generated/OspreyConfig.ts`
- `providers/os-open-zoomstack.yaml`
- `providers/usgs-national-map.yaml`
- `scripts/build_local_basemap.py`
- `scripts/ci_status_check.py`
- `scripts/doc_citations_check.py`
- `scripts/doc_site.py`
- `scripts/domain_model_coverage_check.py`
- `scripts/idp_test_realm.py`
- `scripts/launch.py`
- `scripts/licence_check.py`
- `scripts/osprey_bundle.py`
- `scripts/product_tree_link_check.py`
- `scripts/publish_seed.py`
- `scripts/real_data_exceptions.py`
- `scripts/register_tier4_provider.py`
- `scripts/route_coverage_check.py`
- `scripts/seed_fixture_corp.py`
- `scripts/seed_hmp_fixture.py`
- `scripts/seed_ingest_folder.py`
- `scripts/seed_scenarios.py`
- `scripts/simple_markdown.py`
- `scripts/test_file_coverage_check.py`
- `scripts/verify_map.py`
- `services/api/Dockerfile`
- `services/api/alerts.py`
- `services/api/app.py`
- `services/api/assessments.py`
- `services/api/ingest_sources.py`
- `services/api/suppression.py`
- `services/ingest/Dockerfile`
- `services/resolve/conflicts.py`
- `spec/06_DECISIONS.md`
- `tests/conformance/graph_port/test_suite.py`
- `tests/fixtures/mapconfig/tier2_swap_demo.osprey.yaml`
- `tests/fixtures/product_tree_link_allowlist.txt`
- `tests/harness/fake_idp.py`
- `tests/harness/test_apply_env.py`
- `tests/harness/test_bundle_exit_test.py`
- `tests/harness/test_dev_compose_arcadedb_heap.py`
- `tests/harness/test_geospatial_packaging_boundary.py`
- `tests/harness/test_harness_image.py`
- `tests/harness/test_image_references.py`
- `tests/harness/test_preflight.py`
- `tests/harness/test_realm.py`
- `tests/harness/test_render.py`
- `tests/harness/test_restore_exit_test.py`
- `tests/harness/test_six_screen_live_exit.py`
- `tests/harness/test_webapp_admin_access.py`
- `tests/harness/test_webapp_governance_panel.py`
- `tests/harness/test_webapp_screens.py`
- `tests/harness/test_workspace_bundle.py`
- `tests/licence_check/test_own_licence_and_notice.py`
- `tests/packaging/test_internal_demo_exclusion.py`
- `tests/scenarios/fixtures/boundary_line_recipe.yaml`
- `tests/scenarios/fixtures/code_point_open_recipe.yaml`
- `tests/scenarios/fixtures/fixture_corp.py`
- `tests/scenarios/fixtures/fixture_corp_resolution.py`
- `tests/scenarios/fixtures/nad_recipe.yaml`
- `tests/scenarios/fixtures/open_uprn_recipe.yaml`
- `tests/scenarios/fixtures/os_open_names_recipe.yaml`
- `tests/scenarios/fixtures/test_scenario_cohorts.py`
- `tests/scenarios/fixtures/tiger_line_recipe.yaml`
- `tests/scenarios/fixtures/usgs_gnis_recipe.yaml`
- `tests/scenarios/test_fixture_corp_shape.py`
- `tests/scenarios/test_phase8_exit_over_the_wire.py`
- `tests/services/api/test_assessments.py`
- `tests/services/api/test_geospatial_admin_routes.py`
- `tests/services/api/test_ingest_sources.py`
- `tests/services/api/test_liveness_route.py`
- `tests/services/api/test_revoked_principal_precheck.py`
- `tests/services/api/test_suppression.py`
- `tests/services/api/test_worker_replicas.py`
- `tests/services/api/test_ws_ticket_route.py`
- `tests/test_build_local_basemap.py`
- `tests/test_connector_profile_settings_reach_the_recipe.py`
- `tests/test_decision_log_publication_check.py`
- `tests/test_doc_citations_check.py`
- `tests/test_doc_site.py`
- `tests/test_dockerignore.py`
- `tests/test_image_imports_are_carried.py`
- `tests/test_launch.py`
- `tests/test_osprey_bundle.py`
- `tests/test_product_tree_link_check.py`
- `tests/test_publish_seed.py`
- `tests/test_real_data_exceptions.py`
- `tests/test_seed_scenarios.py`
- `tests/test_test_file_coverage_check.py`
