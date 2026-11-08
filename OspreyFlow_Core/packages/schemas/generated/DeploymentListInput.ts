// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Template =
  | "ofac_sdn"
  | "ofsi_consolidated"
  | "uk_sanctions_list"
  | "un_consolidated"
  | "eu_consolidated"
  | "opensanctions"
  | "blank";
export type Location = string;
export type Ref = string;
export type PrimaryName = string;
export type Aliases = string | null;
export type DateOfBirth = string | null;
export type Nationality = string | null;
export type Identifiers = string | null;
export type Programme = string | null;
export type Separator = "|" | ";" | ",";
export type EntityType = ("Person" | "Organisation") | null;
export type EntityTypeColumn = string | null;
export type Listing = "sanction" | "pep" | "adverse_media";
export type Dataset = string | null;
export type Use = "local_development" | "scale_testing" | "owner_run_demonstration";

/**
 * Importing a list for the deployment. `location` is a file inside the ingest folder. A list
 * that is not one of OspreyFlow's synthetic files is real data: it names its dataset, which this
 * device's `real_data_exceptions.yaml` must admit (rule 9), as ADR-133's lists do.
 */
export interface DeploymentListInput {
  name: Name;
  template: Template;
  location: Location;
  mapping?: BlankListMapping | null;
  dataset?: Dataset;
  use?: Use;
}
/**
 * A client's own list, mapped field by field: each screening field is one of the file's
 * columns, or none. A person or an organisation is either one for every row, or read from a
 * column whose cells must say `Person` or `Organisation` (any other value refuses its row).
 */
export interface BlankListMapping {
  ref: Ref;
  primary_name: PrimaryName;
  aliases?: Aliases;
  date_of_birth?: DateOfBirth;
  nationality?: Nationality;
  identifiers?: Identifiers;
  programme?: Programme;
  separator?: Separator;
  entity_type?: EntityType;
  entity_type_column?: EntityTypeColumn;
  listing?: Listing;
}
