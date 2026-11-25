// The attach point for a page's panel frame (slice PL8a; ADR-152 decisions 3 and 8): the one function a page's script
// calls to wire its `data-action` elements to the panel frame's store. It is written against the few things of an
// element it needs (`PanelFrameRoot`), so it is tested against a stand-in and mounts on no page here.
//
// It sets no inline style: it changes attributes and classes only. A size reaches the page's CSS as a data attribute
// (`data-side-width`, `data-timeline-height`) and as `aria-valuenow` on its sash; what turns a number into a width is
// the page's stylesheet, not a style written here (ADR-152 decision 8: no inline style attribute, no `unsafe-inline`).
//
// With no script, nothing here runs and every panel is in its normal state: the markup a page writes carries no
// controls without script (the owner's ruling of 24 November 2026), so no control waits on this function.
//
// What the markup says, one hook per thing:
//   [data-panel-frame="side"]      the column; gets `data-panel-mode` (normal, collapsed, full), `data-side-width`
//   [data-panel-frame="timeline"]  the timeline; gets `data-panel-open` (true, false), `data-timeline-height`
//   [data-panel-slot="<id>"]       one panel's slot, a child of the side frame; gets `data-folded`, and is put in the
//                                  analyst's order
//   [data-panel-body="<id>"]       the panel's contents; `hidden` while it is folded (kept in the page, not removed)
//   [data-panel-header="<id>"]     the panel's header row; Alt+Up and Alt+Down on it move the panel
//   [data-action="<name>"]         a control; one of ACTIONS below, with `data-panel="<id>"` where it names a panel
//   [data-action="resize"][data-sash="side-width|panel-height|timeline-height"]
//                                  a sash; its arrow keys and Home resize (16 pixels, 64 with Shift), with
//                                  `data-panel`, `data-from` (the measured height) and `data-max` where they apply.
//                                  The upper limits are not the markup's to give: the store reads the live window at
//                                  each key press (`Viewport` in `panelFrameStore.ts`), so a window resized after the
//                                  page was written is still held. `data-max` can only lower a limit, never lift it.
//
// A sash's `data-max` is held on every path: the key path (Home as the arrows) passes it to the writer, and before it
// draws a state the attach asks the one writer to hold any size above a sash's bound to that bound (a stored value, the
// pointer's set, a window resize), so `aria-valuenow` is never above the `aria-valuemax` drawn beside it. A size the
// analyst never chose (the default) is only drawn at a bound, never written to storage: a draw, a fit and a resize save
// nothing. An arrow key that moves a sash is the analyst's act and stores what it reaches; a key that changes nothing on
// the screen (Home at a default already drawn at the bound, a grow key at the bound) stores nothing either (round 11).
//
// What a sash shows is `shownSize` in the store (round 10): the state's value held to the range drawn beside it, a stacked
// panel with no height of its own included (its measured `data-from`). The arrow keys step from that same value, so the
// first press after a bound has lowered what is shown moves the sash by the step; a bound met on a draw still writes nothing.
//
// Each sash also carries `aria-valuemax`, the limit the writer applies now (the store's live limit, lowered by the
// sash's `data-max`), and the attach redraws it when the window it can reach through `ownerDocument.defaultView`
// resizes. Without a window it draws from the store's own limit and the page may call `fitToWindow` itself.
//
// It listens on the root it is given, once for clicks and once for keys, and acts on an element only when it is inside
// that root and carries a name it knows. It does not look beyond the root, and an unknown name does nothing.
import type { PanelFrameStore, PanelFrameState, ResizeAxis } from "./panelFrameStore";
import { SIDE_PANEL_IDS, type SidePanelId } from "./panelOrder";
import { MIN_PANEL_HEIGHT, MIN_SIDE_WIDTH, MIN_TIMELINE_HEIGHT } from "./layoutSizes";
import { lowerLimit, shownSize } from "./panelFrameStore";

/** What the attach function reads of an element. A DOM element has all of it; a test's stand-in need only offer it. */
export interface PanelFrameElement {
  getAttribute(name: string): string | null;
  setAttribute(name: string, value: string): void;
  hidden: boolean;
  classList: { toggle(name: string, force?: boolean): boolean };
  closest(selector: string): PanelFrameElement | null;
  contains(other: PanelFrameElement | null): boolean;
  append(...nodes: PanelFrameElement[]): void;
  querySelectorAll(selector: string): ArrayLike<PanelFrameElement>;
  readonly ownerDocument?: {
    activeElement?: { focus?: () => void } | null;
    /** The window, where the page has one: the attach listens for a resize on it, so the limits are drawn afresh. */
    defaultView?: {
      addEventListener(type: "resize", listener: () => void): void;
      removeEventListener(type: "resize", listener: () => void): void;
    } | null;
  };
}

export interface PanelFrameEvent {
  target: unknown;
  key?: string;
  altKey?: boolean;
  shiftKey?: boolean;
  preventDefault?: () => void;
}

export interface PanelFrameRoot extends PanelFrameElement {
  addEventListener(type: "click" | "keydown", listener: (event: PanelFrameEvent) => void): void;
  removeEventListener(type: "click" | "keydown", listener: (event: PanelFrameEvent) => void): void;
}

type Action = (store: PanelFrameStore, control: PanelFrameElement) => void;

const panelOf = (control: PanelFrameElement): string | null => control.getAttribute("data-panel");

/** The names a control may carry in `data-action`. */
const ACTIONS: Record<string, Action> = {
  "hide-side-panel": (store) => store.actions.hideSidePanel(),
  "show-side-panel": (store) => store.actions.showSidePanel(),
  "open-side-panel-full-width": (store) => store.actions.openSidePanelFullWidth(),
  "return-side-panel-to-normal-width": (store) => store.actions.returnSidePanelToNormalWidth(),
  "hide-timeline": (store) => store.actions.hideTimeline(),
  "show-timeline": (store) => store.actions.showTimeline(),
  "toggle-details": (store) => store.actions.toggleDetails(),
  "toggle-fold": (store, control) => store.actions.toggleFold(panelOf(control) as SidePanelId),
  "move-side-panel-up": (store, control) => store.actions.moveSidePanel(panelOf(control) as SidePanelId, "up"),
  "move-side-panel-down": (store, control) => store.actions.moveSidePanel(panelOf(control) as SidePanelId, "down"),
};

const AXES: readonly string[] = ["side-width", "panel-height", "timeline-height"] satisfies ResizeAxis[];

const asElement = (target: unknown): PanelFrameElement | null =>
  typeof target === "object" && target !== null && typeof (target as PanelFrameElement).closest === "function"
    ? (target as PanelFrameElement)
    : null;

function numberAttribute(element: PanelFrameElement, name: string): number | undefined {
  const raw = element.getAttribute(name);
  if (raw === null || raw.trim() === "") return undefined;
  const value = Number(raw);
  return Number.isFinite(value) ? value : undefined;
}

function all(root: PanelFrameElement, selector: string): PanelFrameElement[] {
  return Array.from(root.querySelectorAll(selector));
}

/** Draws the state as attributes and classes: no style is written. */
function draw(root: PanelFrameRoot, state: PanelFrameState): void {
  for (const side of all(root, '[data-panel-frame="side"]')) {
    side.setAttribute("data-panel-mode", state.sideMode);
    side.setAttribute("data-side-width", String(state.sideWidth));
    side.classList.toggle("panel-frame--collapsed", state.sideMode === "collapsed");
    side.classList.toggle("panel-frame--full", state.sideMode === "full");
    const slots = all(side, "[data-panel-slot]");
    const wanted = state.order.flatMap((id) => slots.filter((slot) => slot.getAttribute("data-panel-slot") === id));
    if (wanted.length === slots.length && wanted.some((slot, index) => slot !== slots[index])) {
      // Moving a node drops focus from it; the one that had it gets it back.
      const active = root.ownerDocument?.activeElement ?? null;
      side.append(...wanted);
      active?.focus?.();
    }
  }
  for (const timeline of all(root, '[data-panel-frame="timeline"]')) {
    timeline.setAttribute("data-panel-open", String(state.timelineOpen));
    timeline.setAttribute("data-timeline-height", String(state.timelineHeight));
  }
  for (const slot of all(root, "[data-panel-slot]")) {
    slot.setAttribute("data-folded", String(state.folded.includes(slot.getAttribute("data-panel-slot") as SidePanelId)));
  }
  for (const body of all(root, "[data-panel-body]")) {
    body.hidden = state.folded.includes(body.getAttribute("data-panel-body") as SidePanelId);
  }
  for (const control of all(root, "[data-action]")) {
    const id = panelOf(control) as SidePanelId;
    const name = control.getAttribute("data-action");
    if (name === "toggle-fold") control.setAttribute("aria-expanded", String(!state.folded.includes(id)));
    else if (name === "toggle-details") control.setAttribute("aria-pressed", String(state.sideMode !== "collapsed"));
    else if (name === "move-side-panel-up") control.setAttribute("aria-disabled", String(state.order[0] === id));
    else if (name === "move-side-panel-down") control.setAttribute("aria-disabled", String(state.order.at(-1) === id));
  }
  for (const sash of all(root, "[data-sash]")) {
    const axis = sash.getAttribute("data-sash");
    // The maximum is the limit the writer applies: the store's live limit, lowered by this sash's `data-max` as the
    // key path lowers it (`lowerLimit`), so what is drawn is never other than what a key press can reach.
    const maxPx = numberAttribute(sash, "data-max");
    // `aria-valuenow` is the store's `shownSize`, the value a key steps from, held to the range drawn beside it.
    const panel = sash.getAttribute("data-panel");
    const from = numberAttribute(sash, "data-from");
    const shown = axis === null || !AXES.includes(axis) ? undefined : shownSize(state, axis as ResizeAxis, { panel, from, maxPx });
    if (shown !== undefined) sash.setAttribute("aria-valuenow", String(Math.round(shown)));
    if (axis === "side-width") {
      sash.setAttribute("aria-valuemin", String(MIN_SIDE_WIDTH));
      sash.setAttribute("aria-valuemax", String(lowerLimit(state.limits.sideWidth, MIN_SIDE_WIDTH, maxPx)));
    } else if (axis === "timeline-height") {
      sash.setAttribute("aria-valuemin", String(MIN_TIMELINE_HEIGHT));
      sash.setAttribute("aria-valuemax", String(lowerLimit(state.limits.timelineHeight, MIN_TIMELINE_HEIGHT, maxPx)));
    } else if (axis === "panel-height") {
      sash.setAttribute("aria-valuemin", String(MIN_PANEL_HEIGHT));
      sash.setAttribute("aria-valuemax", String(lowerLimit(state.limits.panelHeight, MIN_PANEL_HEIGHT, maxPx)));
    }
  }
}

/**
 * Wires the `data-action` elements inside `root` to `store`, draws the store's state on them now and on each change,
 * and returns the function that undoes all of it. Only `root` is listened to; only elements inside it are acted on.
 */
export function attachPanelFrame(root: PanelFrameRoot, store: PanelFrameStore): () => void {
  if (typeof root?.addEventListener !== "function" || typeof root?.removeEventListener !== "function") {
    throw new Error("attachPanelFrame needs an element with addEventListener and removeEventListener");
  }
  const inside = (element: PanelFrameElement | null): element is PanelFrameElement =>
    element !== null && root.contains(element);

  const onClick = (event: PanelFrameEvent): void => {
    const control = asElement(event.target)?.closest("[data-action]") ?? null;
    if (!inside(control)) return;
    ACTIONS[control.getAttribute("data-action") ?? ""]?.(store, control);
  };

  const onKeyDown = (event: PanelFrameEvent): void => {
    const target = asElement(event.target);
    const key = { key: event.key ?? "", altKey: event.altKey, shiftKey: event.shiftKey };
    const header = target?.closest("[data-panel-header]") ?? null;
    if (inside(header)) {
      const id = header.getAttribute("data-panel-header") as SidePanelId;
      if (SIDE_PANEL_IDS.includes(id) && store.actions.moveSidePanelByKey(id, key)) event.preventDefault?.();
      return;
    }
    const sash = target?.closest("[data-sash]") ?? null;
    if (!inside(sash) || sash.getAttribute("data-action") !== "resize") return;
    const axis = sash.getAttribute("data-sash") ?? "";
    if (!AXES.includes(axis)) return;
    const handled = store.actions.resizeByKey(axis as ResizeAxis, key, {
      panel: sash.getAttribute("data-panel"),
      from: numberAttribute(sash, "data-from"),
      maxPx: numberAttribute(sash, "data-max"),
    });
    if (handled) event.preventDefault?.();
  };

  root.addEventListener("click", onClick);
  root.addEventListener("keydown", onKeyDown);
  /**
   * A sash's `data-max` is a bound the writer applies on every path. The key path passes it; a size that arrived without
   * it (a stored value, the pointer's set, a window resize) is above it only until here, where the one writer is asked to
   * hold it to the bound before anything is drawn. Each write makes a state of its own, which the subscription renders.
   */
  /** How many states have been rendered, so a write that made none (it changed nothing) is told from one that did. */
  let renders = 0;
  const holdToBounds = (state: PanelFrameState): void => {
    for (const sash of all(root, "[data-sash]")) {
      const maxPx = numberAttribute(sash, "data-max");
      if (maxPx === undefined) continue;
      const axis = sash.getAttribute("data-sash");
      const before = renders;
      // `fitting`: this is a size brought down to a bound, not one the analyst asked for, so a default is not written.
      if (axis === "side-width" && state.sideWidth > lowerLimit(state.limits.sideWidth, MIN_SIDE_WIDTH, maxPx)) {
        store.actions.setSideWidth(state.sideWidth, { maxPx, fitting: true });
      } else if (axis === "timeline-height" && state.timelineHeight > lowerLimit(state.limits.timelineHeight, MIN_TIMELINE_HEIGHT, maxPx)) {
        store.actions.setTimelineHeight(state.timelineHeight, { maxPx, fitting: true });
      } else if (axis === "panel-height") {
        const id = sash.getAttribute("data-panel") as SidePanelId;
        const own = state.panelHeights[id];
        if (own !== undefined && own > lowerLimit(state.limits.panelHeight, MIN_PANEL_HEIGHT, maxPx)) {
          store.actions.setPanelHeight(id, own, { maxPx, fitting: true });
        }
      }
      // A write made a state of its own, rendered (and holding the rest) inside the call: this state is stale.
      if (renders !== before) return;
    }
  };
  /**
   * The state as a page's sashes bound it. A size above a sash's `data-max` that the writer did not write (a default,
   * which is never saved for a bound: `fitting`) is drawn at the bound, so `aria-valuenow` and the frame's size attribute
   * are never above the `aria-valuemax` beside them. Drawn only; nothing is written here.
   */
  const withinBounds = (state: PanelFrameState): PanelFrameState => {
    let { sideWidth, timelineHeight } = state;
    const panelHeights = { ...state.panelHeights };
    for (const sash of all(root, "[data-sash]")) {
      const maxPx = numberAttribute(sash, "data-max");
      if (maxPx === undefined) continue;
      const axis = sash.getAttribute("data-sash");
      const panel = sash.getAttribute("data-panel") as SidePanelId;
      if (axis === "side-width") sideWidth = Math.min(sideWidth, shownSize(state, "side-width", { maxPx }) ?? sideWidth);
      else if (axis === "timeline-height") timelineHeight = Math.min(timelineHeight, shownSize(state, "timeline-height", { maxPx }) ?? timelineHeight);
      else if (axis === "panel-height" && panelHeights[panel] !== undefined) {
        panelHeights[panel] = Math.min(panelHeights[panel] as number, shownSize(state, "panel-height", { panel, maxPx }) ?? (panelHeights[panel] as number));
      }
    }
    return { ...state, sideWidth, timelineHeight, panelHeights };
  };
  const render =(state: PanelFrameState): void => {
    const mine = ++renders;
    holdToBounds(state);
    // A write that changed something rendered its own state, inside the call above, and that one is drawn. One that
    // changed nothing rendered none: this state is drawn as it is, so the frame is never left undrawn and the loop ends.
    if (renders === mine) draw(root, withinBounds(state));
  };
  // Subscribed before the first draw: a write made to hold a size to its bound is drawn by the subscription.
  const unsubscribe = store.subscribe(render);
  render(store.getState());
  // The window may change after the page was written: the store works the limits out again and the sashes are redrawn.
  const view = root.ownerDocument?.defaultView ?? null;
  const onResize = (): void => store.actions.fitToWindow();
  view?.addEventListener("resize", onResize);
  return () => {
    unsubscribe();
    view?.removeEventListener("resize", onResize);
    root.removeEventListener("click", onClick);
    root.removeEventListener("keydown", onKeyDown);
  };
}
