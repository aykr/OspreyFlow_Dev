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
// lower a limit, never lift it.
//
// A limit changes what is drawn, never what is stored (the owner's ruling of 25 November 2026, round 13). What is kept
// in `ospreyflow.layout-sizes` is read by the React workspace too, so it holds only a size the analyst's own action asked
// for: a drag to a width, a key that moves by a step, a typed size, Home's default. The window's limit and a page's
// `data-max` are applied when a size is *drawn* (`shownSizes`, `shownSize`): a stored 450 opened in a window that holds
// 380, or on a page whose sash says 320, is drawn at 380 or 320 and is still 450 in storage. Reading what is stored, drawing,
// a window resize and `fitToWindow` write nothing.
//
// One writer: every write of a panel size, whichever way it arrives (an arrow, Shift, Home, a pointer drag's
// `setSideWidth`, a programmatic set), ends in `writeSize` below, which says in its own words what it stores. The
// `layoutSizes` setters are not called from anywhere else (a test reads this file and fails on any other call), and
// `SIZE_WRITERS` below lists the entry points that reach the writer: a test walks each against every bound and starting
// state and fails if `actions` has a key that is neither listed there nor known to write no size.
//
// With no script, nothing in this folder runs: every panel is in its normal state with no controls (the markup a page
// writes carries none).
import { createStore } from "zustand/vanilla";

import type { PANEL_FRAME_ACTIONS } from "../keyboard/actionRegistry";
// The size setters and resets of `layoutSizes` are reached only as `sizeStore.<name>`, and only inside the one writer
// marked below; `tests` fail on a call anywhere else in this file, on a named import of one, and on a re-export.
import * as sizeStore from "./layoutSizes";
import {
  MAX_SIDE_WIDTH,
  MIN_CANVAS_WIDTH,
  MIN_PANEL_HEIGHT,
  MIN_SIDE_WIDTH,
  MIN_TIMELINE_HEIGHT,
  clamp,
  getLayoutSizes,
  onLayoutSizesChange,
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

/**
 * The actions that can write a panel size, each through `writeSize`. A new action that writes a size is named here, so
 * that the table in the tests has to give it a row; one that is on neither this list nor the tests' list of actions
 * that write no size fails a test.
 */
export const SIZE_WRITERS = ["setSideWidth", "setPanelHeight", "setTimelineHeight", "resizeByKey"] as const;
export type SizeWriter = (typeof SIZE_WRITERS)[number];

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
  /**
   * The live upper limits the writer applies now (from `Viewport`), so a page can draw them (`aria-valuemax`). Not kept
   * anywhere: they come from the window, and are worked out again with each state.
   */
  limits: SizeUpperLimits;
}

/** The upper limit of each size at one moment: what `upperLimits` gives. */
export type SizeUpperLimits = ReturnType<typeof upperLimits>;

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

/**
 * A page's `maxPx` lowers a limit and never lifts it; a size never goes under its own minimum. The one place this is
 * worked out: the writer applies it, and the attach draws it as `aria-valuemax`, so the two cannot differ.
 *
 * Sizes are whole pixels (`layoutSizes` rounds each one it stores), so a bound is too: a `maxPx` of 350.5 allows 350, not
 * the 351 that rounding 350.5 would store above it. Rounded down, what is written is never above what is drawn as the maximum.
 */
export function lowerLimit(limit: number, minimum: number, maxPx?: number): number {
  return Math.max(minimum, maxPx !== undefined && Number.isFinite(maxPx) ? Math.min(limit, Math.floor(maxPx)) : limit);
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
  /** A window resize: redraws every size for the window as it is now, and writes nothing. A page calls it from its resize listener. */
  fitToWindow(): void;
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

/**
 * The sizes as the page shows them: each held between its minimum and the window's limit as it is now. What is kept in
 * this browser is read by `layoutSizes`, which does not know the window; a size larger than a small window allows is
 * shown at the limit here and is not rewritten (`writeSize` is for the analyst's own act), so it is never mistaken for one.
 */
export function shownSizes(
  sizes: LayoutSizes,
  limits: SizeUpperLimits,
): Pick<PanelFrameState, "sideWidth" | "timelineHeight" | "panelHeights"> {
  const panelHeights: LayoutSizes["panelHeights"] = {};
  for (const [id, height] of Object.entries(sizes.panelHeights) as Array<[SidePanelId, number]>) {
    panelHeights[id] = clamp(height, MIN_PANEL_HEIGHT, limits.panelHeight);
  }
  return {
    sideWidth: clamp(sizes.sideWidth, MIN_SIDE_WIDTH, limits.sideWidth),
    timelineHeight: clamp(sizes.timelineHeight, MIN_TIMELINE_HEIGHT, limits.timelineHeight),
    panelHeights,
  };
}

/**
 * The size of one sash as the page shows it: the state's value held between the axis's minimum and the limit the sash
 * draws as its maximum (the live limit, lowered by the page's `maxPx`). **One place**: the attach draws `aria-valuenow`
 * and the frame's size attribute from it, and `resizeByKey` steps from it, so a key moves the sash from where the page
 * shows it, never from a size the page's bound has already lowered (round 10, J). A stacked panel with no height of its
 * own has the measured `from` (round 10, K), held to the same range. It is only read: a bound met here writes nothing.
 * Undefined for a stacked panel that has neither a height of its own nor a measured one.
 */
export function shownSize(
  state: Pick<PanelFrameState, "sideWidth" | "timelineHeight" | "panelHeights" | "limits">,
  axis: ResizeAxis,
  context: { panel?: SidePanelId | string | null; from?: number; maxPx?: number } = {},
): number | undefined {
  if (axis === "side-width") {
    return clamp(state.sideWidth, MIN_SIDE_WIDTH, lowerLimit(state.limits.sideWidth, MIN_SIDE_WIDTH, context.maxPx));
  }
  if (axis === "timeline-height") {
    return clamp(state.timelineHeight, MIN_TIMELINE_HEIGHT, lowerLimit(state.limits.timelineHeight, MIN_TIMELINE_HEIGHT, context.maxPx));
  }
  const own = isSidePanelId(context.panel) ? state.panelHeights[context.panel] : undefined;
  const value = own ?? context.from;
  if (value === undefined || !finite(value)) return undefined;
  return clamp(value, MIN_PANEL_HEIGHT, lowerLimit(state.limits.panelHeight, MIN_PANEL_HEIGHT, context.maxPx));
}

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

  // The one writer: nothing outside this region calls a `layoutSizes` setter or reset.
  // writer: begin
  type SizeTarget = { axis: "side-width" } | { axis: "timeline-height" } | { axis: "panel-height"; id: SidePanelId };

  /** The size `layoutSizes` itself would keep for a request: whole pixels, never under the minimum, the column never over 480. */
  const asKept = (axis: SizeTarget["axis"], request: number): number =>
    axis === "side-width"
      ? clamp(Math.round(request), MIN_SIDE_WIDTH, MAX_SIDE_WIDTH)
      : Math.max(axis === "timeline-height" ? MIN_TIMELINE_HEIGHT : MIN_PANEL_HEIGHT, Math.round(request));

  /**
   * EVERY WRITE OF A SIZE TO `ospreyflow.layout-sizes` IS THIS FUNCTION, AND IT WRITES ONLY WHAT THE ANALYST ASKED FOR.
   *
   * It is called for the analyst's own act: a drag to a width (`setSideWidth`, `setPanelHeight`, `setTimelineHeight`), a
   * key that moves a sash by a step (the size the sash showed, plus or minus the step), a typed size, or Home (`"default"`:
   * the default, which is the size Home asks for). It stores that size, as asked (whole pixels, never under the minimum,
   * the column never over 480: the range `layoutSizes` keeps for anyone), and nothing else. **It never stores a value
   * produced by the window's limit or a page's `data-max`**: a clamp changes what is drawn (`shownSize`), never what is
   * stored, because the React workspace reads this key too and a size lost to a small window or to one page's bound is the
   * analyst's own size lost for good. So nothing that is not the analyst's act reaches this function: reading what is stored,
   * the first draw, a window resize and `fitToWindow` do not call it.
   *
   * One thing it leaves alone: a request that would change nothing on the screen (a grow key at the limit or the bound, a
   * size that comes to what the sash already shows) stores nothing, so a bound is never kept as if it were chosen.
   *
   * Home asks for the default and stores it (or forgets a stacked panel's own height, which is its default), unless that
   * is already what is kept; the window shows it held to the limit, and it is never stored as the limit.
   */
  const writeSize = (target: SizeTarget, request: number | "default", maxPx?: number): void => {
    const kept = getLayoutSizes();
    if (request === "default") {
      if (target.axis === "side-width") sizeStore.resetSideWidth();
      else if (target.axis === "timeline-height") sizeStore.resetTimelineHeight();
      else sizeStore.resetPanelHeight(target.id);
      return;
    }
    const asked = asKept(target.axis, request);
    const limits = limitsNow();
    const panel = target.axis === "panel-height" ? target.id : null;
    const showsNow = shownSize({ ...kept, limits }, target.axis, { panel, maxPx });
    const wouldShow =
      target.axis === "side-width"
        ? shownSize({ ...kept, sideWidth: asked, limits }, target.axis, { maxPx })
        : target.axis === "timeline-height"
          ? shownSize({ ...kept, timelineHeight: asked, limits }, target.axis, { maxPx })
          : shownSize({ ...kept, panelHeights: { ...kept.panelHeights, [target.id]: asked }, limits }, target.axis, { panel, maxPx });
    if (showsNow !== undefined && wouldShow === showsNow) return;
    if (target.axis === "side-width") sizeStore.setSideWidth(asked);
    else if (target.axis === "timeline-height") sizeStore.setTimelineHeight(asked);
    else sizeStore.setPanelHeight(target.id, asked);
  };
  // writer: end

  const snapshot = (): PanelFrameState => {
    const sizes = getLayoutSizes();
    const limits = limitsNow();
    return {
      sideMode: currentSidePanelMode("normal"),
      timelineOpen,
      order: [...getSidePanelOrder()],
      folded: [...folded],
      ...shownSizes(sizes, limits),
      limits,
    };
  };

  const store = createStore<PanelFrameState>(() => snapshot());
  const sync = (): void => {
    store.setState(snapshot(), true);
  };
  /** Redraws if the window's limits moved though no size did. Nothing is written: a limit changes what is drawn. */
  const redrawIfWindowMoved = (): void => {
    const held = store.getState().limits;
    const now = limitsNow();
    if (held.sideWidth !== now.sideWidth || held.timelineHeight !== now.timelineHeight || held.panelHeight !== now.panelHeight) sync();
  };
  const stops = [onLayoutSizesChange(sync), onSidePanelOrderChange(sync)];
  sidePanelListeners.add(sync);

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
      if (finite(px)) writeSize({ axis: "side-width" }, px, limits?.maxPx);
      redrawIfWindowMoved();
    },
    setPanelHeight(id, px, limits) {
      if (isSidePanelId(id) && finite(px)) writeSize({ axis: "panel-height", id }, px, limits?.maxPx);
      redrawIfWindowMoved();
    },
    setTimelineHeight(px, limits) {
      if (finite(px)) writeSize({ axis: "timeline-height" }, px, limits?.maxPx);
      redrawIfWindowMoved();
    },
    resizeByKey(axis, key, context = {}) {
      const step = key.shiftKey ? SASH_LARGE_STEP : SASH_STEP;
      // The window may have changed since the last key: step from what is drawn for the window as it is now.
      redrawIfWindowMoved();
      const state = store.getState();
      const panel = isSidePanelId(context.panel) ? context.panel : null;
      // A vertical sash (the column's) grows leftwards, a stacked panel's grows downwards, the timeline's upwards
      // (the sash sits above it): the directions of `Sash.tsx`.
      const grows = axis === "side-width" ? "ArrowLeft" : axis === "panel-height" ? "ArrowDown" : "ArrowUp";
      const shrinks = axis === "side-width" ? "ArrowRight" : axis === "panel-height" ? "ArrowUp" : "ArrowDown";
      if (key.key === "Home") {
        // Home asks the one writer for the default, which stores it as the default (the analyst's own reset) and never as the
        // limit or the page's bound; the sash draws it held to them.
        if (axis === "side-width") writeSize({ axis: "side-width" }, "default");
        else if (axis === "timeline-height") writeSize({ axis: "timeline-height" }, "default");
        else if (panel !== null) writeSize({ axis: "panel-height", id: panel }, "default");
        return true;
      }
      if (key.key !== grows && key.key !== shrinks) return false;
      const delta = key.key === grows ? step : -step;
      // Step from the size as the sash shows it (`shownSize`, which the draw reads too), not from the state's value: a
      // page's bound lowers what is shown and writes nothing, so the state may be higher than the sash says.
      const from = shownSize(state, axis, { panel, from: context.from, maxPx: context.maxPx });
      if (from === undefined) return true;
      if (axis === "side-width") actions.setSideWidth(from + delta, { maxPx: context.maxPx });
      else if (axis === "timeline-height") actions.setTimelineHeight(from + delta, { maxPx: context.maxPx });
      else if (panel !== null) {
        // A stacked panel that shares the column has no height of its own: a key that would leave it where it is drawn
        // (a grow key at its bound) chooses nothing, so it does not give the panel the measured height as its own.
        const to = clamp(from + delta, MIN_PANEL_HEIGHT, lowerLimit(state.limits.panelHeight, MIN_PANEL_HEIGHT, context.maxPx));
        if (state.panelHeights[panel] === undefined && to === from) return true;
        actions.setPanelHeight(panel, from + delta, { maxPx: context.maxPx });
      }
      return true;
    },
    toggleDetails: () => toggleSidePanel(),
    fitToWindow: redrawIfWindowMoved,
  };

  return {
    getState() {
      redrawIfWindowMoved();
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
