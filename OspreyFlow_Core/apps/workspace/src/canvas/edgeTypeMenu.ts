// Which edge types the radial menu offers for a node — extracted from `GlassCanvas.tsx` in round
// 12e so the wildcard rule below can be asserted without a browser.
//
// **The bug this fixes.** The filter was `et.from.includes(node.type) || et.to.includes(node.type)`.
// The ontology declares `SAME_AS` and `NOT_SAME_AS` with `from: ["*"]`, `to: ["*"]` — they connect
// any entity type to any other — and `["*"].includes("Person")` is `false`, so **every wildcard
// edge type was silently missing from the menu for every node type**. An analyst could not expand
// `SAME_AS` from the canvas at all.
//
// That is what made "Explain cluster" unreachable in a live session, and it took three rounds to
// find because each layer looked innocent on its own: `services/resolve/projection.py` collapses
// components over the *working set's* `SAME_AS` edges, a search-seeded node carries no edges until
// something expands it (REPORT-12c), and the one control that could expand them did not list them.
// Round 12d mistook the resulting `merged: 0` for a fixture defect and tabulated the edges'
// `weight` (`01_DOMAIN_MODEL.md` §6.1's load-time strength formula) against ADR-035 §C5's match
// *score*, which are different quantities; round 12e measured both and found every stored `score`
// matches §C5 exactly.
import type { EdgeTypeDef } from "../../../../packages/schemas/generated";

/** `"*"` in an ontology edge type's `from`/`to` means "any entity type" — it is a wildcard, not a
 * literal type name, and has to be read as one here. */
export const WILDCARD = "*";

function matches(endpoints: readonly string[], nodeType: string): boolean {
  return endpoints.includes(WILDCARD) || endpoints.includes(nodeType);
}

/** The edge types worth offering on a node of `nodeType`: those the ontology allows at either
 * end, with a wildcard end matching anything.
 *
 * Deliberately *not* filtered by whether this node actually has such an edge — the menu shows
 * what is possible and previews the real cardinality beside it (`08_ACCEPTANCE_SCENARIOS.md` A1,
 * wired in round 12c), so an entry reading `(0)` is informative rather than an omission. */
export function edgeTypesOfferedFor(
  edgeTypes: readonly EdgeTypeDef[],
  nodeType: string,
): EdgeTypeDef[] {
  return edgeTypes.filter(
    (et) => matches(et.from, nodeType) || matches(et.to, nodeType),
  );
}
