// The sizes an analyst drags the sashes to (ADR-086): the right-hand column's width, each stacked
// panel's height and the timeline's height. Kept in this browser only, beside the panel order
// (`panelOrder.ts`), with the same standing as the theme: never sent, not part of the case. A
// stored size can never break the layout: anything that is not a finite number is ignored, and
// every size is held above its minimum when read and when set.
import { useSyncExternalStore } from "react";

import { SIDE_PANEL_IDS, type SidePanelId } from "./panelOrder";

export const LAYOUT_SIZES_KEY = "ospreyflow.layout-sizes";

export const DEFAULT_SIDE_WIDTH = 320; // ADR-082's normal width
export const DEFAULT_TIMELINE_HEIGHT = 252; // ADR-082's timeline height
export const MIN_SIDE_WIDTH = 240;
/** The canvas keeps at least this much of the work area when the column is widened. */
export const MIN_CANVAS_WIDTH = 320;
export const MIN_TIMELINE_HEIGHT = 96; // the control row and a sliver of strip
export const MIN_PANEL_HEIGHT = 48; // a grip row and a title

export interface LayoutSizes {
  sideWidth: number;
  timelineHeight: number;
  /** A stacked panel with no entry shares the column's height with the others. */
  panelHeights: Partial<Record<SidePanelId, number>>;
}

const DEFAULTS: LayoutSizes = {
  sideWidth: DEFAULT_SIDE_WIDTH,
  timelineHeight: DEFAULT_TIMELINE_HEIGHT,
  panelHeights: {},
};

let cache: LayoutSizes | null = null;
const listeners = new Set<() => void>();

/** Holds `value` between `min` and `max`; when the bounds cross, the minimum wins. */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function size(value: unknown, min: number): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.max(min, Math.round(value));
}

/** Every stored size made safe: a bad field falls back, a small one is raised to its minimum. */
export function normaliseLayoutSizes(value: unknown): LayoutSizes {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return { ...DEFAULTS, panelHeights: {} };
  const record = value as Record<string, unknown>;
  const panelHeights: Partial<Record<SidePanelId, number>> = {};
  const heights = record.panelHeights;
  if (typeof heights === "object" && heights !== null && !Array.isArray(heights)) {
    for (const id of SIDE_PANEL_IDS) {
      const height = size((heights as Record<string, unknown>)[id], MIN_PANEL_HEIGHT);
      if (height !== null) panelHeights[id] = height;
    }
  }
  return {
    sideWidth: size(record.sideWidth, MIN_SIDE_WIDTH) ?? DEFAULT_SIDE_WIDTH,
    timelineHeight: size(record.timelineHeight, MIN_TIMELINE_HEIGHT) ?? DEFAULT_TIMELINE_HEIGHT,
    panelHeights,
  };
}

function load(): LayoutSizes {
  if (cache === null) {
    let raw: string | null = null;
    try {
      raw = localStorage.getItem(LAYOUT_SIZES_KEY);
    } catch {
      // A private window or blocked site data: the sizes then last for this page only.
    }
    let parsed: unknown = null;
    if (raw !== null) {
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = null;
      }
    }
    cache = normaliseLayoutSizes(parsed);
  }
  return cache;
}

/** The sizes now in force. */
export function getLayoutSizes(): LayoutSizes {
  return load();
}

function store(next: LayoutSizes): void {
  cache = next;
  try {
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify(next));
  } catch {
    // Kept in memory for this page, which is the honest fallback.
  }
  listeners.forEach((listener) => listener());
}

export function setSideWidth(px: number): void {
  const next = size(px, MIN_SIDE_WIDTH);
  if (next === null || next === load().sideWidth) return;
  store({ ...load(), sideWidth: next });
}

export function resetSideWidth(): void {
  if (load().sideWidth === DEFAULT_SIDE_WIDTH) return;
  store({ ...load(), sideWidth: DEFAULT_SIDE_WIDTH });
}

export function setTimelineHeight(px: number): void {
  const next = size(px, MIN_TIMELINE_HEIGHT);
  if (next === null || next === load().timelineHeight) return;
  store({ ...load(), timelineHeight: next });
}

export function resetTimelineHeight(): void {
  if (load().timelineHeight === DEFAULT_TIMELINE_HEIGHT) return;
  store({ ...load(), timelineHeight: DEFAULT_TIMELINE_HEIGHT });
}

export function setPanelHeight(id: SidePanelId, px: number): void {
  const next = size(px, MIN_PANEL_HEIGHT);
  if (next === null || next === load().panelHeights[id]) return;
  store({ ...load(), panelHeights: { ...load().panelHeights, [id]: next } });
}

export function resetPanelHeight(id: SidePanelId): void {
  if (!(id in load().panelHeights)) return;
  const panelHeights = { ...load().panelHeights };
  delete panelHeights[id];
  store({ ...load(), panelHeights });
}

/** Calls `listener` whenever a size changes. Returns the function that stops it. */
export function onLayoutSizesChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The sizes, re-rendering the caller when they change. */
export function useLayoutSizes(): LayoutSizes {
  return useSyncExternalStore(onLayoutSizesChange, getLayoutSizes, getLayoutSizes);
}

/** Forgets what was read, so the next read comes from storage again. For tests. */
export function forgetLayoutSizesForTest(): void {
  cache = null;
  listeners.clear();
}
