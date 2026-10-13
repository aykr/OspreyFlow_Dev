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
 "create_investigation": "create_case", "list_datasets_route": None, "create_dataset_route": "create_case",
 "case_datasets_route": None, "set_case_datasets_route": "share_case", "list_investigations": None,
 "set_tab_state": None, "rename_investigation": "share_case", "remove_investigation": "remove_case",
 "get_investigation_access": "share_case", "set_investigation_unit_level": "share_case",
 "set_investigation_grant": "share_case", "remove_investigation_grant": "share_case",
 "get_investigation_access_history": "share_case", "get_investigation": None,
 "branch_investigation": "branch_case",
 "seed": "investigate", "expand": "investigate", "links_among_route": "investigate",
 "expand_preview": "investigate", "remove_nodes": "investigate",
 "get_resolution_threshold_route": "investigate", "set_resolution_threshold_route": "investigate",
 "link_resolution_route": "resolve_entities", "split_resolution_route": "resolve_entities",
 "explain_resolution_route": "investigate", "compute_metric_route": "run_analysis",
 "run_extraction_route": "extract_files", "list_extraction_candidates_route": "extract_files",
 "accept_extraction_candidate_route": "extract_files", "reject_extraction_candidate_route": "extract_files",
 "get_dossier_document_route": "investigate", "confirm_node_route": "confirm_inferred",
 "mark_node_for_suppression": "edit_graph", "unmark_node_for_suppression": "edit_graph",
 "retract_node_route": "confirm_inferred", "get_investigation_history": "investigate",
 "restore_history_step": "investigate", "search_route": "investigate", "suggest_route": "investigate",
 "explore_counts_route": "investigate", "explore_most_connected_route": "investigate",
 "explore_busiest_links_route": "investigate", "explore_busiest_days_route": "investigate",
 "explore_groups_route": "investigate", "explore_whats_new_route": "investigate",
 "explore_starter_questions_route": "investigate", "explore_starter_run_route": "investigate",
 "shared_contacts_route": "investigate", "shared_pair_canvas_route": "investigate",
 "patterns_preview_route": "investigate", "patterns_run_route": "investigate",
 "patterns_save_route": "investigate", "patterns_list_route": "investigate", "patterns_load_route": "investigate",
 "create_hotlist_route": "keep_watches", "list_hotlists_route": "keep_watches",
 "save_judgement_route": "record_assessment", "list_judgements_route": "investigate",
 "change_link_route": "edit_graph", "case_link_types_route": "investigate",
 "propose_link_type_route": "propose_link_type", "withdraw_link_type_route": "propose_link_type",
 "list_link_type_proposals_route": "manage_ontology", "promote_link_type_route": "manage_ontology",
 "reject_link_type_route": "manage_ontology", "retire_link_type_route": "manage_ontology",
 "link_history_route": "investigate", "list_link_events_route": "investigate",
 "extract_email_route": "extract_files", "read_document_route": "investigate",
 "designate_in_document_route": "extract_files", "upload_document_route": "extract_files",
 "document_file_route": "investigate", "set_entity_picture_route": "edit_graph",
 "remove_entity_picture_route": "edit_graph", "entity_pictures_route": "investigate",
 "entity_picture_file_route": "investigate", "extract_document_route": "extract_files",
 "accept_document_candidate_route": "extract_files", "accept_document_candidates_route": "extract_files",
 "reject_document_candidate_route": "extract_files", "ask_question_route": "ask_model",
 "list_questions_route": "investigate", "accept_question_candidate_route": "extract_files",
 "reject_question_candidate_route": "extract_files", "show_emails_as_documents_route": "extract_files",
 "accept_email_candidate_route": "extract_files", "reject_email_candidate_route": "extract_files",
 "list_link_notes_route": "investigate", "add_link_note_route": "edit_graph",
 "edit_link_note_route": "edit_graph", "remove_link_note_route": "edit_graph",
 "save_gap_route": "record_assessment", "list_gaps_route": "investigate",
 "save_assumption_route": "record_assessment", "list_assumptions_route": "investigate",
 "submit_export_route": "export", "list_exports_route": "read_export_ledger",
 "create_monitor_route": "keep_watches", "list_monitors_route": "keep_watches",
 "list_alerts_route": "keep_watches", "get_alert_route": "keep_watches", "jump_alert_route": "keep_watches",
 "paths_route": "investigate", "resolve_now_route": "resolve_entities",
 "readiness_route": None, "liveness_route": None, "get_ontology_route": None,
 "get_map_providers_route": None, "get_map_tile_route": None, "get_map_local_source_route": None,
 "build_basemap_route": "manage_geospatial", "verify_map_route": "manage_geospatial",
 "histogram_route": "investigate", "case_event_holders_route": "investigate", "cross_filter_route": "investigate", "first_seen_route": "investigate",
 "geo_bins_route": "investigate", "sightings_route": "investigate", "geometries_route": "investigate",
 "create_site": "edit_graph", "get_site": "investigate", "get_site_image": "investigate",
 "set_site_control_points": "edit_graph", "set_site_grid": "edit_graph",
 "list_connectors": None, "list_domain_packs": None, "get_handling_scheme_route": None,
 "get_yardstick_route": None, "list_ingest_source_files": "add_ingest_files",
 "upload_ingest_source_file": "add_ingest_files", "create_studio_recipe_draft": "edit_pipelines",
 "update_studio_recipe_draft": "edit_pipelines", "update_studio_recipe_pipeline": "edit_pipelines",
 "get_studio_recipe_draft": "edit_pipelines", "list_studio_recipe_drafts": "edit_pipelines",
 "get_studio_recipe_profile": "edit_pipelines", "list_transforms": None,
 "update_studio_recipe_row_template": "edit_pipelines", "get_studio_recipe_sample_row": "edit_pipelines",
 "preview_studio_recipe_element_handling": "edit_pipelines", "verify_studio_recipe": "verify_pipelines",
 "list_studio_recipe_registry": "edit_pipelines", "publish_studio_recipe": "publish_pipelines",
 "update_studio_recipe_schedule": "schedule_pipelines", "create_studio_recipe_version": "edit_pipelines",
 "run_studio_recipe": "run_pipelines", "trace_ownership_route": "trace_ownership",
 "ownership_canvas": "trace_ownership", "kyc_status_route": "trace_ownership",
 "neighbourhood_risk_route": "trace_ownership", "read_case_report": "read_reports", "list_embedded_dashboards": "read_reports",
 "embedded_dashboard_guest_token": "read_reports",
 # ADR-113 decision 7: building, saving and reading trends is run_analysis.
 "trend_options_route": "run_analysis", "preview_trend": "run_analysis", "save_trend": "run_analysis",
 "list_trends": "run_analysis", "trend_figures": "run_analysis", "delete_trend": "run_analysis",
 # ADR-113 decision 7: assembling, refreshing and publishing a pack is record_assessment; reading
 # what was published is read_reports.
 "create_pack": "record_assessment", "list_packs": "record_assessment", "read_pack": "record_assessment",
 "add_pack_item": "record_assessment", "remove_pack_item": "record_assessment",
 "reorder_pack": "record_assessment", "refresh_pack_item": "record_assessment",
 "pack_history": "record_assessment", "publish_pack": "record_assessment",
 "withdraw_pack_version": "record_assessment", "list_published_packs": "read_reports",
 "read_published_pack": "read_reports", "export_pack_route": "export",
 "read_report_feed": "read_report_feed", "read_alert_queue": "read_alert_queue",
 "explain_alert": "read_alert_queue", "claim_alert": "triage_alerts", "release_alert": "triage_alerts",
 "dispose_alert": "triage_alerts", "alert_canvas": "triage_alerts",
 "list_typology_rules": "read_alert_queue", "deploy_typology_rule": "deploy_rules",
 "retire_typology_rule": "deploy_rules", "read_rule_audit": "read_rule_audit",
 "list_held_rows": "read_held_rows", "release_held_rows_route": "decide_held_rows",
 "reject_held_rows": "decide_held_rows", "issue_ws_ticket": None, "my_rights_route": None,
 "list_people_route": "manage_people", "set_person_roles_route": "manage_people",
 # ADR-114 Amendment 5 (B4b)
 "invite_person_route": "manage_people", "set_person_access_route": "manage_people",
 "disable_person_route": "manage_people", "enable_person_route": "manage_people",
 "reset_person_sign_in_route": "manage_people",
 "list_demo_packs_route": "administer_system",
 "list_dashboards_route": "manage_dashboards", "register_dashboard_route": "manage_dashboards",
 "remove_dashboard_route": "manage_dashboards", "system_status_route": "administer_system",
 "list_schedules_route": "operate_schedules", "schedule_runs_route": "operate_schedules",
 "pause_schedule_route": "operate_schedules", "resume_schedule_route": "operate_schedules",
}


AUTHOR = Principal(id="rights-author", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    import os

    previous = {k: os.environ.get(k) for k in ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")}
    os.environ.update(OIDC_JWKS_URL=jwks_url, OIDC_ALGORITHMS="RS256", ARCADEDB_DATABASE="ospreyflow")
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
    area (ADR-110 Amendment 1, ADR-112) and ADR-110's run ledger; screening lists load by a script;
    reverting a load has no route (spec 09 §6)."""
    not_yet = {"read_data_feeds", "load_screening_lists",
               "revert_loads", "read_audit",
               "export_override"}  # fmt: skip
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
            assert _call(client, route, case, _token(key, "rights-member", without)) == 403, (name, right)
            assert _call(client, route, case, _token(key, "rights-outsider", [f"right:{right}"])) in (403, 404), (name, right)
    assert len(checked) >= 25, f"only {len(checked)} rights reached a case route"
