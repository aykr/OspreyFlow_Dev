// The right-hand column's panels in the analyst's order, each in a slot under one header row
// (ADR-085, ADR-097 step 1 for design review item 8): the panel's name at `--fs-12` 600, a drag
// handle for the mouse, and a menu holding Move up / Move down; Alt+Up and Alt+Down on the header
// move the panel too. Those are the keyboard routes (rule 13). Dropping a dragged handle on another
// slot puts the dragged panel at that slot's place.
//
// A panel folds whole from its name in the header (owner, 6 October 2026): its contents stay
// mounted, its height goes to the panels still open, and what is folded is kept in this browser.
//
// A button that cannot act (the top panel's Move up, the bottom panel's Move down) is marked
// `aria-disabled` rather than `disabled`, so it keeps focus: the button an analyst has just pressed
// to move a panel to the top must not throw their focus away as its own result.
import { useLayoutEffect, useRef, useState, type DragEvent, type ReactNode } from "react";

import { MIN_PANEL_HEIGHT, resetPanelHeight, setPanelHeight, useLayoutSizes } from "./layoutSizes";
import { moveSidePanel, moveSidePanelTo, useSidePanelOrder, type SidePanelId } from "./panelOrder";
import { Sash } from "./Sash";

export interface SidePanelSlot {
  id: SidePanelId;
  /** What the panel is called in its buttons, such as "Metrics". */
  name: string;
  content: ReactNode;
}


const FOLDED_KEY = "ospreyflow.side-panels-folded";

function loadFolded(): Set<SidePanelId> {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(FOLDED_KEY) ?? "[]");
    return new Set(Array.isArray(raw) ? (raw.filter((v) => typeof v === "string") as SidePanelId[]) : []);
  } catch {
    return new Set();
  }
}

export function SidePanelStack({ panels }: { panels: SidePanelSlot[] }) {
  const order = useSidePanelOrder();
  const [folded, setFolded] = useState<Set<SidePanelId>>(loadFolded);
  const toggleFolded = (id: SidePanelId) =>
    setFolded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        localStorage.setItem(FOLDED_KEY, JSON.stringify([...next]));
      } catch {
        // Private window or blocked storage: kept for this page only.
      }
      return next;
    });
  const { panelHeights } = useLayoutSizes();
  const dragging = useRef<SidePanelId | null>(null);
  const [arranging, setArranging] = useState<SidePanelId | null>(null);
  // ADR-086: each panel but the last can be given a height of its own by the sash below it; a
  // panel with none shares what is left. A sash speaks in pixels, so the height a sharing panel
  // happens to have is measured after each draw.
  const slotRefs = useRef<Partial<Record<SidePanelId, HTMLDivElement | null>>>({});
  const [measured, setMeasured] = useState<Partial<Record<SidePanelId, number>>>({});
  useLayoutEffect(() => {
    const next: Partial<Record<SidePanelId, number>> = {};
    for (const [id, el] of Object.entries(slotRefs.current)) {
      if (el) next[id as SidePanelId] = Math.round(el.getBoundingClientRect().height);
    }
    setMeasured((prev) =>
      Object.keys(next).every((k) => prev[k as SidePanelId] === next[k as SidePanelId]) &&
      Object.keys(prev).length === Object.keys(next).length
        ? prev
        : next,
    );
  }, [order, panelHeights, panels, folded]);
  const shown = order.flatMap((id) => {
    const panel = panels.find((p) => p.id === id);
    return panel ? [panel] : [];
  });

  const onDragStart = (id: SidePanelId) => (event: DragEvent) => {
    dragging.current = id;
    // jsdom builds a DragEvent with no dataTransfer; the browser needs one set for a drag to begin.
    event.dataTransfer?.setData("text/plain", id);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
  };
  const onDrop = (target: SidePanelId) => (event: DragEvent) => {
    event.preventDefault();
    const moved = dragging.current;
    dragging.current = null;
    if (moved) moveSidePanelTo(moved, target);
  };
  const onDragOver = (event: DragEvent) => {
    if (dragging.current) event.preventDefault();
  };

  return (
    <>
      {shown.map((panel, index) => {
        const lower = panel.name.toLowerCase();
        const first = index === 0;
        const last = index === shown.length - 1;
        const isFolded = folded.has(panel.id);
        // The last panel still open takes what is left, whatever height it was given.
        const lastOpen = shown.filter((p) => !folded.has(p.id)).at(-1)?.id === panel.id;
        const own = panelHeights[panel.id];
        const sized = own !== undefined && !lastOpen;
        return (
          <div
            key={panel.id}
            data-panel-slot={panel.id}
            ref={(el) => {
              slotRefs.current[panel.id] = el;
            }}
            onDragOver={onDragOver}
            onDrop={onDrop(panel.id)}
            style={{
              display: "flex",
              flexDirection: "column",
              height: !isFolded && sized ? own : undefined,
              flex: isFolded || sized ? "0 0 auto" : "1 1 0",
              minHeight: isFolded ? undefined : MIN_PANEL_HEIGHT,
              overflow: isFolded ? "hidden" : "auto",
            }}
          >
            <div
              className="side-panel-header"
              role="toolbar"
              aria-label={`${panel.name} position`}
              onKeyDown={(event) => {
                if (!event.altKey) return;
                if (event.key === "ArrowUp" && !first) {
                  event.preventDefault();
                  moveSidePanel(panel.id, "up");
                } else if (event.key === "ArrowDown" && !last) {
                  event.preventDefault();
                  moveSidePanel(panel.id, "down");
                }
              }}
            >
              <span
                role="img"
                aria-label={`Drag to move the ${lower}`}
                draggable
                onDragStart={onDragStart(panel.id)}
                onDragEnd={() => {
                  dragging.current = null;
                }}
                className="side-panel-header__handle"
              >
                ⠿
              </span>
              <button
                type="button"
                className="side-panel-header__name side-panel-header__toggle"
                aria-expanded={!isFolded}
                title={isFolded ? `Show the ${lower}` : `Fold the ${lower}`}
                onClick={() => toggleFolded(panel.id)}
              >
                <svg className="side-panel-header__chevron" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
                  <path d="M3 2l4 3-4 3" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                {panel.name}
              </button>
              <button
                type="button"
                className="side-panel-header__menu"
                aria-label={`Arrange the ${lower}`}
                aria-expanded={arranging === panel.id}
                title="Move this panel (or Alt+Up / Alt+Down)"
                onClick={() => setArranging((open) => (open === panel.id ? null : panel.id))}
              >
                ⋯
              </button>
              <span role="group" aria-label={`Arrange the ${lower}`} className="side-panel-header__moves" hidden={arranging !== panel.id}>
                <button
                  type="button"
                  className="btn btn--quiet"
                  aria-label={`Move the ${lower} up`}
                  aria-disabled={first}
                  onClick={() => {
                    if (!first) moveSidePanel(panel.id, "up");
                  }}
                >
                  Move up
                </button>
                <button
                  type="button"
                  className="btn btn--quiet"
                  aria-label={`Move the ${lower} down`}
                  aria-disabled={last}
                  onClick={() => {
                    if (!last) moveSidePanel(panel.id, "down");
                  }}
                >
                  Move down
                </button>
              </span>
            </div>
            <div data-panel-body="" hidden={isFolded} style={{ display: isFolded ? "none" : "contents" }}>
              {panel.content}
            </div>
            {!last && !isFolded && (
              <Sash
                label={`Resize the ${lower}`}
                orientation="horizontal"
                value={own ?? Math.max(MIN_PANEL_HEIGHT, measured[panel.id] ?? MIN_PANEL_HEIGHT)}
                min={MIN_PANEL_HEIGHT}
                max={Math.max(MIN_PANEL_HEIGHT, window.innerHeight)}
                direction={1}
                onChange={(px) => setPanelHeight(panel.id, px)}
                onReset={() => resetPanelHeight(panel.id)}
              />
            )}
          </div>
        );
      })}
    </>
  );
}
