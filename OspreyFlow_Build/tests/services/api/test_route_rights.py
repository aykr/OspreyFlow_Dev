"""Every route names the right it needs (`06_DECISIONS.md` ADR-112), and every right is refused both
ways: the right without the case level, and the case level without the right.

`ROUTE_RIGHTS` below is the table, written here as the test's own data: a route added without a right,
or with a right other than this table's, fails `test_every_route_names_the_right_the_table_gives_it`
(the same shape as `test_investigation_levels.py`'s table). `None` is a decision, not an omission:
any signed-in person, the case level still applying — reference catalogues, the case list, health.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.investigations import AccessLevel, InvestigationStore

from schemas.domain import Principal
from schemas.rights import Right
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import give_case_its_dataset

# endpoint name -> right value (None = any signed-in person; the case level still applies)
ROUTE_RIGHTS = {
    "create_investigation": "create_case",
    "list_datasets_route": None,
    "create_dataset_route": "create_case",
    "create_composite_route": "create_case",
    # ADR-143 Amendment 2 decision 5: a drawn dataset, made with its case.
    "make_drawn_dataset": "create_case",
    # A dataset's domain model (ADR-112 Amendment 6, L3.1b), behind the dataset's own gate.
    "read_dataset_model": "edit_target_model",
    "open_dataset_model_draft": "edit_target_model",
    "save_dataset_model_draft": "edit_target_model",
    "discard_dataset_model_draft": "edit_target_model",
    "dataset_model_impact": "edit_target_model",
    "make_dataset_model_live": "edit_target_model",
    "revert_dataset_model": "edit_target_model",
    "case_datasets_route": None,
    "set_case_datasets_route": "share_case",
    "list_investigations": None,
    "set_tab_state": None,
    "rename_investigation": "share_case",
    "remove_investigation": "remove_case",
    "get_investigation_access": "share_case",
    "set_investigation_unit_level": "share_case",
    "set_investigation_grant": "share_case",
    "remove_investigation_grant": "share_case",
    "get_investigation_access_history": "share_case",
    "get_investigation": None,
    # ADR-144: case views, behind the case's level; saving, sharing and deleting work the case.
    "list_case_views": None,
    "save_case_view": "investigate",
    "open_case_view": None,
    "share_case_view": "investigate",
    "delete_case_view": "investigate",
    # ADR-143 decisions 4 to 7 (L3.3): boards, behind the case's level; reading needs investigate,
    # drawing needs draw_on_boards at Editor. A drawing with no case also needs create_case, which
    # it names first.
    "list_boards": "investigate",
    "make_board": "draw_on_boards",
    "open_board": "investigate",
    "share_board": "draw_on_boards",
    "delete_board": "draw_on_boards",
    "declare_drawn_item": "draw_on_boards",
    "draw_link": "draw_on_boards",
    "move_board_items": "draw_on_boards",
    "edit_drawn_item": "draw_on_boards",
    "withdraw_drawn_item": "draw_on_boards",
    "board_match_suggestions": "investigate",
    "decide_board_match": "draw_on_boards",
    "upload_drawn_picture": "draw_on_boards",
    "choose_drawn_picture": "draw_on_boards",
    "board_pictures": "investigate",
    "board_picture_file": "investigate",
    "list_drawn_watches": "investigate",
    "start_a_drawing": "create_case",
    "seed": "investigate",
    "expand": "investigate",
    "links_among_route": "investigate",
    "add_by_identifiers_route": "investigate",
    "expand_preview": "investigate",
    "remove_nodes": "investigate",
    "get_resolution_threshold_route": "investigate",
    "set_resolution_threshold_route": "investigate",
    "link_resolution_route": "resolve_entities",
    "split_resolution_route": "resolve_entities",
    "explain_resolution_route": "investigate",
    "compute_metric_route": "run_analysis",
    "run_extraction_route": "extract_files",
    "list_extraction_candidates_route": "extract_files",
    "accept_extraction_candidate_route": "extract_files",
    "reject_extraction_candidate_route": "extract_files",
    "get_dossier_document_route": "investigate",
    "confirm_node_route": "confirm_inferred",
    "mark_node_for_suppression": "edit_graph",
    "unmark_node_for_suppression": "edit_graph",
    "retract_node_route": "confirm_inferred",
    "get_investigation_history": "investigate",
    "restore_history_step": "investigate",
    "search_route": "investigate",
    "suggest_route": "investigate",
    "explore_counts_route": "investigate",
    "explore_most_connected_route": "investigate",
    "explore_busiest_links_route": "investigate",
    "explore_busiest_days_route": "investigate",
    "explore_groups_route": "investigate",
    "explore_whats_new_route": "investigate",
    "explore_starter_questions_route": "investigate",
    "explore_starter_run_route": "investigate",
    "shared_contacts_route": "investigate",
    "shared_pair_canvas_route": "investigate",
    "patterns_preview_route": "investigate",
    "ask_to_search_route": "ask_model",  # ADR-129 decision 2
    "patterns_run_route": "investigate",
    "patterns_save_route": "investigate",
    "patterns_list_route": "investigate",
    "patterns_load_route": "investigate",
    "create_hotlist_route": "keep_watches",
    "list_hotlists_route": "keep_watches",
    "set_hotlist_audience_route": "keep_watches",  # ADR-133 ruling 3
    "save_judgement_route": "record_assessment",
    "list_judgements_route": "investigate",
    "change_link_route": "edit_graph",
    "case_link_types_route": "investigate",
    # ADR-143 decision 9 (L3.5): the Analyst's `propose_types`, never with `accept_types`.
    "propose_link_type_route": "propose_types",
    "withdraw_link_type_route": "propose_types",
    "promotable_link_types_route": "investigate",
    # The Studio's Model tab decides them, behind the dataset's gate (ADR-090 Amendment 4).
    "list_model_proposals": "accept_types",
    "accept_model_proposal": "accept_types",
    "decline_model_proposal": "accept_types",
    "list_link_type_proposals_route": "manage_ontology",
    "promote_link_type_route": "manage_ontology",
    "reject_link_type_route": "manage_ontology",
    "retire_link_type_route": "manage_ontology",
    "link_history_route": "investigate",
    "list_link_events_route": "investigate",
    "extract_email_route": "extract_files",
    "read_document_route": "investigate",
    "designate_in_document_route": "extract_files",
    "upload_document_route": "extract_files",
    "document_file_route": "investigate",
    "set_entity_picture_route": "edit_graph",
    "remove_entity_picture_route": "edit_graph",
    "entity_pictures_route": "investigate",
    "entity_picture_file_route": "investigate",
    "extract_document_route": "extract_files",
    "accept_document_candidate_route": "extract_files",
    "accept_document_candidates_route": "extract_files",
    "reject_document_candidate_route": "extract_files",
    "ask_question_route": "ask_model",
    "list_questions_route": "investigate",
    "accept_question_candidate_route": "extract_files",
    "reject_question_candidate_route": "extract_files",
    "show_emails_as_documents_route": "extract_files",
    "accept_email_candidate_route": "extract_files",
    "reject_email_candidate_route": "extract_files",
    "list_link_notes_route": "investigate",
    "add_link_note_route": "edit_graph",
    "edit_link_note_route": "edit_graph",
    "remove_link_note_route": "edit_graph",
    # ADR-128 decision 3: the brief is read by anyone who may read the case, edited by its Author.
    "get_case_brief_route": "investigate",
    "set_brief_priority_route": "share_case",
    "add_brief_requirement_route": "share_case",
    "edit_brief_requirement_route": "share_case",
    "remove_brief_requirement_route": "share_case",
    "set_brief_requirement_status_route": "share_case",
    "attach_to_brief_requirement_route": "share_case",
    "detach_from_brief_requirement_route": "share_case",
    "save_gap_route": "record_assessment",
    "list_gaps_route": "investigate",
    "save_assumption_route": "record_assessment",
    "list_assumptions_route": "investigate",
    "submit_export_route": "export",
    "list_exports_route": "read_export_ledger",
    "create_monitor_route": "keep_watches",
    "list_monitors_route": "keep_watches",
    "list_alerts_route": "keep_watches",
    "get_alert_route": "keep_watches",
    "open_alert_at_address": "read_alert_queue",
    "paths_route": "investigate",
    "connections_route": "investigate",
    "resolve_now_route": "resolve_entities",
    "readiness_route": None,
    "liveness_route": None,
    # The API's OpenAPI document (`03_CONDUIT_MIDDLEWARE.md` §3.0a; GDS remediation O1): behind
    # sign-in as every `/v1` route is, and no right beyond it, as the ontology below.
    "openapi_document_route": None,
    "get_ontology_route": None,
    "get_map_providers_route": None,
    "get_map_tile_route": None,
    "get_map_local_source_route": None,
    # ADR-147 Amendment 1 (P4): the map's place search over the case's gazetteer, as its other searches.
    "map_place_search_route": "investigate",
    "build_basemap_route": "manage_geospatial",
    "verify_map_route": "manage_geospatial",
    "histogram_route": "investigate",
    "case_event_holders_route": "investigate",
    "cross_filter_route": "investigate",
    "first_seen_route": "investigate",
    "geo_bins_route": "investigate",
    "sightings_route": "investigate",
    "geometries_route": "investigate",
    "create_site": "edit_graph",
    "get_site": "investigate",
    "get_site_image": "investigate",
    "set_site_control_points": "edit_graph",
    "set_site_grid": "edit_graph",
    "list_connectors": None,
    "list_domain_packs": None,
    "get_handling_scheme_route": None,
    "get_yardstick_route": None,
    # ADR-143 decision 11: the deployment's grading scheme, as the yardstick.
    "get_grading_scheme_route": None,
    "list_ingest_source_files": "add_ingest_files",
    # ADR-140 Amendment 4: connections and registered sources, on dataset routes.
    "list_ingest_connections": "add_ingest_files",
    "list_admin_connections": "administer_system",
    "add_admin_connection": "administer_system",
    "list_dataset_source_files": "add_ingest_files",
    "list_dataset_sources": "add_ingest_files",
    "register_dataset_source": "add_ingest_files",
    "get_dataset_source": "add_ingest_files",
    "get_dataset_source_profile": "add_ingest_files",
    "get_dataset_source_lineage": "add_ingest_files",
    "edit_dataset_source_governance": "edit_pipelines",
    "pause_source_refresh": "schedule_pipelines",
    "resume_source_refresh": "schedule_pipelines",
    # ADR-140 Amendment 13: the screening-list connector, subscriptions by id, a dataset's lists.
    "read_connector_source": "add_ingest_files",
    "test_admin_connection": "administer_system",
    "list_deployment_lists": "load_screening_lists",
    "add_deployment_list": "load_screening_lists",
    "refresh_deployment_list": "load_screening_lists",
    "list_deployment_list_imports": "load_screening_lists",
    "set_deployment_list_schedule": "load_screening_lists",
    "dataset_list_subscriptions": "add_ingest_files",
    "subscribe_dataset_to_list": "add_ingest_files",
    "unsubscribe_dataset_from_list": "add_ingest_files",
    "offered_reference_lists": "edit_pipelines",
    "import_dataset_own_list": "add_ingest_files",
    "upload_ingest_source_file": "add_ingest_files",
    "create_studio_recipe_draft": "edit_pipelines",
    "update_studio_recipe_draft": "edit_pipelines",
    "update_studio_recipe_pipeline": "edit_pipelines",
    "get_studio_recipe_draft": "edit_pipelines",
    "list_studio_recipe_drafts": "edit_pipelines",
    "get_studio_recipe_profile": "edit_pipelines",
    "list_transforms": None,
    "update_studio_recipe_row_template": "edit_pipelines",
    "get_studio_recipe_sample_row": "edit_pipelines",
    "preview_studio_recipe_staging": "edit_pipelines",
    "preview_studio_recipe_element_handling": "edit_pipelines",
    "verify_studio_recipe": "verify_pipelines",
    "preview_studio_recipe_graph": "verify_pipelines",
    # ADR-133 decision 6, stage (d): the "Checks on load" step, an engineer's (D1).
    "read_load_checks": "edit_pipelines",
    "set_load_checks": "edit_pipelines",
    "list_studio_recipe_registry": "edit_pipelines",
    "publish_studio_recipe": "publish_pipelines",
    "update_studio_recipe_schedule": "schedule_pipelines",
    "create_studio_recipe_version": "edit_pipelines",
    "run_studio_recipe": "run_pipelines",
    "trace_ownership_route": "trace_ownership",
    "ownership_canvas": "trace_ownership",
    "kyc_status_route": "trace_ownership",
    "neighbourhood_risk_route": "trace_ownership",
    "read_case_report": "read_reports",
    "list_embedded_dashboards": "read_reports",
    "embedded_dashboard_guest_token": "read_reports",
    # ADR-113 decision 7: building, saving and reading trends is run_analysis.
    "trend_options_route": "run_analysis",
    "preview_trend": "run_analysis",
    "save_trend": "run_analysis",
    "list_trends": "run_analysis",
    "trend_figures": "run_analysis",
    "delete_trend": "run_analysis",
    # ADR-113 decision 7: assembling, refreshing and publishing a pack is record_assessment; reading
    # what was published is read_reports.
    "create_pack": "record_assessment",
    "list_packs": "record_assessment",
    "read_pack": "record_assessment",
    "add_pack_item": "record_assessment",
    "remove_pack_item": "record_assessment",
    "reorder_pack": "record_assessment",
    "refresh_pack_item": "record_assessment",
    "pack_history": "record_assessment",
    "publish_pack": "record_assessment",
    "withdraw_pack_version": "record_assessment",
    "list_published_packs": "read_reports",
    "read_published_pack": "read_reports",
    "export_pack_route": "export",
    "read_report_feed": "read_report_feed",
    "read_alert_queue": "read_alert_queue",
    "read_alert_queue_counts": "read_alert_queue",
    "explain_alert": "read_alert_queue",
    "claim_alert": "triage_alerts",
    "release_alert": "triage_alerts",
    "dispose_alert": "triage_alerts",
    # ADR-133 decision 7, stage (d): a second member approves (or sends back) a high-severity close.
    "approve_alert_close": "triage_alerts",
    "send_back_alert_close": "triage_alerts",
    "alert_canvas": "triage_alerts",
    "assign_alert": "triage_alerts",  # ADR-133 stage (a)
    "read_alert_assignees": "triage_alerts",
    "list_typology_rules": "read_alert_queue",
    "deploy_typology_rule": "deploy_rules",
    "retire_typology_rule": "deploy_rules",
    # ADR-133 decision 7, stage (d): maker–checker — approving, rejecting and changing a rule need
    # the deployer's right (and, for a whole-deployment rule, the administrator's too, in the
    # route); reading a rule's versions and its schedule is the case team's, as reading rules is.
    "approve_rule_change": "deploy_rules",
    "reject_rule_change": "deploy_rules",
    "change_rule_sentence": "deploy_rules",
    "read_rule_versions": "read_alert_queue",
    "read_rule_schedule": "read_alert_queue",
    "compile_rule_sentence": "investigate",
    "read_rule_sentence": "investigate",
    "preview_rule_sentence": "investigate",
    "deploy_rule_sentence": "deploy_rules",
    # ADR-139: installation-wide influencers by maker–checker; the case's reads and its Author's
    # override are investigation (the case level applying).
    "list_strength_influencers_route": "manage_strength_influencers",
    "propose_strength_influencers_route": "manage_strength_influencers",
    "approve_strength_influencers_route": "manage_strength_influencers",
    "send_back_strength_influencers_route": "manage_strength_influencers",
    "case_strength_influencers_route": "investigate",
    "set_case_strength_influencers_route": "investigate",
    "connection_strength_route": "investigate",
    "rarity_route": "investigate",
    "list_screening_lists": "read_alert_queue",
    "manage_screening_lists": "load_screening_lists",
    "subscribe_screening_list": "load_screening_lists",
    "refresh_screening_list_route": "load_screening_lists",
    # ADR-133 Amendment 3 item 4, stage (d): a list's refresh schedule.
    "set_screening_list_schedule": "load_screening_lists",
    "read_rule_audit": "read_rule_audit",
    "list_held_rows": "read_held_rows",
    "release_held_rows_route": "decide_held_rows",
    "reject_held_rows": "decide_held_rows",
    "issue_ws_ticket": None,
    "my_rights_route": None,
    # ADR-135 decision 5: the engines an analyst may choose; any signed-in person, never a key.
    "model_engines_route": None,
    # ADR-136: the same within a case (its datasets' egress), the case's Viewer level applying.
    "case_model_engines_route": None,
    "list_people_route": "manage_people",
    "set_person_roles_route": "manage_people",
    # ADR-114 Amendment 5 (B4b)
    "invite_person_route": "manage_people",
    "set_person_access_route": "manage_people",
    "disable_person_route": "manage_people",
    "enable_person_route": "manage_people",
    "reset_person_sign_in_route": "manage_people",
    "remove_person_route": "manage_people",
    "list_organisation_arrivals_route": "manage_people",
    "link_organisation_account_route": "manage_people",
    "list_demo_packs_route": "administer_system",
    "list_dashboards_route": "manage_dashboards",
    "register_dashboard_route": "manage_dashboards",
    "remove_dashboard_route": "manage_dashboards",
    "system_status_route": "administer_system",
    # ADR-135 Amendment 2, ADR-112 Amendment 7: Admin › Models.
    "models_admin_view_route": "manage_models",
    "models_admin_history_route": "manage_models",
    "models_admin_add_engine_route": "manage_models",
    "models_admin_edit_engine_route": "manage_models",
    "models_admin_remove_engine_route": "manage_models",
    "models_admin_defaults_route": "manage_models",
    "models_admin_set_key_route": "manage_models",
    "models_admin_remove_key_route": "manage_models",
    "models_admin_test_route": "manage_models",
    # ADR-135 Amendment 3 (P2), missed from this table at P2's merge: added in P3.
    "models_admin_limits_route": "manage_models",
    "models_admin_usage_route": "manage_models",
    # ADR-147 (P3): Admin › Maps.
    "maps_admin_view_route": "manage_geospatial",
    "maps_admin_history_route": "manage_geospatial",
    "maps_admin_add_provider_route": "manage_geospatial",
    "maps_admin_edit_provider_route": "manage_geospatial",
    "maps_admin_remove_provider_route": "manage_geospatial",
    "maps_admin_set_key_route": "manage_geospatial",
    "maps_admin_remove_key_route": "manage_geospatial",
    "maps_admin_default_route": "manage_geospatial",
    "maps_admin_areas_route": "manage_geospatial",
    "maps_admin_schedule_route": "manage_geospatial",
    "maps_admin_prefetch_route": "manage_geospatial",
    # ADR-136 decision 2: every dataset's egress, set by an administrator alone, audited.
    "admin_datasets_route": "administer_system",
    # ADR-145 Amendment 4 decision 7: Admin › System's *Dataset owners may be*.
    "read_dataset_owner_setting": "administer_system",
    "set_dataset_owner_setting": "administer_system",
    "set_dataset_egress_route": "administer_system",
    # ADR-145 decision 8 and Amendment 4 decision 6; ADR-143 Amendment 2 decision 1 (L2.4 part 2,
    # missing from this table at its merge: this module is outside the offline `make test`).
    "admin_dataset_authors_route": "administer_system",
    "admin_dataset_cases_route": "administer_system",
    "change_dataset_owners_route": "administer_system",
    "layer_action_dry_run_route": "administer_system",
    "set_dataset_promotion_policy_route": "administer_system",
    # ADR-145 decisions 6 and 7 and Amendment 5 (L2.5): roles, teams, the People rows, Disable….
    "list_roles_route": "manage_people",
    "create_role_route": "manage_people",
    "change_role_route": "manage_people",
    "role_versions_route": "manage_people",
    "make_team_route": "manage_people",
    "set_team_lead_route": "manage_people",
    "set_team_cover_route": "manage_people",
    "people_rows_route": "manage_people",
    "disable_plan_route": "manage_people",
    "name_an_author_route": "manage_people",
    "list_schedules_route": "operate_schedules",
    "schedule_runs_route": "operate_schedules",
    "pause_schedule_route": "operate_schedules",
    "resume_schedule_route": "operate_schedules",
    "data_feeds_route": "read_data_feeds",
    "run_schedule_now_route": "operate_schedules",
    "change_schedule_route": "operate_schedules",
    "schedule_preview_route": "schedule_pipelines",
    "pause_recipe_schedule": "schedule_pipelines",
    "resume_recipe_schedule": "schedule_pipelines",
    "recipe_runs_route": "run_pipelines",  # ADR-145 Amendment 1: the Studio's alone
}


AUTHOR = Principal(id="rights-author", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    import os

    previous = {
        k: os.environ.get(k) for k in ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    }
    os.environ.update(
        OIDC_JWKS_URL=jwks_url, OIDC_ALGORITHMS="RS256", ARCADEDB_DATABASE="ospreyflow"
    )
    try:
        yield
    finally:
        for key, value in previous.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)


def _routes() -> dict[str, APIRoute]:
    from services.api.app import app

    return {r.endpoint.__name__: r for r in app.routes if isinstance(r, APIRoute)}


def _declared(route: APIRoute) -> str | None:
    for dependency in route.dependant.dependencies:
        right = getattr(dependency.call, "required_right", None)
        if right is not None:
            return str(right)
    return None


def test_every_route_names_the_right_the_table_gives_it() -> None:
    routes = _routes()
    assert set(routes) == set(ROUTE_RIGHTS), (
        f"in the app, not the table: {sorted(set(routes) - set(ROUTE_RIGHTS))}; "
        f"in the table, not the app: {sorted(set(ROUTE_RIGHTS) - set(routes))}"
    )
    wrong = {name: (_declared(r), ROUTE_RIGHTS[name]) for name, r in routes.items()
             if _declared(r) != ROUTE_RIGHTS[name]}  # fmt: skip
    assert wrong == {}, wrong


def test_every_right_guards_at_least_one_route() -> None:
    """A right no route checks is a right stated and exercised by nothing (rule 12) — except the
    two the Conduit has no route for yet: people, dashboards and data feeds arrive with the Admin
    area (ADR-110 Amendment 1, ADR-112); reverting a load has no route (spec 09 §6). Screening
    lists gained theirs with ADR-133 stage (c); the domain model's editor, its routes in L3.1b. A
    promotion's reviewer (`review_promotions`, ADR-112 Amendment 4) is held today only to count a
    dataset's approvers in Admin › Datasets; its review route arrives with the promotion (L3.4).
    `manage_models` (ADR-112 Amendment 7) guards *Admin › Models*' routes (platform's P1).
    `draw_on_boards` guards the boards' routes (L3.3)."""
    not_yet = {"revert_loads", "read_audit",
               "export_override", "review_promotions",
               # ADR-112 Amendments 4 and 5: each arrives with its own step's routes (boards,
               # promotion, proposed types, the drawn-dataset merge, Rules and Monitoring).
               "promote_to_dataset",
               "merge_datasets", "author_rules",
               # Superseded at L3.5 by `propose_types` (ADR-112 Amendment 4); its removal from
               # the rights and the role screens is the orchestrator's (case-b's report).
               "propose_link_type"}  # fmt: skip
    guarded = {r for r in ROUTE_RIGHTS.values() if r}
    assert {r.value for r in Right} - guarded == not_yet


def _token(key: rsa.RSAPrivateKey, sub: str, roles: list[str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(key, default_claims(sub=sub, roles=roles))}"}


def _call(client: TestClient, route: APIRoute, case: str, headers: dict[str, str]) -> int:
    path = route.path.replace("{investigation_id}", case)
    path = re.sub(r"\{[a-z_]+\}", "x", path)
    method = sorted(route.methods)[0]
    return client.request(method, path, headers=headers, json={}).status_code


async def _case(viewer_and_author: str) -> str:
    store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        case = await store.create(AUTHOR, name="Rights case")
        await give_case_its_dataset(case.id, AUTHOR)
        await store.set_grant(case.id, viewer_and_author, AccessLevel.AUTHOR, by=AUTHOR)
        return case.id
    finally:
        await store.close()


def test_each_right_is_refused_without_it_and_needs_the_case_level_too(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """For each right, one route it guards: a person holding every other right, and Author on the
    case, is refused (403) — the right is necessary; a person holding only that right and no level
    on the case is refused too (403 or 404) — the right is not sufficient. A case route only, since
    a system route has no case level to withhold."""
    key, _ = keypair
    case = asyncio.run(_case("rights-member"))
    routes = _routes()
    everything = [f"right:{r.value}" for r in Right]
    checked = set()
    with TestClient(__import__("services.api.app", fromlist=["app"]).app) as client:
        for name, right in sorted(ROUTE_RIGHTS.items()):
            route = routes[name]
            if right is None or right in checked or "{investigation_id}" not in route.path:
                continue
            checked.add(right)
            without = [r for r in everything if r != f"right:{right}"]
            assert _call(client, route, case, _token(key, "rights-member", without)) == 403, (
                name,
                right,
            )
            assert _call(
                client, route, case, _token(key, "rights-outsider", [f"right:{right}"])
            ) in (403, 404), (name, right)
    assert len(checked) >= 25, f"only {len(checked)} rights reached a case route"


def test_a_person_from_the_organisation_with_no_role_reads_nothing_on_any_route(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """ADR-114 Amendment 33 decision 4 and the owner's answer 6 (rules 3 and 4): a person signed in
    through the organisation's identity provider arrives with exactly the claims the realm's
    arrival mappers give (`harness.realm.ORGANISATION_ARRIVAL_ATTRIBUTES`; the real Keycloak's
    token is shown to carry them in `tests/harness/test_organisation_sign_in.py`) — no role, no
    handling code, a clearance and a unit no scheme knows. On every read route of the Conduit, with
    a real case in the store, they are refused (403, or 404 for a case they cannot see), or answered
    with nothing: an empty list, never a count."""
    from harness.realm import ORGANISATION_ARRIVAL_ATTRIBUTES

    key, _ = keypair
    case = asyncio.run(_case("rights-member"))
    claims = default_claims(sub="from-the-organisation", roles=[], receivable_handling_codes=[],
                            **ORGANISATION_ARRIVAL_ATTRIBUTES)  # fmt: skip
    claims.pop("roles")
    headers = {"Authorization": f"Bearer {sign_token(key, claims)}"}
    answered: dict[str, object] = {}
    reads = 0
    with TestClient(__import__("services.api.app", fromlist=["app"]).app) as client:
        for name, route in sorted(_routes().items()):
            if "GET" not in route.methods:
                continue
            reads += 1
            path = route.path.replace("{investigation_id}", case)
            for number in ("{z}", "{x}", "{y}"):
                path = path.replace(number, "0")
            path = re.sub(r"\{[a-z_]+(:path)?\}", "x", path)
            response = client.get(path, headers=headers)
            if response.status_code in (403, 404):
                continue
            # A route that answers must answer with nothing of the deployment's.
            assert response.status_code == 200, (name, path, response.status_code, response.text)
            answered[name] = response.json()
    assert reads >= 40, f"only {reads} read routes reached"
    unexpected = answered.keys() - REFERENCE_CATALOGUES - EMPTY_FOR_NO_ROLE
    assert not unexpected, {name: str(answered[name])[:300] for name in unexpected}
    # The case and its dataset exist (made above); this person is shown neither, nor any right.
    for name in EMPTY_FOR_NO_ROLE:
        assert name in answered and _holds_nothing(answered[name]), (name, answered.get(name))


#: Read routes any signed-in person may call (`ROUTE_RIGHTS` `None`, ADR-112) that hold the
#: product's own reference catalogues — the handling scheme, the ontology, the yardstick, the
#: grading scheme, the basemaps, the connectors, domain packs and transforms offered, the model
#: engines, the API's own description, liveness and readiness — and nothing of any case.
REFERENCE_CATALOGUES = frozenset({
    "get_handling_scheme_route", "get_map_providers_route", "get_ontology_route",
    "get_yardstick_route", "get_grading_scheme_route", "list_connectors", "list_domain_packs",
    "list_transforms",
    "model_engines_route", "openapi_document_route", "liveness_route", "readiness_route",
})  # fmt: skip
#: Read routes any signed-in person may call that hold the deployment's data — its cases, its
#: datasets and the person's own rights — and answer this person with none.
EMPTY_FOR_NO_ROLE = frozenset({"list_investigations", "list_datasets_route", "my_rights_route"})


def _holds_nothing(body: object) -> bool:
    if isinstance(body, list):
        return body == []
    if isinstance(body, dict):
        return all(_holds_nothing(v) for v in body.values() if isinstance(v, (list, dict)))
    return True
