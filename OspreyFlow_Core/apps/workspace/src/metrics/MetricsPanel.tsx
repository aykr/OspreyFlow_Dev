// The metrics panel: "Metrics panel with two-metric comparison;
// size encoding; community hull overlay." `ComputePort`'s first real Glass caller (Phase 7 Stage
// 3), talking to `services/api/compute_routes.py` via `metrics/api.ts`.
//
// **"Two-metric comparison," a spec-silent detail filled and disclosed rather than guessed
// silently.** `02_GLASS_FRONTEND.md` names the feature but not its exact
// interaction shape. Read here as: two independent metric selectors (A, always shown and used to
// rank the list; B, shown as a second column only while "Compare" is on) — the simplest reading
// consistent with both the bullet's own wording and a11y's own "a dense two-metric comparison"
// framing for this stage's own showcase requirement.
//
// **Row activation is real canvas-touching logic, not a native-only interaction** — unlike
// `resolution/ThresholdControl.tsx`'s own slider, selecting a row calls `GlassCanvas`'s own
// `focusOnNode` (a camera pan), which is why this panel's row button gets a
// `keyboard/metrics-panel.spec.ts` case (a keyboard-reachability proof) while the metric/compare/hull toggles
// below, built from plain `Select`/`Toggle` with no custom key handling, do not need one — the
// same distinction `ThresholdControl.tsx`'s own docstring already draws for its native `<input>`.
import { useEffect, useState } from "react";

import { nodeLabel } from "../canvas/nodeAttributes";
import { AccordionSection } from "../design/primitives/AccordionSection";
import { Panel } from "../design/primitives/Panel";
import { Select } from "../design/primitives/Select";
import { Toggle } from "../design/primitives/Toggle";
import { Slider } from "../design/primitives/Slider";
import { NO_FILTER, valueRange, type FilterMetricName, type MetricFilter } from "./filters";
import type { WorkingSetGraph } from "../workingset/store";
import { fetchComputeMetric } from "./api";
import { fetchConnectionStrengths, fetchRarity, type RarityScope } from "../strength/api";
import { strengthValues } from "../strength/words";

const METRIC_OPTIONS: { value: FilterMetricName; label: string }[] = [
  { value: "degree", label: "Degree" },
  { value: "weighted_degree", label: "Weighted degree" },
  { value: "betweenness", label: "Betweenness" },
  { value: "eigenvector", label: "Eigenvector" },
  { value: "pagerank", label: "PageRank" },
  { value: "clustering_coefficient", label: "Clustering coefficient" },
  { value: "clique_metric", label: "Clique Metric" },
  // ADR-139 decision 6: worked out in the store over what the reader may see.
  { value: "connection_strength", label: "Connection strength" },
  { value: "shared_attribute_rarity", label: "Shared-attribute rarity" },
];

interface FetchedValues {
  values: Record<string, number> | null;
  edgeValues: Record<string, number> | null;
}

/** A metric's values by node (and, for connection strength, by link): the compute route for the
 * network metrics, the strength and rarity routes for ADR-139's two. */
async function fetchMetricValues(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  graph: WorkingSetGraph,
  metric: FilterMetricName,
  rarityScope: RarityScope,
): Promise<FetchedValues> {
  if (metric === "connection_strength") {
    const found = await fetchConnectionStrengths(apiBaseUrl, bearerToken, investigationId);
    const { nodes, edges } = strengthValues(found.links, (id) =>
      graph.hasEdge(id) ? [graph.source(id), graph.target(id)] : null,
    );
    return { values: nodes, edgeValues: edges };
  }
  if (metric === "shared_attribute_rarity") {
    const found = await fetchRarity(apiBaseUrl, bearerToken, investigationId, rarityScope);
    return { values: found.node_values, edgeValues: null };
  }
  const accepted = await fetchComputeMetric(apiBaseUrl, bearerToken, investigationId, metric);
  return { values: accepted.values ?? null, edgeValues: null };
}

//: The ranked list's own row cap — a working set can hold thousands of nodes; the panel is a
//: ranked-highlights view, not a second copy of the full node table (`design/primitives/Table.tsx`
//: already exists for that), so it shows the top N by the primary metric rather than paginating.
const MAX_ROWS = 20;

type Section = "ranking" | "communities" | "filter";


export interface MetricsPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  graph: WorkingSetGraph;
  onFocusNode: (nodeId: string) => void;
  /** Fires with the latest `communities` result whenever the hull toggle is on and a fetch
   * completes, and with `null` when the toggle turns off — `App.tsx` is what turns this into
   * `GlassCanvas`'s own `communityHulls` prop (`metrics/hulls.ts`'s `computeCommunityHulls`),
   * keeping this panel free of any Sigma/camera dependency of its own. */
  onCommunitiesChange?: (communities: Record<string, string> | null) => void;
  /** The social-network filters (ADR-088), each time one changes; `App.tsx` turns them into
   * dimming on the canvas with `filters.ts`. Omitted, the Filter section still works but dims
   * nothing. */
  onFilterChange?: (filter: MetricFilter) => void;
}

/** A row names its node as the canvas labels it (8 October 2026: it showed the node's id, so the
 * ranking read "Location · 01M46CSD…" where the canvas said "Yard E"). */
function rowLabel(graph: WorkingSetGraph, nodeId: string): string {
  if (!graph.hasNode(nodeId)) return nodeId;
  const node = graph.getNodeAttribute(nodeId, "data");
  return `${node.type} · ${nodeLabel(node)}`;
}

export function MetricsPanel({
  apiBaseUrl,
  bearerToken,
  investigationId,
  graph,
  onFocusNode,
  onCommunitiesChange,
  onFilterChange,
}: MetricsPanelProps) {
  const [metricA, setMetricA] = useState<FilterMetricName>("degree");
  const [metricB, setMetricB] = useState<FilterMetricName>("betweenness");
  // ADR-139 decision 4: rarity per dataset (the client's own) or across the case's datasets.
  const [rarityScope, setRarityScope] = useState<RarityScope>("dataset");
  const [compareMode, setCompareMode] = useState(false);
  const [showHulls, setShowHulls] = useState(false);
  const [valuesA, setValuesA] = useState<Record<string, number> | null>(null);
  const [valuesB, setValuesB] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);
  // ADR-096 (replacing ADR-070's closed strip, one at a time): the panel opens on its preview, the
  // ranking, and the other sections fold; any number may be open. The ranking is kept when its
  // section is closed again.
  const [openSections, setOpenSections] = useState<ReadonlySet<Section>>(() => new Set(["ranking"]));
  // ADR-088: the filters belong to the view, so they live here and nowhere else.
  const [filter, setFilter] = useState<MetricFilter>(NO_FILTER);
  const updateFilter = (change: Partial<MetricFilter>) => {
    setFilter((current) => {
      const next = { ...current, ...change };
      onFilterChange?.(next);
      return next;
    });
  };
  const [rankingWanted, setRankingWanted] = useState(true);
  const toggleSection = (section: Section) => {
    setOpenSections((current) => {
      const next = new Set(current);
      if (next.has(section)) next.delete(section);
      else next.add(section);
      return next;
    });
    if (section === "ranking") setRankingWanted(true);
  };

  useEffect(() => {
    if (!rankingWanted) return;
    let cancelled = false;
    setError(null);
    void fetchMetricValues(apiBaseUrl, bearerToken, investigationId, graph, metricA, rarityScope)
      .then((fetched) => {
        if (!cancelled) setValuesA(fetched.values);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, bearerToken, investigationId, metricA, rankingWanted, rarityScope]);

  useEffect(() => {
    if (!compareMode || !rankingWanted) {
      setValuesB(null);
      return;
    }
    let cancelled = false;
    void fetchMetricValues(apiBaseUrl, bearerToken, investigationId, graph, metricB, rarityScope)
      .then((fetched) => {
        if (!cancelled) setValuesB(fetched.values);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, bearerToken, investigationId, metricB, compareMode, rankingWanted, rarityScope]);

  useEffect(() => {
    if (!showHulls) {
      onCommunitiesChange?.(null);
      return;
    }
    let cancelled = false;
    void fetchComputeMetric(apiBaseUrl, bearerToken, investigationId, "communities")
      .then((accepted) => {
        if (!cancelled) onCommunitiesChange?.(accepted.communities ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, bearerToken, investigationId, showHulls]);

  // The chosen filter metric's values, fetched when the metric is chosen and dropped with it.
  useEffect(() => {
    if (filter.metric === null) return;
    let cancelled = false;
    const metric = filter.metric;
    void fetchMetricValues(apiBaseUrl, bearerToken, investigationId, graph, metric, rarityScope)
      .then((fetched) => {
        if (cancelled) return;
        const values = fetched.values;
        const range = valueRange(values);
        setFilter((current) => {
          if (current.metric !== metric) return current;
          const next = {
            ...current,
            values,
            edgeValues: fetched.edgeValues,
            threshold: current.threshold ?? range.min,
          };
          onFilterChange?.(next);
          return next;
        });
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, bearerToken, investigationId, filter.metric, rarityScope]);
  const range = valueRange(filter.values);
  const step = Math.max((range.max - range.min) / 100, 0.001);

  const ranked = valuesA
    ? Object.entries(valuesA)
        .sort(([, a], [, b]) => b - a)
        .slice(0, MAX_ROWS)
    : [];

  return (
    <Panel title="Metrics" className="metrics-panel">
      <div style={{ display: "flex", flexDirection: "column" }}>
        <AccordionSection title="Ranking" open={openSections.has("ranking")} onToggle={() => toggleSection("ranking")}>
        {openSections.has("ranking") && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)" }}>
            <Select
              aria-label="Primary metric"
              value={metricA}
              onChange={(e) => setMetricA(e.target.value as FilterMetricName)}
            >
              {METRIC_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
            <Toggle checked={compareMode} onChange={setCompareMode} label="Compare a second metric" />
            {compareMode && (
              <Select
                aria-label="Comparison metric"
                value={metricB}
                onChange={(e) => setMetricB(e.target.value as FilterMetricName)}
              >
                {METRIC_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            )}
            {error && <p style={{ color: "var(--error)" }}>{error}</p>}
            <ul
              role="list"
              aria-label="Ranked nodes"
              style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
            >
              {ranked.map(([nodeId, value]) => (
                <li key={nodeId}>
                  <button
                    type="button"
                    className="metrics-panel__row"
                    style={{
                      width: "100%",
                      display: "flex",
                      justifyContent: "space-between",
                      gap: "var(--sp-8)",
                    }}
                    onClick={() => onFocusNode(nodeId)}
                  >
                    <span>{rowLabel(graph, nodeId)}</span>
                    <span className="value">
                      {value.toFixed(3)}
                      {compareMode && valuesB && valuesB[nodeId] !== undefined
                        ? ` / ${(valuesB[nodeId] as number).toFixed(3)}`
                        : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        </AccordionSection>
        <AccordionSection
          title="Community detection"
          open={openSections.has("communities")}
          onToggle={() => toggleSection("communities")}
        >
        {openSections.has("communities") && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)" }}>
            <Toggle checked={showHulls} onChange={setShowHulls} label="Show community hulls" />
            {error && <p style={{ color: "var(--error)" }}>{error}</p>}
          </div>
        )}
        </AccordionSection>
        <AccordionSection title="Filter" open={openSections.has("filter")} onToggle={() => toggleSection("filter")}>
        {openSections.has("filter") && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)" }}>
            <label style={{ display: "grid", gap: "var(--sp-4)" }}>
              <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>
                Relationship strength at least: {filter.strengthFloor.toFixed(2)}
              </span>
              <Slider
                aria-label="Relationship strength at least"
                min={0}
                max={1}
                step={0.05}
                value={filter.strengthFloor}
                onChange={(strengthFloor) => updateFilter({ strengthFloor })}
              />
            </label>
            <Select
              aria-label="Filter by metric"
              value={filter.metric ?? ""}
              onChange={(e) => {
                const metric = (e.target.value || null) as FilterMetricName | null;
                updateFilter({ metric, values: null, edgeValues: null, threshold: null });
              }}
            >
              <option value="">No metric filter</option>
              {METRIC_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
            {filter.metric === "shared_attribute_rarity" && (
              <Select
                aria-label="Rarity worked out"
                value={rarityScope}
                onChange={(e) => {
                  setRarityScope(e.target.value as RarityScope);
                  updateFilter({ values: null, edgeValues: null, threshold: null });
                }}
              >
                <option value="dataset">Per dataset</option>
                <option value="case">Across the case's datasets</option>
              </Select>
            )}
            {(filter.metric === "connection_strength" || filter.metric === "shared_attribute_rarity") && (
              <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                {filter.metric === "connection_strength"
                  ? "Each link's stored strength with the influencers in the legend; a node takes its strongest link."
                  : "How rare what two people share is, over what you may see; a node takes its rarest pairing."}
              </p>
            )}
            {filter.metric !== null && filter.values !== null && (
              <label style={{ display: "grid", gap: "var(--sp-4)" }}>
                <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>
                  Metric value at least: {(filter.threshold ?? range.min).toFixed(3)}
                </span>
                <Slider
                  aria-label="Metric value at least"
                  min={range.min}
                  max={range.max}
                  step={step}
                  value={filter.threshold ?? range.min}
                  onChange={(threshold) => updateFilter({ threshold })}
                />
              </label>
            )}
            {(filter.strengthFloor > 0 || filter.metric !== null) && (
              <button type="button" className="btn" onClick={() => updateFilter(NO_FILTER)}>
                Clear filters
              </button>
            )}
            <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
              Filters dim, they never remove: what falls below stays in place, faint, until the filter is
              cleared. Nothing is stored.
            </p>
            {error && <p style={{ color: "var(--error)" }}>{error}</p>}
          </div>
        )}
        </AccordionSection>
      </div>
    </Panel>
  );
}
