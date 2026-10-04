// The selection, listed (ADR-093 step 2): when more than one node is selected the Inspector names
// each, so the analyst can see what they have chosen, go to any one, and take one out.
import type { Node } from "../../../../packages/schemas/generated";
import { displayValue } from "../search/searchOptions";

export interface SelectionListProps {
  nodes: readonly Node[];
  /** Pan the canvas to this node, keeping the selection as it is. */
  onCentre: (nodeId: string) => void;
  /** Take this node out of the selection. */
  onRemove: (nodeId: string) => void;
}

export function SelectionList({ nodes, onCentre, onRemove }: SelectionListProps) {
  if (nodes.length < 2) return null;
  return (
    <section aria-labelledby="selection-list-heading" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 id="selection-list-heading" style={{ margin: 0, fontSize: "var(--fs-13)", color: "var(--text-secondary)" }}>
        Selected ({nodes.length})
      </h3>
      <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
        {nodes.map((node) => {
          const name = displayValue(node);
          return (
            <li key={node.id} style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
              <button
                type="button"
                className="btn"
                aria-label={`Centre on ${name}`}
                onClick={() => onCentre(node.id)}
                style={{ flex: 1, textAlign: "left" }}
              >
                <span className="value">{name}</span>
                <span style={{ color: "var(--text-tertiary)" }}> · {node.type}</span>
              </button>
              <button
                type="button"
                className="btn"
                aria-label={`Remove ${name} from the selection`}
                onClick={() => onRemove(node.id)}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
