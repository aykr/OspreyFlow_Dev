import type { Node } from "../../../../packages/schemas/generated";
import { chosenLabel } from "../canvas/labelChoices";

export type MatchMode = "starts_with" | "contains" | "exact";

export interface SearchOptions {
  mode: MatchMode;
  ignoreCase: boolean;
  /** Entity types to search. Empty means every type. */
  types: string[];
  /** Search only the nodes drawn on the canvas, without asking the Conduit. */
  onScreenOnly: boolean;
}

export const DEFAULT_SEARCH_OPTIONS: SearchOptions = {
  mode: "starts_with",
  ignoreCase: false,
  types: [],
  onScreenOnly: false,
};

/** The properties that hold the value an analyst types, in the order worth showing. A suggestion
 * labelled with the node's opaque id tells the analyst nothing about which account it is. */
export const DISPLAY_PROPERTIES = [
  "value_normalised",
  "name",
  "title",
  "email",
  "handle",
  "nino",
  "imei",
  "postcode",
  "org_ref",
];

/** The body for `POST /v1/suggest` (ADR-061). A filter left at its default is not sent, so the
 * Conduit's own defaults apply and an unfiltered search is the request ADR-059 already defined. */
export function suggestBody(query: string, limit: number, options: SearchOptions): Record<string, unknown> {
  const body: Record<string, unknown> = { query, limit };
  if (options.mode !== DEFAULT_SEARCH_OPTIONS.mode) body.mode = options.mode;
  if (options.ignoreCase) body.ignore_case = true;
  if (options.types.length > 0) body.types = options.types;
  return body;
}

/** How many filters differ from the defaults: one per filter, not one per chosen type. */
export function activeFilterCount(options: SearchOptions): number {
  return (
    Number(options.mode !== DEFAULT_SEARCH_OPTIONS.mode) +
    Number(options.ignoreCase) +
    Number(options.types.length > 0) +
    Number(options.onScreenOnly)
  );
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** A person's name as it is read, "Petrenko, Illia"; just the family name when that is all there is;
 * empty when the node has neither. */
function personName(properties: Record<string, unknown>): string {
  const family = text(properties.family_name);
  const given = text(properties.given_names);
  if (family && given) return `${family}, ${given}`;
  return family || given;
}

/** What to call a node on screen: the label the analyst chose for its type (ADR-076), else a
 * person's name, else its identifying value, else its id. */
export function displayValue(node: Node): string {
  const chosen = chosenLabel(node);
  if (chosen !== null) return chosen;
  const properties = (node.properties ?? {}) as Record<string, unknown>;
  const name = personName(properties);
  if (name) return name;
  for (const key of DISPLAY_PROPERTIES) {
    const value = properties[key];
    if (typeof value === "string" && value) return value;
  }
  return node.id;
}

function searchableValues(node: Node): string[] {
  const properties = (node.properties ?? {}) as Record<string, unknown>;
  // The name parts are matched one by one, so "Petrenko" and "Illia" each find the person.
  const values: string[] = [text(properties.family_name), text(properties.given_names)].filter(Boolean);
  for (const key of DISPLAY_PROPERTIES) {
    const value = properties[key];
    if (typeof value === "string" && value) values.push(value);
  }
  return values;
}

function matches(value: string, query: string, options: SearchOptions): boolean {
  const left = options.ignoreCase ? value.toLowerCase() : value;
  const right = options.ignoreCase ? query.toLowerCase() : query;
  if (options.mode === "exact") return left === right;
  if (options.mode === "contains") return left.includes(right);
  return left.startsWith(right);
}

/** The same question the Conduit answers, put to the nodes already drawn. Plain string
 * comparison: what is typed is text, never a pattern. */
export function matchOnScreen(
  nodes: readonly Node[],
  query: string,
  options: SearchOptions,
  limit: number,
): { nodes: Node[]; more: boolean } {
  if (query === "") return { nodes: [], more: false };
  const found = nodes.filter(
    (node) =>
      (options.types.length === 0 || options.types.includes(node.type)) &&
      searchableValues(node).some((value) => matches(value, query, options)),
  );
  return { nodes: found.slice(0, limit), more: found.length > limit };
}
