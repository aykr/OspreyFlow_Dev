// What a saved Map template means, as the Conduit's schema reads it (`packages/schemas/ingest.py`'s
// `RecipeEntity`, `RecipeEdge`, `FieldBinding`, `RecipeCondition`, `UnmappedField`), so a template the
// Glass sent can be compared with the committed one (ADR-140 Amendment 10). Two things are forgiven,
// and only these: a field the schema lets be `None` holding `null` (it reads as absent), and a
// `properties` that is a plain empty object (`RecipeEdge.properties` defaults to `{}`). A `null`
// anywhere else, or an empty array, string, `0` or `false` as `properties`, is kept, so it differs:
// the schema refuses each.

/** The recipe fields the schema declares `… | None`. */
const NULLABLE = new Set([
  "field", "fields", "literal", "transform", "map", "optional", "is", "equals", "match_on", "when",
  "handling", "provenance", "content", "valid_to", "temporal", "note",
]);  // prettier-ignore

const isPlainEmptyObject = (v: unknown): boolean =>
  v !== null && typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0;

export function meaning(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(meaning);
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key, v]) => v !== undefined && !(v === null && NULLABLE.has(key)) && !(key === "properties" && isPlainEmptyObject(v)))
      .map(([key, v]) => [key, meaning(v)]),
  );
}
