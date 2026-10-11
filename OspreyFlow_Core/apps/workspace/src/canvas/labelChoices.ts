// Which property names a node of each type on screen (ADR-076).
//
// Six people of one family were each drawn as "Volkov", which tells an analyst nothing. The analyst
// can now choose, per entity type, the property that names its nodes; with no choice a person reads
// "Family, Given" and anything else keeps what it always had.
//
// The choice is a way of looking, so it is kept in this browser only, never sent to the server and
// not part of the case: the same standing the light/dark theme has (ADR-070). The canvas cannot
// read it from a component's state, so, like the theme, it is a small store the canvas listens to.
import type { EntityTypeDef, Node } from "../../../../packages/schemas/generated";
import { TYPOLOGY_LABELS } from "../alerts/names";

export const LABEL_CHOICES_KEY = "ospreyflow.node-labels";

/** Entity type name to the name of the property chosen for it. A type with no entry has no choice. */
export type LabelChoices = Readonly<Record<string, string>>;

let cache: LabelChoices | null = null;
const listeners = new Set<() => void>();

function parse(raw: string | null): LabelChoices {
  if (raw === null) return {};
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
    const entries = Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string" && entry[1] !== "",
    );
    return Object.fromEntries(entries);
  } catch {
    return {};
  }
}

function load(): LabelChoices {
  if (cache === null) {
    try {
      cache = parse(localStorage.getItem(LABEL_CHOICES_KEY));
    } catch {
      // A private window or blocked site data: the choice then lasts for this page only.
      cache = {};
    }
  }
  return cache;
}

/** The choices now in force. */
export function getLabelChoices(): LabelChoices {
  return load();
}

/** Chooses `property` to name nodes of `entityType`, or, with `null`, goes back to the default. */
export function setLabelChoice(entityType: string, property: string | null): void {
  const before = load();
  if ((before[entityType] ?? null) === property) return;
  const next: Record<string, string> = { ...before };
  if (property === null) delete next[entityType];
  else next[entityType] = property;
  cache = next;
  try {
    localStorage.setItem(LABEL_CHOICES_KEY, JSON.stringify(next));
  } catch {
    // Kept in memory for this page, which is the honest fallback.
  }
  listeners.forEach((listener) => listener());
}

/** Calls `listener` whenever a choice changes. Returns the function that stops it. */
export function onLabelChoicesChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Forgets what was read, so the next read comes from storage again. For tests. */
export function forgetLabelChoicesForTest(): void {
  cache = null;
  listeners.clear();
}

function asText(value: unknown): string | null {
  if (typeof value === "string") return value === "" ? null : value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

/** The label the analyst chose for this node's type, or `null` when none was chosen or this node
 * has no value for the chosen property (so a node is never left without a name). */
export function chosenLabel(node: Node): string | null {
  const property = load()[node.type];
  if (property === undefined) return null;
  return asText(node.properties?.[property]);
}

/** What a node is called when nothing was chosen: a person by family name and given names; a thing
 * with a name or a title (an organisation, a place, a document) by it; else by its normalised value
 * (an address, a number); and only failing all of those by its id. */
export function defaultLabel(node: Node): string {
  const properties = (node.properties ?? {}) as Record<string, unknown>;
  // A rule's alert (ADR-109) has no name of its own: it is called by what its rule found.
  if (node.type === "Alert") {
    const typology = asText(properties["typology"]);
    return typology !== null && TYPOLOGY_LABELS[typology] ? `${TYPOLOGY_LABELS[typology]} alert` : "Alert";
  }
  const family = asText(properties["family_name"]);
  if (family !== null) {
    const given = asText(properties["given_names"]);
    return given !== null ? `${family}, ${given}` : family;
  }
  return (
    asText(properties["name"]) ??
    asText(properties["title"]) ??
    asText(properties["value_normalised"]) ??
    node.id
  );
}

/** The properties an analyst can choose from for a type: its identifiers, then its other
 * properties, each once. A sensitive property is never offered (a label is drawn on the canvas for
 * anyone looking over a shoulder), nor a list. */
export function labelPropertiesFor(type: EntityTypeDef): string[] {
  const offered = (property: { sensitivity?: string | null; type: string } | undefined): boolean =>
    property === undefined || (property.sensitivity !== "high" && property.type !== "string[]");
  const declared = new Map((type.properties ?? []).map((p) => [p.name, p]));
  const names: string[] = [];
  for (const name of [...(type.identifiers ?? []), ...declared.keys()]) {
    if (!names.includes(name) && offered(declared.get(name))) names.push(name);
  }
  return names;
}
