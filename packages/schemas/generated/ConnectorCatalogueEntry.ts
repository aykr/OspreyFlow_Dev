// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type Group = string;
export type Structured = boolean;
export type Available = boolean;

/**
 * One row of §2's structured/unstructured connector tables, reproduced
 * verbatim rather than derived, so the Connect screen's catalogue always
 * matches the doc exactly. `id` is a `RecipeConnector.profile` value once
 * a recipe is drafted against this entry. `available` is `False` for
 * every row that has no backing reader yet — only `generic-csv` does
 * today (`services/ingest/connectors/csv_connector.py`); the entry still
 * appears; the catalogue is never trimmed down to only what works, since
 * the whole point of showing it is that the gap is visible, not hidden.
 */
export interface ConnectorCatalogueEntry {
  id: Id;
  label: Label;
  group: Group;
  structured: Structured;
  available?: Available;
  [k: string]: unknown;
}
