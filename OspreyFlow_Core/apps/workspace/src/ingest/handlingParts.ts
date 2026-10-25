// The six parts of a marking a source column may carry (ADR-127 decision 3), as Connect declares
// them and Map binds them. Mirrors `HANDLING_BINDABLE` in `packages/schemas/ingest.py`; the server
// is the authority, this is the Glass's own copy of the list and its wording.

export const HANDLING_BINDABLE = [
  "classification",
  "handling_code",
  "action_code",
  "sanitisation_code",
  "originator",
  "owning_unit",
] as const;

export type HandlingPart = (typeof HANDLING_BINDABLE)[number];

export const HANDLING_PART_LABELS: Record<HandlingPart, string> = {
  classification: "Classification",
  handling_code: "Handling code",
  action_code: "Action code",
  sanitisation_code: "Sanitisation code",
  originator: "Originator",
  owning_unit: "Owning unit",
};

/** `merge_handling`'s order (`packages/ontology/handling.py`), for the codes a scheme defines: the
 * rank of a code, higher being tighter. `null` where the scheme does not define it, so the caller
 * can say nothing rather than guess. */
export interface CodeScheme {
  handling_codes: Record<string, { dissemination: "permitted" | "conditional" | "restricted" }>;
  action_codes?: Record<string, { direct_action: boolean; originator_permission?: boolean }>;
  sanitisation_codes?: Record<string, { consult_originator: boolean }>;
}

const DISSEMINATION_RANK = { permitted: 0, conditional: 1, restricted: 2 } as const;

function codeRank(part: string, code: string, scheme: CodeScheme): number | null {
  if (part === "handling_code") {
    const def = scheme.handling_codes[code];
    return def ? DISSEMINATION_RANK[def.dissemination] : null;
  }
  if (part === "action_code") {
    const def = scheme.action_codes?.[code];
    if (!def) return null;
    return (def.direct_action ? 1 : 2) * 2 + (def.originator_permission ? 1 : 0);
  }
  if (part === "sanitisation_code") {
    const def = scheme.sanitisation_codes?.[code];
    return def ? (def.consult_originator ? 2 : 1) : null;
  }
  return null;
}

/** Whether a literal `code` for a handling, action or sanitisation code part is looser than the
 * source's own, by the order `merge_handling` keeps the stricter of. Only where both codes are
 * defined: a source with no code, or a code the scheme lacks, gives no answer, so no warning. */
export function codeWouldLoosen(
  part: string,
  scheme: CodeScheme | null | undefined,
  sourceCode: unknown,
  literal: string,
): boolean {
  if (!scheme || typeof sourceCode !== "string") return false;
  const base = codeRank(part, sourceCode, scheme);
  const chosen = codeRank(part, literal, scheme);
  return base !== null && chosen !== null && chosen < base;
}

/** What an element's `handling` says about one part: nothing (the source's default), a literal
 * value, or `{field: <column>}` read per row. A recipe may hold either shape, so no reader may
 * assume a string. */
export type HandlingPartState =
  | { kind: "default" }
  | { kind: "literal"; value: string }
  | { kind: "column"; field: string };

export function handlingPartState(
  override: Record<string, unknown> | null | undefined,
  part: string,
): HandlingPartState {
  const value = override?.[part];
  if (typeof value === "string" && value !== "") return { kind: "literal", value };
  if (value !== null && typeof value === "object") {
    const field = (value as { field?: unknown }).field;
    if (typeof field === "string" && field !== "") return { kind: "column", field };
  }
  return { kind: "default" };
}
