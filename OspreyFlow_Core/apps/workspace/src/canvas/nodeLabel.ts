// How a node's label is drawn (ADR-097 step 2, design review item 9): at `--fs-12`, in mono when it
// is a literal value (an identifier, a normalised value, an id: DESIGN.md §9 exception 3), cut in the
// middle at 24 characters so both ends of an address or account stay readable, and placed so it
// never runs past the canvas's edge. The full text stays in the Inspector and the hover box's title.
import type { Node } from "../../../../packages/schemas/generated";
import type { LabelChoices } from "./labelChoices";

export const NODE_LABEL_MAX_CHARS = 24;
/** `--fs-12`; the canvas cannot read CSS variables, so the value is mirrored here. */
export const NODE_LABEL_SIZE = 12;
/** `--ui` and `--mono` from `tokens.css`, mirrored for the canvas. */
export const NODE_LABEL_FONT = "'Atkinson Hyperlegible Next', 'Atkinson Hyperlegible', system-ui, sans-serif";
export const NODE_LABEL_MONO_FONT = "'IBM Plex Mono', ui-monospace, monospace";

/** `text`, or its first and last characters with an ellipsis between, `max` characters in all. */
export function middleTruncate(text: string, max = NODE_LABEL_MAX_CHARS): string {
  const chars = Array.from(text);
  if (chars.length <= max) return text;
  const keep = max - 1;
  const head = Math.ceil(keep / 2);
  const tail = keep - head;
  return `${chars.slice(0, head).join("")}…${chars.slice(chars.length - tail).join("")}`;
}

/** Whether the node's label is a literal value: the analyst's chosen property when it is one of the
 * type's identifiers, otherwise whether the default label is the normalised value or the id (a
 * person's family and given names are not). */
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
  return typeof properties["family_name"] !== "string" || properties["family_name"] === "";
}

/** Where a label starts: right of the node when it fits inside the canvas, else left of it, and
 * never before the left edge. */
export function labelStartX(at: { x: number; size: number; textWidth: number; canvasWidth: number }): number {
  const GAP = 3;
  const right = at.x + at.size + GAP;
  if (right + at.textWidth <= at.canvasWidth) return right;
  return Math.max(0, at.x - at.size - GAP - at.textWidth);
}
