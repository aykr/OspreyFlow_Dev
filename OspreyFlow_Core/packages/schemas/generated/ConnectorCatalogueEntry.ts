// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type Group = string;
export type Structured = boolean;
export type Available = boolean;

/**
 * One row of §2's structured/unstructured connector tables, reproduced
 * verbatim rather than derived, so the Connect screen's catalogue always
 * matches the doc exactly. `id` is a `RecipeConnector.profile` value once
 * a recipe is drafted against this entry.
 *
 * **`available` is derived, not declared** (round 13bf). It is `True` iff a
 * `connectors/<id>.yaml` profile exists naming a reader this codebase implements —
 * `packages/schemas/connectors.py` owns that, and `09_INGEST_STUDIO.md` §2's own "a validated
 * YAML file in `connectors/`, so adding a new carrier's CDR layout is a file rather than a
 * release" is the sentence it finally makes true. Before that it was a literal here *and* a
 * second, unconnected literal in `services/api/studio_profile.py`: two hand-maintained truths
 * about one fact, which is how the CDR layout came to be declared in this table and refused by
 * the Studio.
 *
 * The entry still appears when unavailable; the catalogue is never trimmed down to only what
 * works, since the whole point of showing it is that the gap is visible, not hidden.
 */
export interface ConnectorCatalogueEntry {
  id: Id;
  label: Label;
  group: Group;
  structured: Structured;
  available?: Available;
  [k: string]: unknown;
}
