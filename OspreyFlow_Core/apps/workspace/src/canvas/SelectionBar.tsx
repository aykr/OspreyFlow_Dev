// The selection, shown once (ADR-097 step 1, design review item 2): a floating bar at the bottom
// centre of the canvas while anything is selected, its count the only live count of the selection
// in the page, with what can be done to all of it. Replaces the corner chip (ADR-093 step 3) and
// the toolbar's *Remove selected*. *Save as a view* saves the selection as a private case view
// (ADR-144 decision 4). Escape clears, as on the canvas.
import { useState } from "react";

import { SELECTION_WORDS as W } from "./selectionActions";

/** ADR-098 Amendment 4: the furthest the routes are looked for, and how many may be selected to
 * look past one degree — the Conduit's `LINKS_AMONG_MAX_DEGREE` and `LINKS_AMONG_ROUTE_NODES`. */
const MAX_DEGREE = 6;
const ROUTE_NODES = 8;

/** How far *Show links* looks for `count` selected at the stepper's `degree`: past one degree only for at
 * most ROUTE_NODES. The bar's reading and the right-click menu's *Show links* both (ADR-078 Amendment 1). */
export function degreeShown(count: number, degree: number): number {
  return count <= ROUTE_NODES ? degree : 1;
}

export interface SelectionBarProps {
  count: number;
  /** Expand every selected node. Absent: not offered. */
  onExpand?: () => void;
  /** Save the selection as a private view of this case (ADR-144 decision 4). Absent: not offered. */
  onSaveView?: () => void;
  /** ADR-098: draw the links among the selected nodes, and with a degree above 1 the routes between
   * them within it (Amendment 4). Offered for two or more. */
  onLinksAmong?: (degree: number) => void;
  /** The stepper's degree, held by whoever also offers *Show links* elsewhere (the canvas, for its menu), so
   * the two look as far; with `onDegreeChange`. Absent: the bar holds its own. */
  degree?: number;
  onDegreeChange?: (degree: number) => void;
  /** ADR-098 decision 4, ADR-144 decision 4: save the selection as a private view and ask the model
   * about it there. Offered whenever anything is selected (ADR-098 Amendment 7: a question needs no
   * Document; with none, the model answers from the links and events). */
  onAsk?: () => void;
  /** ADR-128 decision 2: what Select what is lit did, said while its selection stands, with the
   * words "undated links are not included". Absent: the selection did not come from it. */
  litNote?: string;
  /** Gives back the selection that was there before Select what is lit, once. Offered with
   * `litNote`. */
  onUndoLit?: () => void;
  /** Take the selection off the case's canvas. Absent (in a view, which changes nothing on the
   * case): not offered. */
  onRemove?: () => void;
  onClear: () => void;
}

const COUNT = new Intl.NumberFormat("en-GB");

export function SelectionBar({
  count,
  onExpand,
  onSaveView,
  onLinksAmong,
  degree: heldDegree,
  onDegreeChange,
  onAsk,
  litNote,
  onUndoLit,
  onRemove,
  onClear,
}: SelectionBarProps) {
  const [ownDegree, setOwnDegree] = useState(1);
  const degree = heldDegree ?? ownDegree;
  const setDegree = (next: number) => (onDegreeChange ? onDegreeChange(next) : setOwnDegree(next));
  if (count === 0) return null;
  const routesAllowed = count <= ROUTE_NODES;
  const shown = degreeShown(count, degree);
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
          {W.undoLit}
        </button>
      )}
      {onExpand && (
        // ADR-115 E4 (review items 2 and 5): the bar's one primary action, in brass.
        <button type="button" className="btn btn--primary" onClick={onExpand}>
          {W.expand}
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
            {W.linksAmong}
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
      {onAsk && (
        <button type="button" className="btn btn--quiet" onClick={onAsk}>
          {W.ask}
        </button>
      )}
      {onSaveView && (
        <button type="button" className="btn btn--quiet" onClick={onSaveView}>
          {W.saveView}
        </button>
      )}
      {onRemove && (
        <button type="button" className="btn btn--quiet" onClick={onRemove}>
          {W.remove}
        </button>
      )}
      <span className="selection-bar__divider" aria-hidden="true" />
      <button
        type="button"
        className="btn btn--quiet"
        onClick={onClear}
        aria-keyshortcuts="Escape"
      >
        {W.clear}{" "}
        <kbd className="key-cap" aria-hidden="true">
          Esc
        </kbd>
      </button>
    </div>
  );
}
