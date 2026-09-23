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
// `keyboard/metrics-panel.spec.ts` case (standing rule 13) while the metric/compare/hull toggles
// below, built from plain `Select`/`Toggle` with no custom key handling, do not need one — the
// same distinction `ThresholdControl.tsx`'s own docstring already draws for its native `<input>`.
import { useEffect, useState } from "react";

import { Panel } from "../design/primitives/Panel";
import { Select } from "../design/primitives/Select";
import { Toggle } from "../design/primitives/Toggle";
import type { WorkingSetGraph } from "../workingset/store";
import { fetchComputeMetric, type ComputeMetricName } from "./api";

const METRIC_OPTIONS: { value: ComputeMetricName; label: string }[] = [
  { value: "degree", label: "Degree" },
  { value: "weighted_degree", label: "Weighted degree" },
  { value: "betweenness", label: "Betweenness" },
  { value: "eigenvector", label: "Eigenvector" },
  { value: "pagerank", label: "PageRank" },
  { value: "clustering_coefficient", label: "Clustering coefficient" },
  { value: "clique_metric", label: "Clique Metric" },
];

//: The ranked list's own row cap — a working set can hold thousands of nodes; the panel is a
//: ranked-highlights view, not a second copy of the full node table (`design/primitives/Table.tsx`
//: already exists for that), so it shows the top N by the primary metric rather than paginating.
const MAX_ROWS = 20;

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
}

function nodeLabel(graph: WorkingSetGraph, nodeId: string): string {
  if (!graph.hasNode(nodeId)) return nodeId;
  const node = graph.getNodeAttribute(nodeId, "data");
  return `${node.type} · ${nodeId}`;
}

export function MetricsPanel({
  apiBaseUrl,
  bearerToken,
  investigationId,
  graph,
  onFocusNode,
  onCommunitiesChange,
}: MetricsPanelProps) {
  const [metricA, setMetricA] = useState<ComputeMetricName>("degree");
  const [metricB, setMetricB] = useState<ComputeMetricName>("betweenness");
  const [compareMode, setCompareMode] = useState(false);
  const [showHulls, setShowHulls] = useState(false);
  const [valuesA, setValuesA] = useState<Record<string, number> | null>(null);
  const [valuesB, setValuesB] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void fetchComputeMetric(apiBaseUrl, bearerToken, investigationId, metricA)
      .then((accepted) => {
        if (!cancelled) setValuesA(accepted.values ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, metricA]);

  useEffect(() => {
    if (!compareMode) {
      setValuesB(null);
      return;
    }
    let cancelled = false;
    void fetchComputeMetric(apiBaseUrl, bearerToken, investigationId, metricB)
      .then((accepted) => {
        if (!cancelled) setValuesB(accepted.values ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, metricB, compareMode]);

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

  const ranked = valuesA
    ? Object.entries(valuesA)
        .sort(([, a], [, b]) => b - a)
        .slice(0, MAX_ROWS)
    : [];

  return (
    <Panel title="Metrics" className="metrics-panel">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
        <Select
          aria-label="Primary metric"
          value={metricA}
          onChange={(e) => setMetricA(e.target.value as ComputeMetricName)}
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
            onChange={(e) => setMetricB(e.target.value as ComputeMetricName)}
          >
            {METRIC_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        )}
        <Toggle checked={showHulls} onChange={setShowHulls} label="Show community hulls" />
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
                <span>{nodeLabel(graph, nodeId)}</span>
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
    </Panel>
  );
}
