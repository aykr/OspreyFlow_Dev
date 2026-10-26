// The selection, shown once (ADR-097 step 1, design review item 2): a floating bar at the bottom
// centre of the canvas while anything is selected, its count the only live count of the selection
// in the page, with what can be done to all of it. Replaces the corner chip (ADR-093 step 3) and
// the toolbar's *Remove selected* and *Branch selected*. Escape clears, as on the canvas.
import { useState } from "react";

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
  /** ADR-128 decision 2: what Select what is lit did, said while its selection stands, with the
   * words "undated links are not included". Absent: the selection did not come from it. */
  litNote?: string;
  /** Gives back the selection that was there before Select what is lit, once. Offered with
   * `litNote`. */
  onUndoLit?: () => void;
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
  litNote,
  onUndoLit,
  onRemove,
  onClear,
}: SelectionBarProps) {
  const [degree, setDegree] = useState(1);
  if (count === 0) return null;
  const routesAllowed = count <= ROUTE_NODES;
  const shown = routesAllowed ? degree : 1;
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
      {litNote && (
        <span className="selection-bar__note" title={litNote}>
          {litNote}
        </span>
      )}
      {litNote && onUndoLit && (
        <button type="button" className="btn btn--quiet" onClick={onUndoLit}>
          Undo select what is lit
        </button>
      )}
      {onExpand && (
        // ADR-115 E4 (review items 2 and 5): the bar's one primary action, in brass.
        <button type="button" className="btn btn--primary" onClick={onExpand}>
          Expand
        </button>
      )}
      {onLinksAmong && count > 1 && (
        // ADR-098 Amendment 4, made to read as a sentence (the owner, 14 October 2026): *Show links*,
        // then how far — "direct", or "within 2" to "within 6" — stepped by − and +.
        <span className="selection-bar__links">
          <button
            type="button"
            className="btn btn--quiet"
            aria-label="Show links among these"
            onClick={() => onLinksAmong(shown)}
          >
            Show links
          </button>
          <span
            className="selection-bar__stepper"
            role="group"
            aria-label="Degrees of separation"
          >
            <button
              type="button"
              className="selection-bar__step"
              aria-label="Fewer degrees"
              disabled={shown <= 1}
              onClick={() => setDegree(Math.max(1, shown - 1))}
            >
              −
            </button>
            <span
              className="selection-bar__reading"
              aria-live="polite"
              title="How many links apart to look for routes among these"
            >
              {shown === 1 ? "direct" : `within ${shown}`}
            </span>
            <button
              type="button"
              className="selection-bar__step"
              aria-label="More degrees"
              disabled={!routesAllowed || shown >= MAX_DEGREE}
              title={
                routesAllowed
                  ? undefined
                  : `Routes are looked for among at most ${ROUTE_NODES} selected nodes`
              }
              onClick={() => setDegree(Math.min(MAX_DEGREE, shown + 1))}
            >
              +
            </button>
          </span>
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
      <span className="selection-bar__divider" aria-hidden="true" />
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
