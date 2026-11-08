// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Table = string;
export type RowIndex = number;
export type LoadId = string | null;
export type Side = ("left" | "right") | null;

/**
 * ADR-140 Amendment 12: a row a rejection came from, in a staged run. The table it is a row of
 * (a source's name, `reference_list:<name>@v<n>`, or a staged step's table), its row number, the
 * load that read it (a source row's; `None` for a list row or a staged table's row) and, for a
 * Join, the side. **No row key, raw or hashed** (rule 7;
 * `tests/schemas/test_staging_report_schemas.py`).
 */
export interface RejectionRef {
  table: Table;
  row_index: RowIndex;
  load_id?: LoadId;
  side?: Side;
}
