// Pure helpers over `RowTemplate`/`FieldBinding` — `docs/09_INGEST_STUDIO.md`
// §4. No component logic lives here so it can be unit-tested directly
// (this repo has no RTL/jsdom setup — `ConnectScreen.test.ts`'s own
// docstring — so a screen's *logic* is what gets covered, not its render).
import type {
  EdgeTypeDef,
  EntityTypeDef,
  FieldBinding,
  OntologySchema,
  RecipeEdge,
  RecipeEntity,
  RowTemplate,
  TransformDescriptor,
} from "../../../../../packages/schemas/generated";

/** The next unused entity ref, `e1`, `e2`, ... — refs are freeform strings
 * on the wire (`RecipeEntity.ref`), but a stable, readable generated
 * sequence is what the canvas offers by default; an analyst can still
 * rename one (§6's example recipe uses `a`/`b`/`cell`). */
export function nextEntityRef(entities: RecipeEntity[]): string {
  const used = new Set(entities.map((e) => e.ref));
  let n = 1;
  while (used.has(`e${n}`)) n++;
  return `e${n}`;
}

/** Entity concrete types under a POLE class — §4: "POLE first, then
 * narrow." */
export function entityTypesForPole(
  ontology: OntologySchema,
  poleClass: string,
): EntityTypeDef[] {
  return ontology.entity_types.filter((t) => t.pole_class === poleClass);
}

/** Edge types valid between two already-chosen entity concrete types —
 * not required by §4's prose, but a direct, low-cost use of
 * `EdgeTypeDef.from`/`.to` that keeps the studio from letting an analyst
 * draw a link the ontology would reject at Verify/load time anyway. */
export function edgeTypesForEndpoints(
  ontology: OntologySchema,
  fromType: string,
  toType: string,
): EdgeTypeDef[] {
  return ontology.edge_types.filter(
    (t) => !t.system && t.from.includes(fromType) && t.to.includes(toType),
  );
}

/** A transform's declared column count — 1 for any transform not in the
 * catalogue's own `arity` (single `field`, never `fields`), per
 * `packages/knowledge_adapters`'s own docstring. */
export function arityForTransform(
  transforms: TransformDescriptor[],
  name: string | null | undefined,
): number {
  if (!name) return 1;
  return transforms.find((t) => t.name === name)?.arity ?? 1;
}

function bindingsOf(template: RowTemplate): FieldBinding[] {
  const bindings: FieldBinding[] = [];
  for (const entity of template.entities) {
    bindings.push(...Object.values(entity.properties ?? {}));
  }
  for (const edge of template.edges ?? []) {
    bindings.push(...Object.values(edge.properties ?? {}));
    if (edge.temporal) bindings.push(edge.temporal.at);
  }
  return bindings;
}

/** Every source field name a binding anywhere in the template actually
 * references — `field` or every entry of `fields`. */
export function boundFieldNames(template: RowTemplate): Set<string> {
  const names = new Set<string>();
  for (const binding of bindingsOf(template)) {
    if (binding.field) names.add(binding.field);
    for (const name of binding.fields ?? []) names.add(name);
  }
  return names;
}

/** §4: "Unmapped fields are shown, always." A profiled column with no
 * binding anywhere in the template and no explicit `ignore` entry. */
export function unmappedFieldNames(
  profileColumnNames: string[],
  template: RowTemplate,
  ignoredFieldNames: Set<string>,
): string[] {
  const bound = boundFieldNames(template);
  return profileColumnNames.filter((name) => !bound.has(name) && !ignoredFieldNames.has(name));
}

/** §3's independent-minimums rule, restated in §4: a per-element
 * `handling` override may tighten but never loosen the source-level
 * classification set at Connect. Mirrors the server-side check
 * (`services/api/studio_map.py`'s `validate_handling_tightens`) for
 * immediate UI feedback — the server call is still the authority, this is
 * only a pre-check. `classificationOrder` is `HandlingScheme.classification`,
 * least restrictive first. */
export function classificationWouldLoosen(
  classificationOrder: string[],
  baselineClassification: string,
  overrideClassification: string | null | undefined,
): boolean {
  if (!overrideClassification || overrideClassification === baselineClassification) return false;
  const baselineRank = classificationOrder.indexOf(baselineClassification);
  const overrideRank = classificationOrder.indexOf(overrideClassification);
  if (baselineRank === -1 || overrideRank === -1) return false;
  return overrideRank < baselineRank;
}

/** All entity refs an edge may legally point at — every other entity's
 * ref (an edge cannot reference itself as both endpoints in this studio;
 * nothing in the schema forbids it, but the canvas never offers it). */
export function entityRefs(template: RowTemplate): string[] {
  return template.entities.map((e) => e.ref);
}

export function findEntity(template: RowTemplate, ref: string): RecipeEntity | undefined {
  return template.entities.find((e) => e.ref === ref);
}

export function findEdge(template: RowTemplate, index: number): RecipeEdge | undefined {
  return template.edges?.[index];
}
