// The selection, shown once (ADR-097 step 1, design review item 2): a floating bar at the bottom
// centre of the canvas while anything is selected, its count the only live count of the selection
// in the page, with what can be done to all of it. Replaces the corner chip (ADR-093 step 3) and
// the toolbar's *Remove selected* and *Branch selected*. Escape clears, as on the canvas.
import { useId, useState } from "react";

/** ADR-098 Amendment 4: the furthest the routes are looked for, and how many may be selected to
 * look past one degree — the Conduit's `LINKS_AMONG_MAX_DEGREE` and `LINKS_AMONG_ROUTE_NODES`. */
const MAX_DEGREE = 6;
const ROUTE_NODES = 8;

export interface SelectionBarProps {
  count: number;
  /** Expand every selected node. Absent: not offered. */
  onExpand?: () => void;
  /** Send the selection to a new case (ADR-084). Absent: this surface cannot branch. */
  onBranch?: () => void;
  /** ADR-098: draw the links among the selected nodes, and with a degree above 1 the routes between
   * them within it (Amendment 4). Offered for two or more. */
  onLinksAmong?: (degree: number) => void;
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
  const [degree, setDegree] = useState(1);
  const degreesName = useId();
  if (count === 0) return null;
  const routesAllowed = count <= ROUTE_NODES;
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
        <span className="selection-bar__links">
          <span
            role="radiogroup"
            aria-label="Degrees of separation"
            className="selection-bar__degrees"
            title={
              routesAllowed
                ? "How many links apart to look for routes among these"
                : `Routes are looked for among at most ${ROUTE_NODES} selected nodes`
            }
          >
            {Array.from({ length: MAX_DEGREE }, (_, i) => i + 1).map((d) => (
              <label key={d} className="selection-bar__degree">
                <input
                  type="radio"
                  name={degreesName}
                  value={d}
                  aria-label={d === 1 ? "Direct links" : `Within ${d} degrees`}
                  checked={(routesAllowed ? degree : 1) === d}
                  disabled={!routesAllowed && d > 1}
                  onChange={() => setDegree(d)}
                />
                <span aria-hidden="true">{d}</span>
              </label>
            ))}
          </span>
          <button
            type="button"
            className="btn btn--quiet"
            onClick={() => onLinksAmong(routesAllowed ? degree : 1)}
          >
            Show links among these
          </button>
        </span>
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
      <button
        type="button"
        className="btn btn--quiet"
        onClick={onClear}
        aria-keyshortcuts="Escape"
      >
        Clear{" "}
        <kbd className="key-cap" aria-hidden="true">
          Esc
        </kbd>
      </button>
    </div>
  );
}
