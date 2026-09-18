// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type SourceLocation = string | null;

/**
 * Body of `POST /v1/investigations/{id}/ingest/recipes/{id}/run` —
 * §8: "Loader: run a published recipe against a file", not necessarily
 * the one Connect recorded. `source_location` is optional: omitted, the
 * run repeats against the recipe's own recorded location (a plain
 * re-run); given, it overrides just this run, the ordinary shape of a
 * Loader's day — a fresh day's export through an already-mapped recipe.
 */
export interface RunRecipeInput {
  source_location?: SourceLocation;
  [k: string]: unknown;
}
