// How a node's label is drawn (ADR-097 step 2, design review item 9; DESIGN.md v0.3 §5a, ADR-115
// decision 9): at 11px, in mono when it is a literal value (an identifier, a normalised value, an id:
// DESIGN.md §9 exception 3), and over 28 characters cut to its first 19 and last 4 so both ends of an
// address or account stay readable; placed so it never runs past the canvas's edge (`labelStyle.ts`). The full text stays in the Inspector and the hover box's title.
import type { Node } from "../../../../packages/schemas/generated";
import type { LabelChoices } from "./labelChoices";

export const NODE_LABEL_MAX_CHARS = 28;
const KEEP_HEAD = 19;
const KEEP_TAIL = 4;
/** `--fs-11`; the canvas cannot read CSS variables, so the value is mirrored here. */
export const NODE_LABEL_SIZE = 11;
/** `--ui` and `--mono` from `tokens.css`, mirrored for the canvas. */
export const NODE_LABEL_FONT = "'Atkinson Hyperlegible Next', 'Atkinson Hyperlegible', system-ui, sans-serif";
export const NODE_LABEL_MONO_FONT = "'IBM Plex Mono', ui-monospace, monospace";

/** `text` when it is 28 characters or fewer; otherwise its first 19 and last 4, an ellipsis between. */
export function middleTruncate(text: string, max = NODE_LABEL_MAX_CHARS): string {
  const chars = Array.from(text);
  if (chars.length <= max) return text;
  return `${chars.slice(0, KEEP_HEAD).join("")}…${chars.slice(chars.length - KEEP_TAIL).join("")}`;
}

/** Whether the node's label is a literal value: the analyst's chosen property when it is one of the
 * type's identifiers, otherwise whether the default label is the normalised value or the id (a
 * person's names, a thing's name and a document's title are not). */
export function labelIsLiteral(
  node: Node,
  identifiersOf: (type: string) => readonly string[],
  choices: LabelChoices,
): boolean {
  const properties = (node.properties ?? {}) as Record<string, unknown>;
  const chosen = choices[node.type];
  if (chosen !== undefined && properties[chosen] !== undefined && properties[chosen] !== "") {
    return identifiersOf(node.type).includes(chosen);
  }
  const has = (key: string) => typeof properties[key] === "string" && properties[key] !== "";
  // A person's names, a thing's name or a document's title are words, not literal values.
  return !(has("family_name") || has("name") || has("title"));
}
