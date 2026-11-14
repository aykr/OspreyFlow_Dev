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

/** `services/api/questions.py`'s `SearchCitation` (ADR-129 Amendment 5): an `[S-n]`, a record the
 * case's search found under *Whole case*, with the ids it stands for (a merged entity's visible
 * members) and the Conduit's words for why it was found. */
export interface SearchCitation {
  number: number;
  label: string;
  name: string;
  type: string;
  why: string;
  node_ids: string[];
}

export type AnswerPart =
  | { kind: "text"; text: string }
  | { kind: "fact"; citation: GraphCitation }
  | { kind: "source"; citation: SearchCitation };

const MARKER = /\[([GS])-(\d+)\]/g;

/** The answer in order, each `[G-n]` or `[S-n]` that the payload holds (every occurrence of a
 * repeated marker is one) and the rest as text. A citation the words do not mark is in `unmarked`
 * or `unmarkedSources`, for a row after the answer, so every citation is reachable. */
export function splitAnswer(
  answer: string,
  citations: readonly GraphCitation[],
  sources: readonly SearchCitation[] = [],
): { parts: AnswerPart[]; unmarked: GraphCitation[]; unmarkedSources: SearchCitation[] } {
  const facts = new Map(citations.map((c) => [c.number, c]));
  const found = new Map(sources.map((c) => [c.number, c]));
  const parts: AnswerPart[] = [];
  const placed = new Set<number>();
  const placedSources = new Set<number>();
  let from = 0;
  for (const match of answer.matchAll(MARKER)) {
    const number = Number(match[2]);
    const fact = match[1] === "G" ? facts.get(number) : undefined;
    const source = match[1] === "S" ? found.get(number) : undefined;
    if (!fact && !source) continue;
    const at = match.index ?? 0;
    if (at > from) parts.push({ kind: "text", text: answer.slice(from, at) });
    if (fact) {
      parts.push({ kind: "fact", citation: fact });
      placed.add(number);
    } else if (source) {
      parts.push({ kind: "source", citation: source });
      placedSources.add(number);
    }
    from = at + match[0].length;
  }
  if (from < answer.length) parts.push({ kind: "text", text: answer.slice(from) });
  return {
    parts,
    unmarked: citations.filter((c) => !placed.has(c.number)),
    unmarkedSources: sources.filter((c) => !placedSources.has(c.number)),
  };
}

/** An `[S-n]` as the canvas selects it: its records, and no link. */
export function sourceAsFact(source: SearchCitation): GraphCitation {
  return { number: source.number, label: source.label, node_ids: source.node_ids, link_ids: [] };
}

/** The part of `GlassCanvasHandle` that selecting a fact uses. */
export interface FactCanvas {
  highlightNodes: (nodeIds: readonly string[]) => void;
  selectLink: (edgeId: string | null) => void;
  centreOn: (nodeId: string) => void;
  /** Whether the canvas draws a link now: `true` drawn, `false` hidden, `null` not in the view. */
  linkDrawn: (edgeId: string) => boolean | null;
}

/** Selects what a fact stands for and brings it into view. A fact that stands for exactly one link
 * that is drawn selects the link: the canvas ends a link selection when nodes are chosen, so the
 * link and its two ends cannot both be selected, and the link is what the fact is. A fact whose
 * link is not drawn, or that stands for several links (only one link can be selected), selects its
 * nodes instead. Either way the camera goes to its first end. A fact none of whose ids is on the
 * canvas leaves the selection as it was. */
export function bringFactIntoView(canvas: FactCanvas, citation: GraphCitation): void {
  const [link] = citation.link_ids;
  if (citation.link_ids.length === 1 && link !== undefined && canvas.linkDrawn(link) === true) {
    canvas.selectLink(link);
  } else if (citation.node_ids.length > 0) {
    canvas.highlightNodes(citation.node_ids);
  }
  const [first] = citation.node_ids;
  if (first !== undefined) canvas.centreOn(first);
}
