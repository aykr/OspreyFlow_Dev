// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Title = string;
export type Shows = string;
export type Delivery = "seed" | "download";
export type Licence = string;
export type Attribution = string | null;
export type CaseName = string;
export type LoadedCaseId = string | null;
export type Command = string;
export type SourcePage = string | null;
export type SizeBytes = number | null;

/**
 * A demo pack as the Admin area shows it (ADR-114 Amendment 5, "Show and explain"): what it
 * shows, its licence and credit, whether it is loaded — only in a case the administrator can open
 * — and the command that adds it on the host. The Conduit never runs it.
 */
export interface DemoPackStatus {
  id: Id;
  title: Title;
  shows: Shows;
  delivery: Delivery;
  licence: Licence;
  attribution?: Attribution;
  case_name: CaseName;
  loaded_case_id?: LoadedCaseId;
  command: Command;
  source_page?: SourcePage;
  size_bytes?: SizeBytes;
  [k: string]: unknown;
}
