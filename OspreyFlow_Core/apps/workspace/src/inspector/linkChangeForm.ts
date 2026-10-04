// The arithmetic behind the "Change this link" form (ADR-080), kept apart from the component so each
// rule can be tested on its own: which types a link may change to, what the form starts with, and
// how what the analyst typed becomes the request the server takes — only what changed, with the
// reason, or a sentence saying what is wrong.
import type { Edge, EdgeTypeDef, PropertyDef } from "../../../../packages/schemas/generated";
import { linkTypeName } from "../canvas/linkLabel";
import type { LinkChangeInput } from "./linkChangeApi";

/** The same limit the server holds (`services/api/link_changes.py::MAX_REASON_CHARS`). */
export const MAX_REASON_CHARS = 1000;

export type BasisChoice = "direct" | "probabilistic";

export interface LinkDraft {
  type: string;
  /** What each property box holds, as typed. */
  properties: Record<string, string>;
  occurrences: string;
  validFrom: string;
  validTo: string;
  reason: string;
  /** What stands behind the link, as chosen; `""` until the analyst says (ADR-081: no default). */
  basis: BasisChoice | "";
}

/** What stands behind a link now: the link's own mark, or its type's basis (ADR-081 decision 2). */
export function currentBasis(edge: Edge, typeDef: EdgeTypeDef | undefined): BasisChoice | null {
  const typeBasis = typeDef?.basis ?? null;
  if (typeBasis === "probabilistic") return "probabilistic";
  if (edge.basis === "probabilistic") return "probabilistic";
  return typeBasis;
}

/** The bases the form may offer for this link under this type (ADR-081 Amendment 1 item 6): Direct
 * only where the type is Direct and the link is not already probabilistic, since a person never
 * promotes a link to Direct; Probabilistic always; nothing for a type with no basis. */
export function basisChoicesFor(edge: Edge, typeDef: EdgeTypeDef | undefined): BasisChoice[] {
  const typeBasis = typeDef?.basis ?? null;
  if (typeBasis === null) return [];
  if (typeBasis === "probabilistic" || edge.basis === "probabilistic") return ["probabilistic"];
  return ["direct", "probabilistic"];
}

export type ChangeOutcome =
  | { kind: "nothing" }
  | { kind: "problem"; message: string }
  | { kind: "change"; input: LinkChangeInput };

const RESOLUTION = new Set(["SAME_AS", "NOT_SAME_AS"]);

function joins(declared: readonly string[], entityType: string): boolean {
  return declared.includes("*") || declared.includes(entityType);
}

/** The types a link between these two kinds of entity may be changed to: the ontology's own rule,
 * and never a same-as type (those are confirmed or marked, not edited). */
export function typesFor(
  edgeTypes: readonly EdgeTypeDef[],
  sourceType: string,
  targetType: string,
): EdgeTypeDef[] {
  return edgeTypes.filter(
    (t) =>
      !RESOLUTION.has(t.name) &&
      t.system !== true &&
      joins(t.from, sourceType) &&
      joins(t.to, targetType),
  );
}

function propertyText(def: PropertyDef | undefined, value: unknown): string {
  if (value === undefined || value === null) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export function initialDraft(edge: Edge): LinkDraft {
  const properties: Record<string, string> = {};
  for (const [name, value] of Object.entries(edge.properties ?? {})) {
    properties[name] = propertyText(undefined, value);
  }
  return {
    type: edge.type,
    properties,
    occurrences: String(edge.occurrences ?? 1),
    validFrom: edge.interval ? edge.interval.valid_from.slice(0, 10) : "",
    validTo: edge.interval?.valid_to ? edge.interval.valid_to.slice(0, 10) : "",
    reason: "",
    basis: "",
  };
}

/** The draft after the type is changed: values are kept only for properties the new type has, and
 * a chosen basis only where the new type still allows it. */
export function retypeDraft(
  draft: LinkDraft,
  type: string,
  edgeTypes: readonly EdgeTypeDef[],
): LinkDraft {
  const def = edgeTypes.find((t) => t.name === type);
  const declared = new Set((def?.properties ?? []).map((p) => p.name));
  const properties: Record<string, string> = {};
  for (const [name, text] of Object.entries(draft.properties)) {
    if (declared.has(name)) properties[name] = text;
  }
  const basis = draft.basis !== "" && def?.basis === "direct" ? draft.basis : "";
  return { ...draft, type, properties, basis };
}

function parseProperty(def: PropertyDef, text: string): { value: unknown } | { problem: string } {
  const trimmed = text.trim();
  switch (def.type) {
    case "string":
    case "date":
    case "datetime":
    case "enum":
      return { value: trimmed };
    case "string[]":
      return {
        value: trimmed
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s !== ""),
      };
    case "integer": {
      if (!/^-?\d+$/.test(trimmed)) return { problem: `${def.name} must be a whole number.` };
      return { value: Number(trimmed) };
    }
    case "float": {
      const n = Number(trimmed);
      if (trimmed === "" || !Number.isFinite(n)) return { problem: `${def.name} must be a number.` };
      return { value: n };
    }
    case "boolean":
      return { value: trimmed === "true" };
  }
}

function sorted(value: Record<string, unknown>): string {
  return JSON.stringify(Object.keys(value).sort().map((k) => [k, value[k]]));
}

/** What the analyst typed, as the request the server takes. Only what differs from the link is
 * sent, together with the reason; `nothing` when nothing differs; a sentence when something is
 * wrong, so the server is not asked to say it. */
export function toChangeInput(
  edge: Edge,
  draft: LinkDraft,
  edgeTypes: readonly EdgeTypeDef[],
): ChangeOutcome {
  const original = initialDraft(edge);
  const reason = draft.reason.trim();
  const typeDef = edgeTypes.find((t) => t.name === draft.type);

  // Properties, only for those the chosen type declares and only when something is typed.
  const defs = typeDef?.properties ?? [];
  const properties: Record<string, unknown> = {};
  for (const def of defs) {
    const text = draft.properties[def.name] ?? "";
    const empty = text.trim() === "";
    if (empty) {
      if (def.required) return { kind: "problem", message: `${def.name} is required for ${linkTypeName(draft.type, [])}.` };
      continue;
    }
    const parsed = parseProperty(def, text);
    if ("problem" in parsed) return { kind: "problem", message: parsed.problem };
    properties[def.name] = parsed.value;
  }
  const propertiesChanged =
    draft.type !== edge.type || sorted(properties) !== sorted((edge.properties ?? {}) as Record<string, unknown>);

  const occurrencesText = draft.occurrences.trim();
  if (!/^\d+$/.test(occurrencesText) || Number(occurrencesText) < 1) {
    return { kind: "problem", message: "Records behind it must be a whole number, at least 1." };
  }
  const occurrences = Number(occurrencesText);

  if (draft.validTo !== "" && draft.validFrom === "") {
    return { kind: "problem", message: "A validity period needs a start date." };
  }
  if (draft.validTo !== "" && draft.validTo < draft.validFrom) {
    return { kind: "problem", message: "The end date is before the start date." };
  }
  const intervalChanged =
    draft.validFrom !== original.validFrom || draft.validTo !== original.validTo;

  // What stands behind the link (ADR-081 step B). With one possible answer there is nothing to
  // ask; otherwise the analyst must say before anything is saved (the question comes first, so a
  // save with nothing else changed is told what is missing rather than "nothing changed"), and
  // only a basis that differs from today's is sent.
  const choices = basisChoicesFor(edge, typeDef);
  const chosen: BasisChoice | null = choices.length === 1 ? choices[0]! : draft.basis || null;
  if (choices.length > 1 && chosen === null) {
    return { kind: "problem", message: "Say what stands behind the link: Direct or Probabilistic." };
  }
  const basisChanged = chosen !== null && chosen !== currentBasis(edge, typeDef);

  const input: LinkChangeInput = { reason };
  if (draft.type !== edge.type) input.type = draft.type;
  if (propertiesChanged) input.properties = properties;
  if (occurrences !== (edge.occurrences ?? 1)) input.occurrences = occurrences;
  if (intervalChanged) {
    input.interval =
      draft.validFrom === ""
        ? null
        : {
            valid_from: `${draft.validFrom}T00:00:00Z`,
            valid_to: draft.validTo === "" ? null : `${draft.validTo}T00:00:00Z`,
          };
  }
  if (basisChanged && chosen !== null) input.basis = chosen;

  const changed = Object.keys(input).length > 1;
  if (!changed) return { kind: "nothing" };
  if (reason === "") return { kind: "problem", message: "Say why the link is being changed." };
  if (reason.length > MAX_REASON_CHARS) {
    return { kind: "problem", message: `A reason can be at most ${MAX_REASON_CHARS} characters.` };
  }
  return { kind: "change", input };
}
