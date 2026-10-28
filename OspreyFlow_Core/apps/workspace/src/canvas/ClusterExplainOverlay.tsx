import { Popover } from "../design/primitives/Popover";
import { Table, type TableColumn } from "../design/primitives/Table";
import { explanationBasis, visiblePairs } from "../resolution/explainView";
import type { ClusterExplanation, PairwiseExplanation } from "../workingset/models";
import type { WorkingSetGraph } from "../workingset/store";
import { nodeLabel } from "./nodeAttributes";

export interface ClusterExplainOverlayProps {
  x: number;
  y: number;
  explanation: ClusterExplanation;
  graph: WorkingSetGraph;
  onClose: () => void;
}

function labelFor(graph: WorkingSetGraph, nodeId: string): string {
  // `visiblePairs` already guarantees `graph.hasNode(nodeId)` for every row this renders — the
  // fallback below is unreachable in practice, not a case this component needs to handle
  // gracefully, but `getNodeAttribute` has no narrower return type to lean on instead.
  return graph.hasNode(nodeId) ? nodeLabel(graph.getNodeAttribute(nodeId, "data")) : nodeId;
}

/** `spec/02_GLASS_FRONTEND.md`'s resolution-cluster section (added alongside this component):
 * a transient `Popover` anchored to the triggering canvas position (ADR-002's "one honest caveat")
 * — not a new Inspector tab or the Dossier (B6/Stage 4's own,
 * larger, permanent surface). `03_CONDUIT_MIDDLEWARE.md` §3.5 / B10: "per-comparison match
 * weights, not just the total." */
export function ClusterExplainOverlay({ x, y, explanation, graph, onClose }: ClusterExplainOverlayProps) {
  const columns: TableColumn<PairwiseExplanation>[] = [
    { key: "node_a", header: "Node A", render: (p) => labelFor(graph, p.node_a) },
    { key: "node_b", header: "Node B", render: (p) => labelFor(graph, p.node_b) },
    { key: "edge_type", header: "Type", render: (p) => p.edge_type },
    { key: "basis", header: "Basis", render: explanationBasis },
    {
      key: "meets_threshold",
      header: "Meets τ",
      // Never colour alone — text reads correctly even to an analyst who can't distinguish the
      // colours the axe-core contrast floor is separately checked against.
      render: (p) => (p.meets_threshold ? "Yes" : "No"),
    },
  ];

  return (
    <Popover x={x} y={y} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 360 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong className="value">Cluster explanation</strong>
          <button
            type="button"
            className="icon-btn"
            aria-label="Close cluster explanation"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <Table
          columns={columns}
          rows={visiblePairs(explanation, graph)}
          getRowId={(p) => `${p.node_a}-${p.node_b}-${p.edge_type}`}
        />
      </div>
    </Popover>
  );
}
