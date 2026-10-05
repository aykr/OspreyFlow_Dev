// The arithmetic behind *Define a new type…* in the change form (ADR-090 C2), apart from the
// component so each rule is tested on its own: the ID made from the display name, and what the
// analyst typed as the request the server takes, or a sentence saying what is wrong. The server
// holds the same rules (`services/api/link_types.py`); these only spare the analyst a round trip.
import type { EdgeTypeDef } from "../../../../packages/schemas/generated";
import type { ProposeLinkTypeInput } from "./linkTypesApi";

/** The nine data-channel names a type may be drawn in (`schemas/domain.py::DATA_CHANNELS`). */
export const TYPE_COLOURS = ["ochre", "rose", "plum", "violet", "indigo", "azure", "cyan", "jade", "moss"] as const;

/** The same limits the server holds. */
export const MAX_TYPE_ID_CHARS = 48;
export const MAX_PROPOSAL_REASON_CHARS = 2000;
const TYPE_ID = /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$/;

export interface TypeDraft {
  /** What a person reads, in sentence case ("Known to"). */
  label: string;
  /** The key stored on every link ("KNOWN_TO"), made from the label unless typed. */
  id: string;
  idTyped: boolean;
  /** The entity types at the link's two ends. */
  sourceType: string;
  targetType: string;
  /** Either way round: undirected, and between both kinds of entity in either order. */
  eitherWay: boolean;
  colour: string;
  thickness: string;
  reason: string;
}

export function emptyTypeDraft(sourceType: string, targetType: string): TypeDraft {
  return { label: "", id: "", idTyped: false, sourceType, targetType, eitherWay: false, colour: "", thickness: "", reason: "" };
}

export function typeIdFrom(label: string): string {
  return label
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, MAX_TYPE_ID_CHARS);
}

export type ProposalOutcome =
  | { kind: "problem"; message: string }
  | { kind: "proposal"; input: ProposeLinkTypeInput };

export function toProposal(draft: TypeDraft, offered: readonly EdgeTypeDef[]): ProposalOutcome {
  const label = draft.label.trim();
  if (label === "") return { kind: "problem", message: "Give the type a name, such as “Known to”." };
  const id = draft.id.trim();
  if (id.length < 3 || id.length > MAX_TYPE_ID_CHARS || !TYPE_ID.test(id)) {
    return {
      kind: "problem",
      message: `The ID is three to ${MAX_TYPE_ID_CHARS} capital letters, digits and single underscores, such as KNOWN_TO.`,
    };
  }
  if (offered.some((t) => t.name === id)) {
    return { kind: "problem", message: `${id} is already a type here: choose it from the list instead.` };
  }
  const reason = draft.reason.trim();
  if (reason === "" || reason.length > MAX_PROPOSAL_REASON_CHARS) {
    return { kind: "problem", message: `Say why no type fits, in at most ${MAX_PROPOSAL_REASON_CHARS} characters.` };
  }
  const ends = draft.eitherWay
    ? [...new Set([draft.sourceType, draft.targetType])].sort()
    : null;
  const input: ProposeLinkTypeInput = {
    name: id,
    label,
    from_types: ends ?? [draft.sourceType],
    to_types: ends ?? [draft.targetType],
    directed: !draft.eitherWay,
    reason,
  };
  if (draft.colour !== "") input.colour = draft.colour;
  if (draft.thickness !== "") input.thickness = Number(draft.thickness);
  return { kind: "proposal", input };
}
