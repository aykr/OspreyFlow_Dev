// Pure rendering-boundary logic for `explain_cluster`'s response —
// `08_ACCEPTANCE_SCENARIOS.md` B10. `explain_cluster` (`services/api/working_set/service.py`, fixed in
// Stage 2) already guarantees every id in its response — `member_node_ids` and every
// `pairs[i].node_a`/`node_b` — is visible to the calling principal *today*: `member_ids` is
// narrowed to `expand`'s own principal-filtered result before anything is returned, and a `pairs`
// entry only exists when both its endpoints are in that narrowed set.
//
// What the API's own correctness cannot guarantee is what this module exists for: that this
// specific Glass session's own local `graphology` graph already holds a given member (a
// legitimately-visible node another principal added to the shared working set, not yet synced
// here), and it cannot protect against a future regression reopening the Stage 2 gap. Trusting
// either the response's own `member_node_ids` alone, or the local graph alone, would each be a
// single point of failure — `visiblePairs` requires both to agree before a pair is ever rendered,
// the same "belt and braces" reasoning `set_resolution_threshold`'s own fix used, applied one
// layer up. A pair failing either check is dropped entirely, never shown in a redacted form: a
// redacted row still asserts "an edge exists here," which is exactly the signal to avoid.
import type { WorkingSetGraph } from "../workingset/store";
import type { ClusterExplanation, PairwiseExplanation } from "../workingset/models";

export function visiblePairs(
  explanation: ClusterExplanation,
  graph: WorkingSetGraph,
): PairwiseExplanation[] {
  const visibleIds = new Set(explanation.member_node_ids);
  return explanation.pairs.filter(
    (pair) =>
      visibleIds.has(pair.node_a) &&
      visibleIds.has(pair.node_b) &&
      graph.hasNode(pair.node_a) &&
      graph.hasNode(pair.node_b),
  );
}

/**
 * The "Basis" column's own render logic, factored out so it is unit-testable without mounting a
 * component. `manually_asserted` is checked *first* — a manual edge returns its own dedicated
 * string and never falls through to a `score`-shaped path, so it cannot render as blank/missing
 * data by construction (`manual_link`'s own docstring: leaving `score`/`model_version`/
 * `comparison_vector` unset "keeps `explain`'s `manually_asserted` flag the one honest signal for
 * why is this pair linked, not a fabricated model tag" — this is that signal's own rendering).
 */
export function explanationBasis(pair: PairwiseExplanation): string {
  if (pair.manually_asserted) return "Asserted by analyst";
  const score = pair.score !== null ? pair.score.toFixed(2) : "—";
  const model = pair.model_version ?? "unknown model";
  const vector = pair.comparison_vector
    ? Object.entries(pair.comparison_vector)
        .map(([key, value]) => `${key}: ${String(value)}`)
        .join(", ")
    : null;
  return vector ? `${score} · ${model} (${vector})` : `${score} · ${model}`;
}
