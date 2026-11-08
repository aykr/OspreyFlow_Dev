// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string;
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
export type Gives = string[];

/**
 * A built-in role or the *Super user* preset (ADR-145 decision 7): listed with its rights,
 * copied into a custom role, never edited. A preset is given as the roles it names.
 */
export interface BuiltInRole {
  id: Id;
  label: Label;
  rights: Rights;
  gives?: Gives;
  [k: string]: unknown;
}
