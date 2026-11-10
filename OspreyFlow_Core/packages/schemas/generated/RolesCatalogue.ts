// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type Right =
  | "create_case"
  | "share_case"
  | "remove_case"
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
  | "write_sql_transforms"
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
export type BuiltIn = BuiltInRole[];
export type Id1 = string;
export type Name = string;
export type Version = number;
export type Rights1 = Right[];
export type ChangedBy = string;
export type ChangedAt = string;
export type Holders = number;
export type RoleId = string;
export type DisplayName = string;
export type Mailbox = string;
export type Lead = string | null;
export type Cover = string | null;
export type CoverUntil = string | null;
export type ActingLead = string | null;
export type Id2 = string;
export type Name1 = string | null;
export type Members = TeamMember[];
export type Custom = CustomRole[];

/**
 * `GET /v1/admin/roles`: the built-in roles, the preset and every custom role.
 */
export interface RolesCatalogue {
  built_in: BuiltIn;
  custom: Custom;
  [k: string]: unknown;
}
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
/**
 * A custom role's current version, held in the token as `role:<id>`.
 */
export interface CustomRole {
  id: Id1;
  name: Name;
  version: Version;
  rights: Rights1;
  changed_by: ChangedBy;
  changed_at: ChangedAt;
  holders?: Holders;
  team?: Team | null;
  [k: string]: unknown;
}
/**
 * A team: a custom role's holders (the owner's L2.5 Q4 (a)), its lead, and a cover until a
 * date. `acting_lead` is the cover while the cover lasts, else the lead: the shape ADR-146
 * Amendment 1's queue tools read (rules' L2.10, `services/api/teams.py::acting_lead`).
 */
export interface Team {
  role_id: RoleId;
  display_name: DisplayName;
  mailbox: Mailbox;
  lead?: Lead;
  cover?: Cover;
  cover_until?: CoverUntil;
  acting_lead?: ActingLead;
  members?: Members;
  [k: string]: unknown;
}
export interface TeamMember {
  id: Id2;
  name?: Name1;
  [k: string]: unknown;
}
