import { useState } from "react";

export interface ViewActionsProps {
  nodeCount: number;
  selectedCount: number;
  onRemoveSelected: () => void;
  onClearAll: () => void;
}

/**
 * Two ways to tidy the view: remove the selected nodes, or clear everything. Clearing asks first
 * and says what it does and does not do: the records stay in the store and History can undo it.
 */
export function ViewActions({
  nodeCount,
  selectedCount,
  onRemoveSelected,
  onClearAll,
}: ViewActionsProps) {
  const [confirming, setConfirming] = useState(false);
  const total = nodeCount.toLocaleString("en-GB");
  return (
    <div
      style={{
        position: "absolute",
        top: "var(--sp-8)",
        right: "var(--sp-8)",
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: "var(--sp-4)",
      }}
    >
      <div style={{ display: "flex", gap: "var(--sp-4)" }}>
        <button
          type="button"
          className="radial-menu__item"
          disabled={selectedCount === 0}
          onClick={onRemoveSelected}
        >
          Remove selected ({selectedCount})
        </button>
        <button
          type="button"
          className="radial-menu__item"
          disabled={nodeCount === 0}
          onClick={() => setConfirming(true)}
        >
          Clear view
        </button>
      </div>
      {confirming && nodeCount > 0 && (
        <div
          role="alertdialog"
          aria-label="Clear the view"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-6)",
            padding: "var(--sp-8)",
            maxWidth: 300,
            background: "var(--surface-raised, var(--surface))",
            border: "1px solid var(--border)",
          }}
        >
          <strong className="value">
            Remove all {total} nodes from this view?
          </strong>
          <span>
            The records stay in the store. History can bring them back.
          </span>
          <button
            type="button"
            className="radial-menu__item"
            onClick={() => {
              setConfirming(false);
              onClearAll();
            }}
          >
            Clear all {total}
          </button>
          <button
            type="button"
            className="radial-menu__item"
            onClick={() => setConfirming(false)}
          >
            Keep
          </button>
        </div>
      )}
    </div>
  );
}
