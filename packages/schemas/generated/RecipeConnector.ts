// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type Profile = string;
export type Delimiter = string;
export type Encoding = string;
export type HeaderRows = number;
export type DateOrder = ("dmy" | "mdy") | null;
export type SourceCrs = string | null;

export interface RecipeConnector {
  profile: Profile;
  delimiter?: Delimiter;
  encoding?: Encoding;
  header_rows?: HeaderRows;
  date_order?: DateOrder;
  source_crs?: SourceCrs;
  [k: string]: unknown;
}
