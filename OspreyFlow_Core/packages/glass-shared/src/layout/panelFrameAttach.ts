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
//                                  `data-panel`, `data-from` (the measured height) and `data-max` where they apply
//
// It listens on the root it is given, once for clicks and once for keys, and acts on an element only when it is inside
// that root and carries a name it knows. It does not look beyond the root, and an unknown name does nothing.
import type { PanelFrameStore, PanelFrameState, ResizeAxis } from "./panelFrameStore";
import { SIDE_PANEL_IDS, type SidePanelId } from "./panelOrder";
import { MIN_PANEL_HEIGHT, MIN_SIDE_WIDTH, MIN_TIMELINE_HEIGHT } from "./layoutSizes";

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
  readonly ownerDocument?: { activeElement?: { focus?: () => void } | null };
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
    if (axis === "side-width") {
      sash.setAttribute("aria-valuenow", String(state.sideWidth));
      sash.setAttribute("aria-valuemin", String(MIN_SIDE_WIDTH));
    } else if (axis === "timeline-height") {
      sash.setAttribute("aria-valuenow", String(state.timelineHeight));
      sash.setAttribute("aria-valuemin", String(MIN_TIMELINE_HEIGHT));
    } else if (axis === "panel-height") {
      const own = state.panelHeights[sash.getAttribute("data-panel") as SidePanelId];
      const shown = own ?? numberAttribute(sash, "data-from");
      if (shown !== undefined) sash.setAttribute("aria-valuenow", String(Math.round(shown)));
      sash.setAttribute("aria-valuemin", String(MIN_PANEL_HEIGHT));
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
  const render = (state: PanelFrameState): void => draw(root, state);
  render(store.getState());
  const unsubscribe = store.subscribe(render);
  return () => {
    unsubscribe();
    root.removeEventListener("click", onClick);
    root.removeEventListener("keydown", onKeyDown);
  };
}
