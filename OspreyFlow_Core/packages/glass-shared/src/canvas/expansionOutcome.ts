// What to tell the analyst when a relationship chosen from a node's menu adds nothing.
//
// Seen 3 October 2026 on the Fixture Corp case: choosing any relationship changed nothing on the
// canvas and said nothing, so it looked broken. The six Volkovs are linked to each other and all
// already drawn, so every expansion from one of them returns only what is on screen. An expansion
// that adds nothing is a result the analyst needs told, in one of two ways.

import { linkTypeName, type NamedType } from "./linkLabel";

export interface ExpansionResult {
  /** The node that was expanded; the server may return it with its neighbours. */
  rootId: string;
  /** Ids of the nodes and links the server returned. */
  nodeIds: readonly string[];
  edgeIds: readonly string[];
  /** Whether the canvas already holds a node or link, asked before the result is applied. */
  hasNode: (id: string) => boolean;
  hasEdge: (id: string) => boolean;
  /** The relationship chosen, or `null` when every kind was asked for. */
  edgeType: string | null;
  /** The ontology's relationship types, for the chosen one's display name (ADR-091). */
  edgeTypes?: readonly NamedType[];
}

/** `null` when the expansion added a node or a link, else a sentence saying why nothing changed. */
export function describeEmptyExpansion(result: ExpansionResult): string | null {
  if (result.nodeIds.some((id) => !result.hasNode(id))) return null;
  if (result.edgeIds.some((id) => !result.hasEdge(id))) return null;
  // Named as a person reads it (ADR-091), quoted so the name reads as one in the sentence.
  const name = result.edgeType === null ? null : `\u2018${linkTypeName(result.edgeType, result.edgeTypes ?? [])}\u2019`;
  const ofType = name === null ? "" : `${name} `;
  const leftNodes = result.nodeIds.filter((id) => id !== result.rootId);
  if (leftNodes.length === 0 && result.edgeIds.length === 0) {
    return `No ${ofType}links from this node.`;
  }
  const linked = name === null ? "linked to this node" : `linked by ${name}`;
  return `Nothing new: everything ${linked} is already in view.`;
}
