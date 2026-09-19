import type { Edge } from "../../../../packages/schemas/generated";
import { Popover } from "../design/primitives/Popover";

export interface EdgeInspectionOverlayProps {
  x: number;
  y: number;
  edge: Edge;
  onClose: () => void;
}

/** `docs/02_GLASS_FRONTEND.md` §1.1: "Hovering or selecting an edge opens
 * a DOM overlay anchored to Sigma's camera showing the edge's type,
 * occurrence count, interval, provenance and contributing source
 * records" — the one place per-edge decoration is genuinely easier in
 * HTML than in the WebGL layer (ADR-002's own "one honest caveat"). */
export function EdgeInspectionOverlay({ x, y, edge, onClose }: EdgeInspectionOverlayProps) {
  return (
    <Popover x={x} y={y} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 220 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong className="value">{edge.type}</strong>
          <button
            type="button"
            className="icon-btn"
            aria-label="Close edge details"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div>Occurrences: <span className="value">{edge.occurrences ?? 1}</span></div>
        {edge.interval && (
          <div className="value">
            {edge.interval.valid_from}
            {edge.interval.valid_to ? ` – ${edge.interval.valid_to}` : " – present"}
          </div>
        )}
        <div>Provenance: {edge.provenance.state}</div>
        <div>
          <div style={{ color: "var(--text-secondary)", fontSize: "var(--fs-12)" }}>Sources</div>
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {edge.provenance.sources.map((source, i) => (
              <li key={i} className="value">
                {source.document_id} · {source.locator}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Popover>
  );
}
