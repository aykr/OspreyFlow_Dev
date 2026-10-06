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
  onRemove: () => void;
  onClear: () => void;
}

const COUNT = new Intl.NumberFormat("en-GB");

export function SelectionBar({ count, onExpand, onBranch, onRemove, onClear }: SelectionBarProps) {
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
        <button type="button" className="btn btn--quiet" onClick={onExpand}>
          Expand
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
      <button type="button" className="btn btn--quiet" onClick={onClear}>
        Clear
      </button>
    </div>
  );
}
