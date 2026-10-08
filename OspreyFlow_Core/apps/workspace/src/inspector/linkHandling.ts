// What counts as lowering a link's handling (ADR-102), mirrored from the Conduit's
// `ontology.handling.merge_handling` so the Change form can say so, and ask for a confirmation,
// before the server would refuse. The server's rule still decides.
import type { Handling } from "../../../../packages/schemas/generated";
import type { HandlingScheme } from "../ingest/api";

const DISSEMINATION = { permitted: 0, conditional: 1, restricted: 2 } as const;

function actionRank(code: string | null | undefined, scheme: HandlingScheme): number {
  if (!code) return 0;
  const action = scheme.action_codes?.[code];
  if (!action) return 0;
  return (action.direct_action ? 1 : 2) * 2 + (action.originator_permission ? 1 : 0);
}

function sanitisationRank(code: string | null | undefined, scheme: HandlingScheme): number {
  if (!code) return 0;
  return scheme.sanitisation_codes?.[code]?.consult_originator ? 2 : 1;
}

/** The parts of `wanted` that are lower than `old`'s, in the order the form shows them. */
export function lowerParts(old: Handling, wanted: Handling, scheme: HandlingScheme): string[] {
  const parts: string[] = [];
  if (scheme.classification.indexOf(wanted.classification) < scheme.classification.indexOf(old.classification)) {
    parts.push("classification");
  }
  const rank = (code: string) => DISSEMINATION[scheme.handling_codes[code]?.dissemination ?? "permitted"];
  if (rank(wanted.handling_code) < rank(old.handling_code)) parts.push("handling code");
  if (actionRank(wanted.action_code, scheme) < actionRank(old.action_code, scheme)) parts.push("action code");
  if (sanitisationRank(wanted.sanitisation_code, scheme) < sanitisationRank(old.sanitisation_code, scheme)) {
    parts.push("sanitisation code");
  }
  return parts;
}
