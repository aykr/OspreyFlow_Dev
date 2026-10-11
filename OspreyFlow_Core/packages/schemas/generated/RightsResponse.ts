// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Right =
  | "create_case"
  | "share_case"
  | "remove_case"
  | "branch_case"
  | "export"
  | "export_override"
  | "investigate"
  | "edit_graph"
  | "confirm_inferred"
  | "extract_files"
  | "resolve_entities"
  | "record_assessment"
  | "ask_model"
  | "run_analysis"
  | "propose_link_type"
  | "read_alert_queue"
  | "triage_alerts"
  | "deploy_rules"
  | "read_rule_audit"
  | "read_held_rows"
  | "decide_held_rows"
  | "trace_ownership"
  | "keep_watches"
  | "load_screening_lists"
  | "edit_pipelines"
  | "verify_pipelines"
  | "publish_pipelines"
  | "run_pipelines"
  | "schedule_pipelines"
  | "add_ingest_files"
  | "revert_loads"
  | "read_reports"
  | "read_report_feed"
  | "read_data_feeds"
  | "administer_system"
  | "manage_people"
  | "manage_dashboards"
  | "operate_schedules"
  | "manage_ontology"
  | "manage_geospatial"
  | "read_audit"
  | "read_export_ledger";
export type Rights = Right[];

/**
 * `GET /v1/me/rights`: what the signed-in person may do, so the Glass and the Studio can leave
 * out what they would only refuse. The Conduit still refuses it (decision 1).
 */
export interface RightsResponse {
  rights: Rights;
  [k: string]: unknown;
}
