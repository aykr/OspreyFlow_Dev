// The right-hand column's panels in the analyst's order, each in a slot with a grip row (ADR-085):
// a drag handle for the mouse and Move up / Move down buttons, which are the keyboard route (rule
// 13). Dropping a dragged handle on another slot puts the dragged panel at that slot's place.
//
// A button that cannot act (the top panel's Move up, the bottom panel's Move down) is marked
// `aria-disabled` rather than `disabled`, so it keeps focus: the button an analyst has just pressed
// to move a panel to the top must not throw their focus away as its own result.
import { useRef, type DragEvent, type ReactNode } from "react";

import { IconButton } from "../design/primitives/IconButton";
import { moveSidePanel, moveSidePanelTo, useSidePanelOrder, type SidePanelId } from "./panelOrder";

export interface SidePanelSlot {
  id: SidePanelId;
  /** What the panel is called in its buttons, such as "Metrics". */
  name: string;
  content: ReactNode;
}

const gripStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "var(--sp-4)",
  padding: "0 var(--sp-8)",
  color: "var(--text-tertiary)",
  flexShrink: 0,
} as const;

const handleStyle = {
  cursor: "grab",
  padding: "var(--sp-4) var(--sp-8)",
  fontSize: "var(--fs-13)",
  lineHeight: 1,
  userSelect: "none",
} as const;

export function SidePanelStack({ panels }: { panels: SidePanelSlot[] }) {
  const order = useSidePanelOrder();
  const dragging = useRef<SidePanelId | null>(null);
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
        return (
          <div
            key={panel.id}
            data-panel-slot={panel.id}
            onDragOver={onDragOver}
            onDrop={onDrop(panel.id)}
            style={{ display: "flex", flexDirection: "column", flexShrink: 0 }}
          >
            <div style={gripStyle} role="toolbar" aria-label={`${panel.name} position`}>
              <span
                role="img"
                aria-label={`Drag to move the ${lower}`}
                draggable
                onDragStart={onDragStart(panel.id)}
                onDragEnd={() => {
                  dragging.current = null;
                }}
                style={handleStyle}
              >
                ⠿
              </span>
              <span style={{ display: "flex", gap: "var(--sp-4)" }}>
                <IconButton
                  label={`Move the ${lower} up`}
                  aria-disabled={first}
                  onClick={() => {
                    if (!first) moveSidePanel(panel.id, "up");
                  }}
                >
                  ▲
                </IconButton>
                <IconButton
                  label={`Move the ${lower} down`}
                  aria-disabled={last}
                  onClick={() => {
                    if (!last) moveSidePanel(panel.id, "down");
                  }}
                >
                  ▼
                </IconButton>
              </span>
            </div>
            {panel.content}
          </div>
        );
      })}
    </>
  );
}
