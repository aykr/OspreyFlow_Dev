// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DateOrder = ("dmy" | "mdy") | null;
export type Tz = string | null;

export interface DateParseSettings {
  date_order?: DateOrder;
  tz?: Tz;
}
