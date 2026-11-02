// The social-network filters (ADR-088), as the Wynyard Enron walk-through showed them: a
// relationship-strength floor that thins the picture to its strongly linked core, and a metric
// threshold that keeps, say, the most cliquish people. Both dim and never remove (spec 02 §2
// rule 2), so the analyst's spatial memory of the network survives the filter, and sliding back
// brightens everything again. A filter is a way of looking: it belongs to the view, nothing is
// stored. The rule is pure so it can be tested without a screen; `App.tsx` feeds it the graph.
import type { ComputeMetricName } from "./api";

/** ADR-139 decision 6: connection strength and shared-attribute rarity join the metrics a filter
 * judges by. Strength is a link's (a node takes its strongest link's), rarity a pair's (a node takes
 * its highest with another of its kind in view); both are worked out in the store as the reader. */
export type StrengthMetricName = "connection_strength" | "shared_attribute_rarity";
export type FilterMetricName = ComputeMetricName | StrengthMetricName;

export function isStrengthMetric(metric: FilterMetricName | null): metric is StrengthMetricName {
  return metric === "connection_strength" || metric === "shared_attribute_rarity";
}

export interface MetricFilter {
  /** A link whose weight is below this is dimmed; 0 dims nothing. */
  strengthFloor: number;
  /** The metric nodes are judged by, or `null` for none. */
  metric: FilterMetricName | null;
  /** Nodes whose value is below this are dimmed; `null` while no threshold is set. */
  threshold: number | null;
  /** The metric's values by node id, once fetched; `null` dims nothing by metric. */
  values: Record<string, number> | null;
  /** A link metric's values by link id (connection strength, ADR-139): a link below the threshold
   * is dimmed as well as a node none of whose links reaches it. Absent for a node metric. */
  edgeValues?: Record<string, number> | null;
}

export const NO_FILTER: MetricFilter = {
  strengthFloor: 0,
  metric: null,
  threshold: null,
  values: null,
  edgeValues: null,
};

export interface FilterEdge {
  id: string;
  source: string;
  target: string;
  weight: number;
}

export interface FilterDimming {
  dimmedNodeIds: ReadonlySet<string>;
  dimmedEdgeIds: ReadonlySet<string>;
}

export function filterDimming(
  nodeIds: readonly string[],
  edges: readonly FilterEdge[],
  filter: MetricFilter,
): FilterDimming {
  const dimmedEdgeIds = new Set<string>();
  const dimmedNodeIds = new Set<string>();

  if (filter.strengthFloor > 0) {
    // A node with links keeps its brightness only while at least one of them is strong enough.
    const linked = new Set<string>();
    const strong = new Set<string>();
    for (const edge of edges) {
      linked.add(edge.source);
      linked.add(edge.target);
      if (edge.weight < filter.strengthFloor) dimmedEdgeIds.add(edge.id);
      else {
        strong.add(edge.source);
        strong.add(edge.target);
      }
    }
    for (const id of nodeIds) if (linked.has(id) && !strong.has(id)) dimmedNodeIds.add(id);
  }

  if (filter.metric !== null && filter.threshold !== null && filter.values !== null) {
    for (const id of nodeIds) {
      const value = filter.values[id];
      if (value === undefined || value < filter.threshold) dimmedNodeIds.add(id);
    }
    const edgeValues = filter.edgeValues;
    if (edgeValues) {
      for (const edge of edges) {
        const value = edgeValues[edge.id];
        if (value === undefined || value < filter.threshold) dimmedEdgeIds.add(edge.id);
      }
    }
  }

  return { dimmedNodeIds, dimmedEdgeIds };
}

/** The smallest and largest value a metric took, for the threshold slider's ends. */
export function valueRange(values: Record<string, number> | null): { min: number; max: number } {
  const list = values ? Object.values(values) : [];
  if (list.length === 0) return { min: 0, max: 1 };
  return { min: Math.min(...list), max: Math.max(...list) };
}
