// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Version = number;
export type Name = string;
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
  | "draw_on_boards"
  | "promote_to_dataset"
  | "propose_types"
  | "read_alert_queue"
  | "triage_alerts"
  | "deploy_rules"
  | "read_rule_audit"
  | "read_held_rows"
  | "decide_held_rows"
  | "trace_ownership"
  | "keep_watches"
  | "load_screening_lists"
  | "author_rules"
  | "manage_strength_influencers"
  | "edit_pipelines"
  | "verify_pipelines"
  | "publish_pipelines"
  | "run_pipelines"
  | "schedule_pipelines"
  | "add_ingest_files"
  | "revert_loads"
  | "edit_target_model"
  | "review_promotions"
  | "accept_types"
  | "merge_datasets"
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
  | "read_export_ledger"
  | "manage_models";
export type Rights = Right[];
export type ChangedBy = string;
export type ChangedAt = string;

export interface CustomRoleVersion {
  version: Version;
  name: Name;
  rights: Rights;
  changed_by: ChangedBy;
  changed_at: ChangedAt;
  [k: string]: unknown;
}
