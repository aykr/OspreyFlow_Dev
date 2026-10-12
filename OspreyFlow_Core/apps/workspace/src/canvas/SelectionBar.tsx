// The selection, shown once (ADR-097 step 1, design review item 2): a floating bar at the bottom
// centre of the canvas while anything is selected, its count the only live count of the selection
// in the page, with what can be done to all of it. Replaces the corner chip (ADR-093 step 3) and
// the toolbar's *Remove selected* and *Branch selected*. Escape clears, as on the canvas.
export interface SelectionBarProps {
  count: number;
  /** Expand every selected node. Absent: not offered. */
  onExpand?: () => void;
  /** Send the selection to a new case (ADR-084). Absent: this surface cannot branch. */
  onBranch?: () => void;
  /** ADR-098: draw the links among the selected nodes. Offered for two or more. */
  onLinksAmong?: () => void;
  /** ADR-098 decision 4: branch the selection and ask the model about its Documents. Offered while
   * the selection holds at least one Document (`documentCount`). */
  onAsk?: () => void;
  documentCount?: number;
  onRemove: () => void;
  onClear: () => void;
}

const COUNT = new Intl.NumberFormat("en-GB");

export function SelectionBar({
  count,
  onExpand,
  onBranch,
  onLinksAmong,
  onAsk,
  documentCount = 0,
  onRemove,
  onClear,
}: SelectionBarProps) {
  if (count === 0) return null;
  return (
    <div
      role="toolbar"
      aria-label="Selection"
      className="selection-bar"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          onClear();
        }
      }}
    >
      <span className="selection-bar__count" role="status">
        {COUNT.format(count)} selected
      </span>
      {onExpand && (
        // ADR-115 E4 (review items 2 and 5): the bar's one primary action, in brass.
        <button type="button" className="btn btn--primary" onClick={onExpand}>
          Expand
        </button>
      )}
      {onLinksAmong && count > 1 && (
        <button type="button" className="btn btn--quiet" onClick={onLinksAmong}>
          Show links among these
        </button>
      )}
      {onAsk && documentCount > 0 && (
        <button type="button" className="btn btn--quiet" onClick={onAsk}>
          Ask the model about these…
        </button>
      )}
      {onBranch && (
        <button type="button" className="btn btn--quiet" onClick={onBranch}>
          Branch to a new case
        </button>
      )}
      <button type="button" className="btn btn--quiet" onClick={onRemove}>
        Remove from view
      </button>
      <button type="button" className="btn btn--quiet" onClick={onClear} aria-keyshortcuts="Escape">
        Clear <kbd className="key-cap" aria-hidden="true">Esc</kbd>
      </button>
    </div>
  );
}
