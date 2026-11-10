// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "sql";
/**
 * @minItems 1
 */
export type Inputs = [string, ...string[]];
export type Select = string;
export type Summary = string;

/**
 * Expert mode (ADR-140 decision 12; R4, R15): **one SELECT** over the tables named in
 * `inputs`, each read under its own name, run by the Vault's DuckDB in a sandbox: read-only, no
 * file or network function, no table but its inputs, a time and a memory limit, and only the
 * rows the person running it may read. Every input table carries a `_ref` column; the SELECT
 * must carry it through, as a column named `_ref` or starting `_ref_` (an aggregate as a list,
 * `list(_ref)`), so each output row names every input row it came from. `summary` is the plain
 * words guided mode and every run report show beside the SQL: mandatory.
 */
export interface SqlStep {
  id: Id;
  label?: Label;
  kind: Kind;
  inputs: Inputs;
  select: Select;
  summary: Summary;
}
