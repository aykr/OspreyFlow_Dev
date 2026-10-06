import { useState } from "react";

export interface ViewActionsProps {
  nodeCount: number;
  onClearAll: () => void;
  /** A link is selected, so it can be hidden from this view. */
  selectedLink?: boolean;
  /** How many links are hidden in this browser tab. */
  hiddenLinkCount?: number;
  onHideLink?: () => void;
  onShowHiddenLinks?: () => void;
  /** ADR-094: add files to the case, standing alone. Absent: not offered. */
  onAddFiles?: () => void;
}

/**
 * Tidying the view: hide a selected link, show hidden links again, or clear everything. Clearing
 * asks first and says what it does and does not do: the records stay in the store and History can
 * undo it. What is done to selected nodes is on the selection bar (ADR-097 step 1).
 */
export function ViewActions({
  nodeCount,
  onClearAll,
  selectedLink = false,
  hiddenLinkCount = 0,
  onHideLink,
  onShowHiddenLinks,
  onAddFiles,
}: ViewActionsProps) {
  const [confirming, setConfirming] = useState(false);
  const total = nodeCount.toLocaleString("en-GB");
  return (
    <div
      style={{
        position: "absolute",
        // Above the renderer's canvas layers, which are added to the same container after this
        // and would otherwise take every click meant for these buttons.
        zIndex: 10,
        top: "var(--sp-8)",
        right: "var(--sp-8)",
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: "var(--sp-4)",
      }}
    >
      <div style={{ display: "flex", gap: "var(--sp-4)" }}>
        {selectedLink && (
          <button type="button" className="radial-menu__item" onClick={onHideLink}>
            Hide selected link
          </button>
        )}
        {hiddenLinkCount > 0 && (
          <button type="button" className="radial-menu__item" onClick={onShowHiddenLinks}>
            Show hidden links ({hiddenLinkCount})
          </button>
        )}
        <button
          type="button"
          className="radial-menu__item"
          disabled={nodeCount === 0}
          onClick={() => setConfirming(true)}
        >
          Clear view
        </button>
      </div>
      {onAddFiles && (
        // A row of its own, so the row above keeps its place (buttons there are right-aligned).
        <button type="button" className="radial-menu__item" onClick={onAddFiles}>
          Add files
        </button>
      )}
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
