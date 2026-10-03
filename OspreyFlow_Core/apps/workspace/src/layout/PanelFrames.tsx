// The frames the Glass puts round its side panel (the Inspector, its metrics and the query builder)
// and its bottom panel (the timeline), so an analyst can put either out of the way, and open the
// side panel to the whole work area when the query builder needs the room.
//
// The contents stay mounted while hidden, so nothing an analyst has typed or chosen is lost by
// hiding a panel. All of it is the layout of this browser tab: nothing is stored or sent.
import { useState, type ReactNode } from "react";

import { Button } from "../design/primitives/Button";

export type SidePanelMode = "normal" | "collapsed" | "full";

export const SIDE_PANEL_WIDTH = 320;
export const SIDE_PANEL_RAIL_WIDTH = 36;

const headerStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "var(--sp-8)",
  padding: "var(--sp-8)",
  flexShrink: 0,
} as const;

/**
 * The right-hand column. Normal is 320 pixels wide; collapsed leaves a narrow strip with one button
 * to bring it back; full covers the whole work area (the parent must be `position: relative`) so a
 * wide query fits. The canvas underneath stays as it was, so nothing in the view moves.
 */
export function SidePanelFrame({
  name,
  children,
  initialMode = "normal",
}: {
  /** What the panel is called in its buttons, such as "Inspector". */
  name: string;
  children: ReactNode;
  initialMode?: SidePanelMode;
}) {
  const [mode, setMode] = useState<SidePanelMode>(initialMode);
  const lower = name.toLowerCase();
  const collapsed = mode === "collapsed";
  const full = mode === "full";
  return (
    <div
      role="region"
      aria-label={name}
      data-panel-mode={mode}
      style={
        full
          ? {
              position: "absolute",
              inset: 0,
              zIndex: 20,
              background: "var(--surface-panel)",
              borderLeft: "1px solid var(--border-subtle)",
              display: "flex",
              flexDirection: "column",
              overflowY: "auto",
            }
          : {
              width: collapsed ? SIDE_PANEL_RAIL_WIDTH : SIDE_PANEL_WIDTH,
              borderLeft: "1px solid var(--border-subtle)",
              display: "flex",
              flexDirection: "column",
              overflowY: collapsed ? "hidden" : "auto",
            }
      }
    >
      {collapsed ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "var(--sp-8) 0" }}>
          <Button
            aria-label={`Show the ${lower}`}
            aria-expanded={false}
            onClick={() => setMode("normal")}
            style={{ writingMode: "vertical-rl", padding: "var(--sp-8) 4px" }}
          >
            {name}
          </Button>
        </div>
      ) : (
        <div style={headerStyle}>
          {full ? (
            <Button aria-label={`Return the ${lower} to its normal width`} onClick={() => setMode("normal")}>
              Normal width
            </Button>
          ) : (
            <Button aria-label={`Open the ${lower} to the full width`} onClick={() => setMode("full")}>
              Full width
            </Button>
          )}
          <Button aria-label={`Hide the ${lower}`} aria-expanded={true} onClick={() => setMode("collapsed")}>
            Hide
          </Button>
        </div>
      )}
      <div
        style={{
          display: collapsed ? "none" : "flex",
          flexDirection: "column",
          flex: 1,
          minHeight: 0,
        }}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * The bottom panel. Hidden, only its title row stays and the contents keep their size (clipped), so
 * the timeline's own brush and playback are as they were when it is shown again.
 */
export function BottomPanelFrame({
  title,
  height,
  children,
  initiallyOpen = true,
}: {
  title: string;
  height: number;
  children: ReactNode;
  initiallyOpen?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const lower = title.toLowerCase();
  return (
    <div
      role="region"
      aria-label={title}
      style={{ borderTop: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column" }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--sp-8)",
          padding: "4px var(--sp-8)",
        }}
      >
        <span style={{ color: "var(--text-secondary)" }}>{title}</span>
        <Button aria-label={open ? `Hide the ${lower}` : `Show the ${lower}`} aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"}
        </Button>
      </div>
      <div style={{ height: open ? height : 0, overflow: "hidden" }}>
        <div style={{ height }} aria-hidden={!open}>
          {children}
        </div>
      </div>
    </div>
  );
}
