// Graph facts in a question's answer (ADR-129 decision 1). The model cites a fact as `[G-n]`; the
// Conduit returns, for each one it cited, the node and link ids it stands for, and this is the only
// place the Glass maps a number to ids (from the payload, never from the text). A number the
// payload does not hold is left as the plain words it is.

/** `services/api/questions.py`'s `GraphCitation`. */
export interface GraphCitation {
  number: number;
  label: string;
  node_ids: string[];
  link_ids: string[];
}

export type AnswerPart =
  | { kind: "text"; text: string }
  | { kind: "fact"; citation: GraphCitation };

const MARKER = /\[G-(\d+)\]/g;

/** The answer in order, each `[G-n]` that the payload holds as a fact and the rest as text. Every
 * citation appears once: a fact the words do not mark is in `unmarked`, for a row after the answer. */
export function splitAnswer(
  answer: string,
  citations: readonly GraphCitation[],
): { parts: AnswerPart[]; unmarked: GraphCitation[] } {
  const held = new Map(citations.map((c) => [c.number, c]));
  const parts: AnswerPart[] = [];
  const placed = new Set<number>();
  let from = 0;
  for (const match of answer.matchAll(MARKER)) {
    const citation = held.get(Number(match[1]));
    if (!citation || placed.has(citation.number)) continue;
    const at = match.index ?? 0;
    if (at > from) parts.push({ kind: "text", text: answer.slice(from, at) });
    parts.push({ kind: "fact", citation });
    placed.add(citation.number);
    from = at + match[0].length;
  }
  if (from < answer.length) parts.push({ kind: "text", text: answer.slice(from) });
  return { parts, unmarked: citations.filter((c) => !placed.has(c.number)) };
}

/** The part of `GlassCanvasHandle` that selecting a fact uses. */
export interface FactCanvas {
  highlightNodes: (nodeIds: readonly string[]) => void;
  selectLink: (edgeId: string | null) => void;
  centreOn: (nodeId: string) => void;
}

/** Selects what a fact stands for and brings it into view. A link fact selects the link: the canvas
 * ends a link selection when nodes are chosen, so the link and its two ends cannot both be
 * selected, and the link is what the fact is. Either way the camera goes to its first end. A fact
 * whose ids are not on the canvas leaves the selection as it was. */
export function bringFactIntoView(canvas: FactCanvas, citation: GraphCitation): void {
  const [link] = citation.link_ids;
  if (link !== undefined) canvas.selectLink(link);
  else canvas.highlightNodes(citation.node_ids);
  const [first] = citation.node_ids;
  if (first !== undefined) canvas.centreOn(first);
}
