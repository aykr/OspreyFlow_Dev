// The panel frame's state and its ten actions, in plain TypeScript (slice PL8a; ADR-152 decision 3: one panel pattern,
// a vanilla store; decision 8: no inline style). No React, no drawing library, and no page: a page's script gives this
// store to `panelFrameAttach.ts`, which is the only thing that touches an element.
//
// What the store holds, and which of it is kept (the table in `spec/02_GLASS_FRONTEND.md`, "The ten panel actions";
// the declaration is `PANEL_ACTION_STORAGE` below, and `tests/glass_trees/test_panel_frame_spec_table.py` fails if the
// two differ):
//
//   this tab only        the side panel's mode (open, closed, full width), the timeline's open or folded state.
//                        Not stored: each panel opens in its normal state on reload (ADR-082).
//   this browser         the order (`panelOrder.ts`), the sizes (`layoutSizes.ts`) and what is folded (here, under the
//                        key the workspace already uses). A stored value that is missing, corrupt or of the wrong
//                        shape is ignored and the normal state used; a browser with no storage, or one that refuses
//                        a write, leaves the change in memory for the page. Nothing here throws for either.
//
// The three modules above and `sidePanelState.ts` are used, not copied: they hold the order, the sizes and the side
// panel's mode (their own storage, their own clamping, their own listeners), and this store is the one place that
// reads them together, adds the fold and the timeline, and tells its subscribers when any of it changes.
//
// The minimum side width is 300 (the owner's ruling of 24 November 2026). A width set below it is raised to it, not
// refused, as `layoutSizes.ts` does; a width above the widest allowed is held there.
//
// The upper limits are the store's own, read from the live window at each resize (the spec table: the timeline no
// taller than seven tenths of the window; the column no wider than 480 and leaving the canvas 320; a stacked panel no
// taller than the window). A server-rendered page cannot keep them in its markup, since the window changes after the
// page is written, so the store asks one function, `Viewport`, each time (the default reads the window as
// `sidePanelState.isWide()` reads `innerWidth`; a test or a page gives its own). A `maxPx` a caller passes can only
// lower a limit, never lift it. A stored size above today's limit is brought down when it is read and at each key press.
//
// With no script, nothing in this folder runs: every panel is in its normal state with no controls (the markup a page
// writes carries none).
import { createStore } from "zustand/vanilla";

import type { PANEL_FRAME_ACTIONS } from "../keyboard/actionRegistry";
import {
  MAX_SIDE_WIDTH,
  MIN_CANVAS_WIDTH,
  MIN_PANEL_HEIGHT,
  MIN_SIDE_WIDTH,
  MIN_TIMELINE_HEIGHT,
  clamp,
  getLayoutSizes,
  onLayoutSizesChange,
  resetPanelHeight,
  resetSideWidth,
  resetTimelineHeight,
  setPanelHeight,
  setSideWidth,
  setTimelineHeight,
  type LayoutSizes,
} from "./layoutSizes";
import {
  SIDE_PANEL_IDS,
  getSidePanelOrder,
  moveSidePanel,
  moveSidePanelTo,
  onSidePanelOrderChange,
  type SidePanelId,
} from "./panelOrder";
import {
  currentSidePanelMode,
  setSidePanelMode,
  sidePanelListeners,
  toggleSidePanel,
  type SidePanelMode,
} from "./sidePanelState";

export type PanelFrameActionId = (typeof PANEL_FRAME_ACTIONS)[number];

/** The key the workspace's own fold is kept under (`SidePanelStack.tsx`), so a browser that has one has the other. */
export const FOLDED_PANELS_KEY = "ospreyflow.side-panels-folded";

/** The sash steps of spec/02 "Resizing panels": 16 pixels, 64 with Shift. */
export const SASH_STEP = 16;
export const SASH_LARGE_STEP = 64;

/** Whether each action's result is kept in the tab only or in this browser: the spec table's *Kept* column. */
export const PANEL_ACTION_STORAGE = {
  "hide-and-show-the-side-panel-by-keyboard": "tab",
  "open-the-side-panel-to-the-full-width-and-return-by-keyboard": "tab",
  "hide-and-show-the-timeline-by-keyboard": "tab",
  "move-a-side-panel-up-and-down-by-keyboard": "browser",
  "move-a-side-panel-with-alt-arrows-by-keyboard": "browser",
  "fold-a-side-panel-by-keyboard": "browser",
  "resize-the-side-panel-by-keyboard": "browser",
  "resize-a-stacked-panel-by-keyboard": "browser",
  "resize-the-timeline-by-keyboard": "browser",
  "close-and-open-the-details-panel-by-keyboard": "tab",
} as const satisfies Record<PanelFrameActionId, "tab" | "browser">;

/** The folded panels in a new browser: every panel but the Inspector (ADR-145 decision 4, Amendment 2). */
export const DEFAULT_FOLDED_PANELS: readonly SidePanelId[] = SIDE_PANEL_IDS.filter((id) => id !== "inspector");

export type ResizeAxis = "side-width" | "panel-height" | "timeline-height";

export interface PanelFrameState {
  /** This tab only. */
  sideMode: SidePanelMode;
  /** This tab only: the timeline opens folded. */
  timelineOpen: boolean;
  /** This browser: every panel once, in the analyst's order. */
  order: SidePanelId[];
  /** This browser: the folded panels, held in the panels' default order. */
  folded: SidePanelId[];
  /** This browser. */
  sideWidth: number;
  timelineHeight: number;
  panelHeights: LayoutSizes["panelHeights"];
}

/** How much room there is now: the window's height and the work area's width, in pixels. */
export interface ViewportSize {
  windowHeight: number;
  workWidth: number;
}

/** Asked at each resize, so a window that has changed since the page was written is the one the limits come from. */
export type Viewport = () => ViewportSize;

export interface PanelFrameStoreOptions {
  viewport?: Viewport;
}

/** The timeline is held to this share of the window's height, so the canvas keeps the rest (as the workspace does). */
export const TIMELINE_HEIGHT_SHARE = 0.7;

/** Taken as the window's size where there is none to read (no window at all), so no limit is ever missing. */
const FALLBACK_VIEWPORT: ViewportSize = { windowHeight: 768, workWidth: 1280 };

/** The default `Viewport`: the window's inner size, read at each call; the work area is as wide as the window. */
export const windowViewport: Viewport = () => {
  const win = (globalThis as { window?: { innerWidth?: unknown; innerHeight?: unknown } }).window;
  const positive = (value: unknown, fallback: number): number =>
    typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback;
  return {
    windowHeight: positive(win?.innerHeight, FALLBACK_VIEWPORT.windowHeight),
    workWidth: positive(win?.innerWidth, FALLBACK_VIEWPORT.workWidth),
  };
};

/** The upper limit of each size for a viewport, never below that size's own minimum. */
export function upperLimits(viewport: ViewportSize): { sideWidth: number; timelineHeight: number; panelHeight: number } {
  return {
    sideWidth: Math.min(MAX_SIDE_WIDTH, Math.max(MIN_SIDE_WIDTH, Math.floor(viewport.workWidth - MIN_CANVAS_WIDTH))),
    timelineHeight: Math.max(MIN_TIMELINE_HEIGHT, Math.round(viewport.windowHeight * TIMELINE_HEIGHT_SHARE)),
    panelHeight: Math.max(MIN_PANEL_HEIGHT, Math.round(viewport.windowHeight)),
  };
}

/** What a page knows and the store does not. */
export interface SizeLimits {
  /**
   * A bound a page may add. It can only lower the limit the store reads from the window, never lift it, and a size
   * never goes below its minimum whatever this says.
   */
  maxPx?: number;
}

export interface ResizeContext extends SizeLimits {
  /** For a stacked panel's sash: which panel. */
  panel?: SidePanelId | string | null;
  /** For a stacked panel with no height of its own: the height it has now, measured by the page. */
  from?: number;
}

export interface KeyLike {
  key: string;
  altKey?: boolean;
  shiftKey?: boolean;
}

export interface PanelFrameActions {
  hideSidePanel(): void;
  showSidePanel(): void;
  openSidePanelFullWidth(): void;
  returnSidePanelToNormalWidth(): void;
  hideTimeline(): void;
  showTimeline(): void;
  moveSidePanel(id: SidePanelId, direction: "up" | "down"): void;
  /** Alt+Up and Alt+Down on a panel's header. Returns whether the key moved the panel (so the caller may stop it). */
  moveSidePanelByKey(id: SidePanelId, key: KeyLike): boolean;
  /** A drop: the dragged panel takes the target's place. */
  dropSidePanelOn(id: SidePanelId, target: SidePanelId): void;
  toggleFold(id: SidePanelId): void;
  setSideWidth(px: number, limits?: SizeLimits): void;
  setPanelHeight(id: SidePanelId, px: number, limits?: SizeLimits): void;
  setTimelineHeight(px: number, limits?: SizeLimits): void;
  /** A sash's arrow keys and Home. Returns whether the key was one of them. */
  resizeByKey(axis: ResizeAxis, key: KeyLike, context?: ResizeContext): boolean;
  /** The canvas toolbar's *Details*. */
  toggleDetails(): void;
}

export interface PanelFrameStore {
  getState(): PanelFrameState;
  subscribe(listener: (state: PanelFrameState, previous: PanelFrameState) => void): () => void;
  readonly actions: PanelFrameActions;
  /** Stops listening to the layout modules. For a page that goes away, and for tests. */
  destroy(): void;
}

export function isSidePanelId(value: unknown): value is SidePanelId {
  return typeof value === "string" && (SIDE_PANEL_IDS as readonly string[]).includes(value);
}

/** A stored fold made safe: only known panels, once each, in default order; anything but a list of panels is the default. */
export function normaliseFolded(value: unknown): SidePanelId[] {
  if (!Array.isArray(value)) return [...DEFAULT_FOLDED_PANELS];
  const known = SIDE_PANEL_IDS.filter((id) => value.includes(id));
  // An empty list is a real choice (every panel open); a list that names no panel the Glass knows is not one.
  return value.length > 0 && known.length === 0 ? [...DEFAULT_FOLDED_PANELS] : known;
}

/** The browser's storage, or null where there is none or it refuses to be touched (a private window). */
function browserStorage(): Pick<Storage, "getItem" | "setItem"> | null {
  try {
    return (globalThis as { localStorage?: Storage }).localStorage ?? null;
  } catch {
    return null;
  }
}

function readFolded(): SidePanelId[] {
  let parsed: unknown = null;
  try {
    const raw = browserStorage()?.getItem(FOLDED_PANELS_KEY) ?? null;
    parsed = raw === null ? null : JSON.parse(raw);
  } catch {
    parsed = null;
  }
  return normaliseFolded(parsed);
}

function writeFolded(folded: readonly SidePanelId[]): void {
  try {
    browserStorage()?.setItem(FOLDED_PANELS_KEY, JSON.stringify(folded));
  } catch {
    // A full or refused store: the fold is kept for this page, which is the honest fallback.
  }
}

const finite = (px: number): boolean => typeof px === "number" && Number.isFinite(px);

export function createPanelFrameStore(options: PanelFrameStoreOptions = {}): PanelFrameStore {
  const readViewport = options.viewport ?? windowViewport;
  let folded = readFolded();
  let timelineOpen = false;

  /** The limits for the window as it is now. A function that throws or gives nonsense is the fallback window. */
  const limitsNow = () => {
    let size: ViewportSize = FALLBACK_VIEWPORT;
    try {
      const read = readViewport();
      if (finite(read?.windowHeight) && finite(read?.workWidth)) size = read;
    } catch {
      // Keep the fallback: a limit is never missing.
    }
    return upperLimits(size);
  };

  /** A page's `maxPx` lowers a limit and never lifts it; a size never goes under its own minimum. */
  const lowered = (limit: number, minimum: number, maxPx?: number): number =>
    Math.max(minimum, maxPx !== undefined && finite(maxPx) ? Math.min(limit, maxPx) : limit);

  /** Brings every kept size down to today's limit (a stored one, or one a smaller window now rules out). */
  const enforce = (): void => {
    const sizes = getLayoutSizes();
    const limits = limitsNow();
    if (sizes.sideWidth > limits.sideWidth) setSideWidth(limits.sideWidth);
    if (sizes.timelineHeight > limits.timelineHeight) setTimelineHeight(limits.timelineHeight);
    for (const id of SIDE_PANEL_IDS) {
      const own = sizes.panelHeights[id];
      if (own !== undefined && own > limits.panelHeight) setPanelHeight(id, limits.panelHeight);
    }
  };
  enforce();

  const snapshot = (): PanelFrameState => {
    const sizes = getLayoutSizes();
    return {
      sideMode: currentSidePanelMode("normal"),
      timelineOpen,
      order: [...getSidePanelOrder()],
      folded: [...folded],
      sideWidth: sizes.sideWidth,
      timelineHeight: sizes.timelineHeight,
      panelHeights: { ...sizes.panelHeights },
    };
  };

  const store = createStore<PanelFrameState>(() => snapshot());
  const sync = (): void => {
    store.setState(snapshot(), true);
  };
  const stops = [onLayoutSizesChange(sync), onSidePanelOrderChange(sync)];
  sidePanelListeners.add(sync);

  const sideWidthWithin = (px: number, limits?: SizeLimits): number =>
    clamp(px, MIN_SIDE_WIDTH, lowered(limitsNow().sideWidth, MIN_SIDE_WIDTH, limits?.maxPx));

  const actions: PanelFrameActions = {
    hideSidePanel: () => setSidePanelMode("collapsed"),
    showSidePanel: () => setSidePanelMode("normal"),
    openSidePanelFullWidth: () => setSidePanelMode("full"),
    returnSidePanelToNormalWidth: () => setSidePanelMode("normal"),
    hideTimeline() {
      timelineOpen = false;
      sync();
    },
    showTimeline() {
      timelineOpen = true;
      sync();
    },
    moveSidePanel(id, direction) {
      if (isSidePanelId(id)) moveSidePanel(id, direction);
    },
    moveSidePanelByKey(id, key) {
      if (!key.altKey || !isSidePanelId(id)) return false;
      if (key.key !== "ArrowUp" && key.key !== "ArrowDown") return false;
      const before = getSidePanelOrder();
      moveSidePanel(id, key.key === "ArrowUp" ? "up" : "down");
      return getSidePanelOrder() !== before;
    },
    dropSidePanelOn(id, target) {
      if (isSidePanelId(id) && isSidePanelId(target)) moveSidePanelTo(id, target);
    },
    toggleFold(id) {
      if (!isSidePanelId(id)) return;
      folded = SIDE_PANEL_IDS.filter((other) => (other === id ? !folded.includes(other) : folded.includes(other)));
      writeFolded(folded);
      sync();
    },
    setSideWidth(px, limits) {
      if (finite(px)) setSideWidth(sideWidthWithin(px, limits));
    },
    setPanelHeight(id, px, limits) {
      if (!isSidePanelId(id) || !finite(px)) return;
      setPanelHeight(id, clamp(px, MIN_PANEL_HEIGHT, lowered(limitsNow().panelHeight, MIN_PANEL_HEIGHT, limits?.maxPx)));
    },
    setTimelineHeight(px, limits) {
      if (!finite(px)) return;
      setTimelineHeight(clamp(px, MIN_TIMELINE_HEIGHT, lowered(limitsNow().timelineHeight, MIN_TIMELINE_HEIGHT, limits?.maxPx)));
    },
    resizeByKey(axis, key, context = {}) {
      const step = key.shiftKey ? SASH_LARGE_STEP : SASH_STEP;
      // The window may have changed since the last key: bring what is kept down to it before stepping from it.
      enforce();
      const state = store.getState();
      const panel = isSidePanelId(context.panel) ? context.panel : null;
      // A vertical sash (the column's) grows leftwards, a stacked panel's grows downwards, the timeline's upwards
      // (the sash sits above it): the directions of `Sash.tsx`.
      const grows = axis === "side-width" ? "ArrowLeft" : axis === "panel-height" ? "ArrowDown" : "ArrowUp";
      const shrinks = axis === "side-width" ? "ArrowRight" : axis === "panel-height" ? "ArrowUp" : "ArrowDown";
      if (key.key === "Home") {
        if (axis === "side-width") resetSideWidth();
        else if (axis === "timeline-height") resetTimelineHeight();
        else if (panel !== null) resetPanelHeight(panel);
        return true;
      }
      if (key.key !== grows && key.key !== shrinks) return false;
      const delta = key.key === grows ? step : -step;
      if (axis === "side-width") actions.setSideWidth(state.sideWidth + delta, context);
      else if (axis === "timeline-height") actions.setTimelineHeight(state.timelineHeight + delta, context);
      else if (panel !== null) {
        const from = state.panelHeights[panel] ?? context.from;
        if (from !== undefined && finite(from)) actions.setPanelHeight(panel, from + delta, context);
      }
      return true;
    },
    toggleDetails: () => toggleSidePanel(),
  };

  return {
    getState() {
      enforce();
      return store.getState();
    },
    subscribe: (listener) => store.subscribe(listener),
    actions,
    destroy() {
      stops.forEach((stop) => stop());
      sidePanelListeners.delete(sync);
    },
  };
}

// The rule that no panel code sets a style (ADR-152 decision 8: no inline style attribute, no `unsafe-inline`).
// Written from pieces so that this file does not name the thing it looks for, and so that a test can plant each shape.
const STYLE = ["sty", "le"].join("");
const INLINE_STYLE_SHAPES: readonly RegExp[] = [
  new RegExp(`\\.${STYLE}\\b`), // el.style.width = ..., el.style.cssText = ..., el.style.setProperty(...)
  new RegExp(`\\[\\s*["'\`]${STYLE}["'\`]\\s*\\]`), // el["style"]
  new RegExp(`setAttribute\\(\\s*["'\`]${STYLE}["'\`]`), // el.setAttribute("style", ...)
  new RegExp(`\\s${STYLE}=\\\\?["']`), // markup in a string: <div style="...">
];

/** The lines of `source` that set an inline style, comments left out. Each line comes back as `n: text`. */
export function findInlineStyle(source: string): string[] {
  const withoutBlocks = source.replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "));
  const found: string[] = [];
  withoutBlocks.split("\n").forEach((line, index) => {
    const code = line.replace(/(^|\s)\/\/.*$/, "");
    if (INLINE_STYLE_SHAPES.some((shape) => shape.test(code))) found.push(`${index + 1}: ${line.trim()}`);
  });
  return found;
}
