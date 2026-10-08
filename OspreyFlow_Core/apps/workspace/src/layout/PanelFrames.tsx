// The frames the Glass puts round its side panel (the Inspector, its metrics and the query builder)
// and its bottom panel (the timeline), so an analyst can put either out of the way, open the side
// panel to the whole work area when the query builder needs the room (ADR-082), and set each
// one's size by dragging its edge or moving it with the keyboard (ADR-086).
//
// The contents stay mounted while hidden, so nothing an analyst has typed or chosen is lost by
// hiding a panel. Hidden or not is the layout of this browser tab (ADR-082: nothing stored); the
// sizes are kept per analyst in this browser (`layoutSizes.ts`, ADR-086).
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "../design/primitives/Button";
import {
  MIN_CANVAS_WIDTH,
  MIN_SIDE_WIDTH,
  MIN_TIMELINE_HEIGHT,
  resetSideWidth,
  resetTimelineHeight,
  setSideWidth,
  setTimelineHeight,
  useLayoutSizes,
} from "./layoutSizes";
import { Sash } from "./Sash";

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

/** The widest the column may be: the work area less the canvas's minimum, or the window's when
 * the frame is not yet laid out. */
function widestSide(frame: HTMLElement | null): number {
  const room = frame?.parentElement?.clientWidth || window.innerWidth;
  return Math.max(MIN_SIDE_WIDTH, room - MIN_CANVAS_WIDTH);
}

/**
 * The right-hand column. Normal is as wide as the analyst last set it (320 pixels to begin with),
 * with a sash on its left edge; collapsed leaves a narrow strip with one button to bring it back;
 * full covers the whole work area (the parent must be `position: relative`) so a wide query fits.
 * The canvas underneath stays as it was, so nothing in the view moves.
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
  const frameRef = useRef<HTMLDivElement>(null);
  const { sideWidth } = useLayoutSizes();
  const lower = name.toLowerCase();
  const collapsed = mode === "collapsed";
  const full = mode === "full";
  return (
    <div
      ref={frameRef}
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
              width: collapsed ? SIDE_PANEL_RAIL_WIDTH : sideWidth,
              maxWidth: collapsed ? undefined : `calc(100% - ${MIN_CANVAS_WIDTH}px)`,
              borderLeft: collapsed ? "1px solid var(--border-subtle)" : undefined,
              display: "flex",
              flexDirection: "row",
              overflow: "hidden",
            }
      }
    >
      {!collapsed && !full && (
        <Sash
          label="Resize the side panel"
          orientation="vertical"
          value={sideWidth}
          min={MIN_SIDE_WIDTH}
          max={widestSide(frameRef.current)}
          direction={-1}
          onChange={setSideWidth}
          onReset={resetSideWidth}
        />
      )}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          overflowY: collapsed ? "hidden" : full ? "visible" : "hidden",
          borderLeft: collapsed || full ? undefined : "1px solid var(--border-subtle)",
        }}
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
    </div>
  );
}

/** The tallest the timeline may be: seven tenths of the window, so the canvas keeps the rest. */
function tallestTimeline(): number {
  return Math.max(MIN_TIMELINE_HEIGHT, Math.round(window.innerHeight * 0.7));
}

/**
 * The bottom panel. Its height is the one the analyst last set (`height` to begin with), with a
 * sash along its top edge while it is shown. Hidden, only its title row stays and the contents
 * keep their size (clipped), so the timeline's own brush and playback are as they were when it is
 * shown again.
 */
export function BottomPanelFrame({
  title,
  height,
  children,
  initiallyOpen = true,
  openSignal = 0,
}: {
  title: string;
  /** The height to begin with; the analyst's own setting, once made, takes its place. */
  height: number;
  children: ReactNode;
  initiallyOpen?: boolean;
  /** Each change opens the panel (Explore's busiest day sets the timeline's window, ADR-100). */
  openSignal?: number;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  useEffect(() => {
    if (openSignal > 0) setOpen(true);
  }, [openSignal]);
  const { timelineHeight } = useLayoutSizes();
  const current = timelineHeight ?? height;
  const lower = title.toLowerCase();
  return (
    <div
      role="region"
      aria-label={title}
      style={{ borderTop: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column" }}
    >
      {open && (
        <Sash
          label={`Resize the ${lower}`}
          orientation="horizontal"
          value={current}
          min={MIN_TIMELINE_HEIGHT}
          max={tallestTimeline()}
          direction={-1}
          onChange={setTimelineHeight}
          onReset={resetTimelineHeight}
        />
      )}
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
      <div style={{ height: open ? current : 0, overflow: "hidden" }}>
        <div style={{ height: current }} aria-hidden={!open}>
          {children}
        </div>
      </div>
    </div>
  );
}
