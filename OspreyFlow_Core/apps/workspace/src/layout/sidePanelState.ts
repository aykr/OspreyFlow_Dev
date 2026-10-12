// The right panel's mode, shared (ADR-115 E4): the panel's own buttons and the canvas toolbar's
// *Details* toggle change the same thing. At a viewport of 1200px or wider it starts docked and open;
// below, it starts closed and opens as an overlay (DESIGN.md v0.3 §5a). Kept for the page only.
import { useSyncExternalStore } from "react";

export type SidePanelMode = "normal" | "collapsed" | "full";
export const DOCK_BREAKPOINT = 1200;

const listeners = new Set<() => void>();
let mode: SidePanelMode | null = null;

export function isWide(): boolean {
  return typeof window === "undefined" || window.innerWidth >= DOCK_BREAKPOINT;
}

function current(initial: SidePanelMode): SidePanelMode {
  if (mode === null) mode = isWide() ? initial : "collapsed";
  return mode;
}

export function setSidePanelMode(next: SidePanelMode): void {
  if (mode === next) return;
  mode = next;
  listeners.forEach((listener) => listener());
}

export function toggleSidePanel(): void {
  setSidePanelMode(current("normal") === "collapsed" ? "normal" : "collapsed");
}

export function useSidePanelMode(initial: SidePanelMode = "normal"): SidePanelMode {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current(initial),
  );
}

/** Whether the viewport is wide enough to dock the panel, following resizes. */
export function useWide(): boolean {
  return useSyncExternalStore(
    (listener) => {
      window.addEventListener("resize", listener);
      return () => window.removeEventListener("resize", listener);
    },
    isWide,
  );
}

/** For tests: forget the mode, so the next panel starts afresh for the viewport. */
export function forgetSidePanelForTest(): void {
  mode = null;
  listeners.forEach((listener) => listener());
}
