// The panel frame's store and its attach point (slice PL8a, ADR-152 decision 3 and 8; the owner's rulings of 24
// November 2026), against stand-ins for the browser's storage and for a page's elements. Nothing here mounts on a page.
//
// Which test fails if the invariant is broken (rule 12):
//  - an action does not change the state the spec table says: the "each of the ten actions" cases;
//  - something kept in this browser is not read back by a fresh store, or hide and show is: the "reload" cases;
//  - the 300 minimum: the "minimum" cases (raised, not refused: the same as `layoutSizes`);
//  - a corrupt or missing stored value throws, or a missing storage throws: the "corrupt" and "no storage" cases,
//    where the stand-in refuses as a real browser does (private mode throws on the property; a full store throws on
//    set), not only grants;
//  - the attach function wires an element it was not given, or sets a style: the "attach" cases, shown red on a
//    planted style write and on a planted inline-style source line.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PANEL_FRAME_ACTIONS } from "../keyboard/actionRegistry";
import {
  DEFAULT_SIDE_WIDTH,
  DEFAULT_TIMELINE_HEIGHT,
  LAYOUT_SIZES_KEY,
  MIN_SIDE_WIDTH,
  forgetLayoutSizesForTest,
  getLayoutSizes,
  resetSideWidth as rawResetSideWidth,
  resetTimelineHeight as rawResetTimelineHeight,
  setPanelHeight as rawSetPanelHeight,
  setSideWidth as rawSetSideWidth,
  setTimelineHeight as rawSetTimelineHeight,
} from "./layoutSizes";
import { SIDE_PANEL_IDS, SIDE_PANEL_ORDER_KEY, forgetSidePanelOrderForTest } from "./panelOrder";
import { attachPanelFrame, type PanelFrameRoot } from "./panelFrameAttach";
import {
  FOLDED_PANELS_KEY,
  PANEL_ACTION_STORAGE,
  SIZE_WRITERS,
  SASH_LARGE_STEP,
  SASH_STEP,
  createPanelFrameStore,
  findInlineStyle,
  type PanelFrameStore,
  type SizeWriter,
} from "./panelFrameStore";
import { forgetSidePanelForTest } from "./sidePanelState";

// ---------------------------------------------------------------------------------------------- the stand-ins

class MemoryStorage {
  readonly items = new Map<string, string>();
  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.items.set(key, String(value));
  }
  removeItem(key: string): void {
    this.items.delete(key);
  }
}

/** Storage that is full: reads work, every write is refused as a browser refuses it. */
class FullStorage extends MemoryStorage {
  override setItem(): void {
    throw new DOMException("The quota has been exceeded.", "QuotaExceededError");
  }
}

function installStorage(storage: MemoryStorage): void {
  vi.stubGlobal("localStorage", storage);
}

/** Site data blocked: the property itself throws when read, as in some private windows. */
function blockStorage(): void {
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() {
      throw new DOMException("The operation is insecure.", "SecurityError");
    },
  });
}

function reload(): PanelFrameStore {
  // A reload forgets what the page held in memory and reads the browser's storage again.
  forgetLayoutSizesForTest();
  forgetSidePanelOrderForTest();
  forgetSidePanelForTest();
  return createPanelFrameStore();
}

let live: PanelFrameStore[] = [];
function open(): PanelFrameStore {
  const store = reload();
  live.push(store);
  return store;
}

beforeEach(() => {
  installStorage(new MemoryStorage());
  forgetLayoutSizesForTest();
  forgetSidePanelOrderForTest();
  forgetSidePanelForTest();
});

afterEach(() => {
  live.forEach((store) => store.destroy());
  live = [];
  vi.unstubAllGlobals();
  delete (globalThis as { localStorage?: unknown }).localStorage;
});

const DEFAULT_FOLDED = SIDE_PANEL_IDS.filter((id) => id !== "inspector");

// ----------------------------------------------------------------------------- each of the ten actions

describe("each of the ten actions changes the state as the spec table says", () => {
  it("the ten ids are the registry's and each is declared as kept in the tab or in this browser", () => {
    expect(Object.keys(PANEL_ACTION_STORAGE).sort()).toEqual([...PANEL_FRAME_ACTIONS].sort());
    expect(PANEL_FRAME_ACTIONS).toHaveLength(10);
    for (const kept of Object.values(PANEL_ACTION_STORAGE)) expect(["tab", "browser"]).toContain(kept);
  });

  it("starts in the normal state: side panel open and normal, timeline folded, the default order, only the Inspector open, the default sizes", () => {
    const state = open().getState();
    expect(state.sideMode).toBe("normal");
    expect(state.timelineOpen).toBe(false);
    expect(state.order).toEqual([...SIDE_PANEL_IDS]);
    expect(state.folded).toEqual(DEFAULT_FOLDED);
    expect(state.sideWidth).toBe(DEFAULT_SIDE_WIDTH);
    expect(state.timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
    expect(state.panelHeights).toEqual({});
  });

  it("hide-and-show-the-side-panel-by-keyboard", () => {
    const store = open();
    store.actions.hideSidePanel();
    expect(store.getState().sideMode).toBe("collapsed");
    store.actions.showSidePanel();
    expect(store.getState().sideMode).toBe("normal");
  });

  it("open-the-side-panel-to-the-full-width-and-return-by-keyboard", () => {
    const store = open();
    store.actions.openSidePanelFullWidth();
    expect(store.getState().sideMode).toBe("full");
    store.actions.returnSidePanelToNormalWidth();
    expect(store.getState().sideMode).toBe("normal");
  });

  it("hide-and-show-the-timeline-by-keyboard", () => {
    const store = open();
    store.actions.showTimeline();
    expect(store.getState().timelineOpen).toBe(true);
    store.actions.hideTimeline();
    expect(store.getState().timelineOpen).toBe(false);
  });

  it("move-a-side-panel-up-and-down-by-keyboard", () => {
    const store = open();
    store.actions.moveSidePanel("query-builder", "up");
    expect(store.getState().order).toEqual(["inspector", "query-builder", "metrics", "connections"]);
    store.actions.moveSidePanel("query-builder", "down");
    expect(store.getState().order).toEqual([...SIDE_PANEL_IDS]);
    // At the ends nothing changes, and nothing throws.
    store.actions.moveSidePanel("inspector", "up");
    store.actions.moveSidePanel("connections", "down");
    expect(store.getState().order).toEqual([...SIDE_PANEL_IDS]);
  });

  it("move-a-side-panel-with-alt-arrows-by-keyboard: the same move, from the header's own keys, and a drop on another slot", () => {
    const store = open();
    store.actions.moveSidePanelByKey("metrics", { key: "ArrowDown", altKey: true });
    expect(store.getState().order).toEqual(["inspector", "query-builder", "metrics", "connections"]);
    store.actions.moveSidePanelByKey("metrics", { key: "ArrowUp", altKey: true });
    expect(store.getState().order).toEqual([...SIDE_PANEL_IDS]);
    // An arrow with no Alt is not a move.
    store.actions.moveSidePanelByKey("metrics", { key: "ArrowDown", altKey: false });
    expect(store.getState().order).toEqual([...SIDE_PANEL_IDS]);
    store.actions.dropSidePanelOn("connections", "inspector");
    expect(store.getState().order[0]).toBe("connections");
  });

  it("fold-a-side-panel-by-keyboard", () => {
    const store = open();
    store.actions.toggleFold("metrics");
    expect(store.getState().folded).not.toContain("metrics");
    store.actions.toggleFold("inspector");
    expect(store.getState().folded).toContain("inspector");
    store.actions.toggleFold("inspector");
    expect(store.getState().folded).not.toContain("inspector");
  });

  it("resize-the-side-panel-by-keyboard: arrows move it 16 pixels, Shift 64, Home resets", () => {
    const store = open();
    expect([SASH_STEP, SASH_LARGE_STEP]).toEqual([16, 64]);
    store.actions.resizeByKey("side-width", { key: "ArrowLeft", shiftKey: false });
    expect(store.getState().sideWidth).toBe(DEFAULT_SIDE_WIDTH + 16);
    store.actions.resizeByKey("side-width", { key: "ArrowLeft", shiftKey: true });
    expect(store.getState().sideWidth).toBe(DEFAULT_SIDE_WIDTH + 16 + 64);
    store.actions.resizeByKey("side-width", { key: "ArrowRight", shiftKey: false });
    expect(store.getState().sideWidth).toBe(DEFAULT_SIDE_WIDTH + 64);
    store.actions.resizeByKey("side-width", { key: "Home", shiftKey: false });
    expect(store.getState().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
    store.actions.setSideWidth(400);
    expect(store.getState().sideWidth).toBe(400);
  });

  it("resize-a-stacked-panel-by-keyboard: a height of its own, and Home lets it share again", () => {
    const store = open();
    store.actions.resizeByKey("panel-height", { key: "ArrowDown", shiftKey: false }, { panel: "metrics", from: 200 });
    expect(store.getState().panelHeights).toEqual({ metrics: 216 });
    store.actions.resizeByKey("panel-height", { key: "ArrowUp", shiftKey: true }, { panel: "metrics", from: 216 });
    expect(store.getState().panelHeights).toEqual({ metrics: 152 });
    store.actions.resizeByKey("panel-height", { key: "Home", shiftKey: false }, { panel: "metrics", from: 152 });
    expect(store.getState().panelHeights).toEqual({});
  });

  it("resize-the-timeline-by-keyboard: raised with the up arrow, lowered with the down arrow, Home resets, never above its bound", () => {
    const store = open();
    store.actions.resizeByKey("timeline-height", { key: "ArrowUp", shiftKey: false });
    expect(store.getState().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT + 16);
    store.actions.resizeByKey("timeline-height", { key: "ArrowDown", shiftKey: false });
    expect(store.getState().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
    store.actions.setTimelineHeight(400, { maxPx: 280 });
    expect(store.getState().timelineHeight).toBe(280);
    store.actions.resizeByKey("timeline-height", { key: "Home", shiftKey: false });
    expect(store.getState().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
  });

  it("close-and-open-the-details-panel-by-keyboard: the toolbar's Details toggles the side panel", () => {
    const store = open();
    store.actions.toggleDetails();
    expect(store.getState().sideMode).toBe("collapsed");
    store.actions.toggleDetails();
    expect(store.getState().sideMode).toBe("normal");
    store.actions.openSidePanelFullWidth();
    store.actions.toggleDetails();
    expect(store.getState().sideMode).toBe("collapsed");
  });

  it("a subscriber is told of each change, and not after it has stopped", () => {
    const store = open();
    const seen: string[] = [];
    const stop = store.subscribe((state) => seen.push(state.sideMode));
    store.actions.hideSidePanel();
    store.actions.showSidePanel();
    stop();
    store.actions.hideSidePanel();
    expect(seen).toEqual(["collapsed", "normal"]);
  });

  it("a narrow viewport opens the side panel closed, as spec/02 says (below 1200 pixels)", () => {
    vi.stubGlobal("window", { innerWidth: 900 });
    expect(open().getState().sideMode).toBe("collapsed");
  });
});

// ------------------------------------------------------------------------------------------------ a reload

describe("a reload: what is kept in this browser survives, hide and show does not", () => {
  it("the actions declared 'browser' are the order, the fold and the sizes, and the others are the hide and show", () => {
    const browser = Object.entries(PANEL_ACTION_STORAGE).filter(([, kept]) => kept === "browser").map(([id]) => id);
    expect(browser.sort()).toEqual(
      [
        "fold-a-side-panel-by-keyboard",
        "move-a-side-panel-up-and-down-by-keyboard",
        "move-a-side-panel-with-alt-arrows-by-keyboard",
        "resize-a-stacked-panel-by-keyboard",
        "resize-the-side-panel-by-keyboard",
        "resize-the-timeline-by-keyboard",
      ].sort(),
    );
  });

  it("the order survives, under the existing key", () => {
    const store = open();
    store.actions.moveSidePanel("connections", "up");
    expect(JSON.parse(localStorage.getItem(SIDE_PANEL_ORDER_KEY) ?? "null")).toEqual(store.getState().order);
    expect(reload().getState().order).toEqual(["inspector", "metrics", "connections", "query-builder"]);
  });

  it("the fold survives, under the key the workspace already uses", () => {
    expect(FOLDED_PANELS_KEY).toBe("ospreyflow.side-panels-folded");
    const store = open();
    store.actions.toggleFold("query-builder");
    store.actions.toggleFold("inspector");
    // Query builder opened, Inspector folded: held in the panels' default order whatever order they were pressed in.
    expect(reload().getState().folded).toEqual(["inspector", "metrics", "connections"]);
  });

  it("the three sizes survive, under the existing key", () => {
    const store = open();
    store.actions.setSideWidth(420);
    store.actions.setPanelHeight("metrics", 180);
    store.actions.setTimelineHeight(200);
    expect(LAYOUT_SIZES_KEY).toBe("ospreyflow.layout-sizes");
    expect(JSON.parse(localStorage.getItem(LAYOUT_SIZES_KEY) ?? "null")).toMatchObject({ sideWidth: 420, timelineHeight: 200 });
    const state = reload().getState();
    expect([state.sideWidth, state.timelineHeight, state.panelHeights]).toEqual([420, 200, { metrics: 180 }]);
  });

  it("hide and show is not stored: after a reload each panel is in its normal state, and nothing about it is in storage", () => {
    const store = open();
    store.actions.hideSidePanel();
    store.actions.showTimeline();
    store.actions.openSidePanelFullWidth();
    const written = [...(localStorage as unknown as MemoryStorage).items.entries()].map(([key, value]) => `${key}=${value}`).join("\n");
    expect(written).not.toMatch(/collapsed|full|timelineOpen|sideMode|"open"/);
    const state = reload().getState();
    expect([state.sideMode, state.timelineOpen]).toEqual(["normal", false]);
  });

  it("a hide and a reload do not lose the order, the fold or the sizes already kept", () => {
    const store = open();
    store.actions.moveSidePanel("metrics", "down");
    store.actions.setSideWidth(380);
    store.actions.hideSidePanel();
    const state = reload().getState();
    expect([state.order[1], state.sideWidth, state.sideMode]).toEqual(["query-builder", 380, "normal"]);
  });
});

// --------------------------------------------------------------------------------------------- the minimum

describe("the minimum side width is 300", () => {
  it("is 300 in the code", () => {
    expect(MIN_SIDE_WIDTH).toBe(300);
  });

  it("a width below it is raised to it, not refused, and kept", () => {
    const store = open();
    store.actions.setSideWidth(250);
    expect(store.getState().sideWidth).toBe(300);
    store.actions.setSideWidth(0);
    expect(store.getState().sideWidth).toBe(300);
    expect(reload().getState().sideWidth).toBe(300);
  });

  it("the arrow keys cannot take the column under it either", () => {
    const store = open();
    store.actions.setSideWidth(300);
    store.actions.resizeByKey("side-width", { key: "ArrowRight", shiftKey: true });
    expect(store.getState().sideWidth).toBe(300);
  });

  it("a width above the widest the page allows is held there, and the widest never goes below the minimum", () => {
    const store = open();
    store.actions.setSideWidth(900);
    expect(store.getState().sideWidth).toBe(480);
    store.actions.setSideWidth(900, { maxPx: 360 });
    expect(store.getState().sideWidth).toBe(360);
    store.actions.setSideWidth(900, { maxPx: 200 });
    expect(store.getState().sideWidth).toBe(300);
  });

  it("a stored width below it is read raised, and a size that is not a number is ignored", () => {
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 240, timelineHeight: "tall" }));
    const state = open().getState();
    expect([state.sideWidth, state.timelineHeight]).toEqual([300, DEFAULT_TIMELINE_HEIGHT]);
  });

  it("a value that is not a finite number sets nothing", () => {
    const store = open();
    store.actions.setSideWidth(Number.NaN);
    store.actions.setTimelineHeight(Number.POSITIVE_INFINITY);
    store.actions.setPanelHeight("metrics", Number.NaN);
    const state = store.getState();
    expect([state.sideWidth, state.timelineHeight, state.panelHeights]).toEqual([DEFAULT_SIDE_WIDTH, DEFAULT_TIMELINE_HEIGHT, {}]);
  });
});

// -------------------------------------------------------------------------------------- corrupt and missing

describe("a corrupt or missing stored value is ignored and a normal state is used; the store never throws", () => {
  const corrupt = ["{not json", "null", "42", '"text"', "[1,2", "{}", "[[]]"];

  it.each(corrupt)("a corrupt value %s under each key: the normal state, no throw", (value) => {
    localStorage.setItem(LAYOUT_SIZES_KEY, value);
    localStorage.setItem(SIDE_PANEL_ORDER_KEY, value);
    localStorage.setItem(FOLDED_PANELS_KEY, value);
    const state = open().getState();
    expect(state.order).toEqual([...SIDE_PANEL_IDS]);
    expect(state.folded).toEqual(DEFAULT_FOLDED);
    expect([state.sideWidth, state.timelineHeight]).toEqual([DEFAULT_SIDE_WIDTH, DEFAULT_TIMELINE_HEIGHT]);
    expect(state.panelHeights).toEqual({});
  });

  it("a stored fold that is valid JSON but not a list is the normal fold, not 'everything open'", () => {
    localStorage.setItem(FOLDED_PANELS_KEY, '{"metrics":true}');
    expect(open().getState().folded).toEqual(DEFAULT_FOLDED);
  });

  it("a stored fold keeps the panels it knows, once each, and drops the rest; an empty list is a real choice (all open)", () => {
    localStorage.setItem(FOLDED_PANELS_KEY, JSON.stringify(["metrics", "metrics", "nonsense", 7, "inspector"]));
    expect(open().getState().folded).toEqual(["inspector", "metrics"]);
    localStorage.setItem(FOLDED_PANELS_KEY, "[]");
    expect(reload().getState().folded).toEqual([]);
  });

  it("a stored order that lacks a panel or repeats one is mended, never losing or duplicating a panel", () => {
    localStorage.setItem(SIDE_PANEL_ORDER_KEY, JSON.stringify(["connections", "connections", "ghost"]));
    expect(open().getState().order).toEqual(["connections", "inspector", "metrics", "query-builder"]);
  });

  it("no storage at all (the property throws, as in a private window): state is kept in memory and nothing throws", () => {
    blockStorage();
    const store = open();
    expect(() => {
      store.actions.moveSidePanel("metrics", "down");
      store.actions.toggleFold("inspector");
      store.actions.setSideWidth(410);
      store.actions.setPanelHeight("metrics", 120);
      store.actions.setTimelineHeight(150);
      store.actions.hideSidePanel();
    }).not.toThrow();
    const state = store.getState();
    expect(state.order[1]).toBe("query-builder");
    expect(state.folded).toContain("inspector");
    expect([state.sideWidth, state.timelineHeight, state.panelHeights, state.sideMode]).toEqual([410, 150, { metrics: 120 }, "collapsed"]);
  });

  it("no storage global at all: the same", () => {
    vi.unstubAllGlobals();
    delete (globalThis as { localStorage?: unknown }).localStorage;
    const store = open();
    expect(() => {
      store.actions.toggleFold("metrics");
      store.actions.setSideWidth(333);
    }).not.toThrow();
    expect(store.getState().sideWidth).toBe(333);
  });

  it("a full storage (every write refused): the change is still made, in memory, and nothing throws", () => {
    installStorage(new FullStorage());
    const store = open();
    expect(() => {
      store.actions.moveSidePanel("metrics", "down");
      store.actions.toggleFold("metrics");
      store.actions.setSideWidth(350);
    }).not.toThrow();
    const state = store.getState();
    expect([state.order[1], state.folded.includes("metrics"), state.sideWidth]).toEqual(["query-builder", false, 350]);
  });

  it("an action given a panel it does not know changes nothing and does not throw", () => {
    const store = open();
    const before = JSON.stringify(store.getState());
    expect(() => {
      store.actions.toggleFold("ghost" as never);
      store.actions.moveSidePanel("ghost" as never, "up");
      store.actions.setPanelHeight("ghost" as never, 100);
    }).not.toThrow();
    expect(JSON.stringify(store.getState())).toBe(before);
  });
});

// ----------------------------------------------------------------------------------------------- the attach

type Listener = (event: FakeEvent) => void;
interface FakeEvent {
  type: string;
  target: FakeElement;
  key?: string;
  altKey?: boolean;
  shiftKey?: boolean;
  defaultPrevented: boolean;
  preventDefault(): void;
}

/** What the page's element does that the attach function touches. `style` refuses every write, as the rule does. */
class FakeElement {
  readonly attributes = new Map<string, string>();
  readonly classes = new Set<string>();
  readonly children: FakeElement[] = [];
  readonly listeners = new Map<string, Listener[]>();
  readonly styleWrites: string[] = [];
  parent: FakeElement | null = null;
  readonly classList = {
    add: (...names: string[]) => names.forEach((name) => this.classes.add(name)),
    remove: (...names: string[]) => names.forEach((name) => this.classes.delete(name)),
    toggle: (name: string, force?: boolean) => {
      const on = force ?? !this.classes.has(name);
      if (on) this.classes.add(name);
      else this.classes.delete(name);
      return on;
    },
    contains: (name: string) => this.classes.has(name),
  };
  readonly style: Record<string, string>;

  constructor(
    readonly tag: string,
    attributes: Record<string, string> = {},
  ) {
    for (const [name, value] of Object.entries(attributes)) this.attributes.set(name, value);
    this.style = new Proxy({} as Record<string, string>, {
      set: (_target, property) => {
        this.styleWrites.push(String(property));
        return true;
      },
    });
  }
  append(...nodes: FakeElement[]): void {
    for (const node of nodes) {
      node.parent?.children.splice(node.parent.children.indexOf(node), 1);
      node.parent = this;
      this.children.push(node);
    }
  }
  setAttribute(name: string, value: string): void {
    if (name === "style") this.styleWrites.push("setAttribute(style)");
    this.attributes.set(name, value);
  }
  getAttribute(name: string): string | null {
    return this.attributes.get(name) ?? null;
  }
  removeAttribute(name: string): void {
    this.attributes.delete(name);
  }
  hasAttribute(name: string): boolean {
    return this.attributes.has(name);
  }
  set hidden(value: boolean) {
    if (value) this.attributes.set("hidden", "");
    else this.attributes.delete("hidden");
  }
  get hidden(): boolean {
    return this.attributes.has("hidden");
  }
  /** This element and each ancestor, nearest first. */
  chain(): FakeElement[] {
    const out: FakeElement[] = [this];
    for (let up = this.parent; up; up = up.parent) out.push(up);
    return out;
  }
  contains(node: FakeElement | null): boolean {
    return node !== null && node.chain().includes(this);
  }
  closest(selector: string): FakeElement | null {
    const name = /^\[([a-z-]+)\]$/.exec(selector)?.[1];
    return this.chain().find((at) => name !== undefined && at.attributes.has(name)) ?? null;
  }
  querySelectorAll(selector: string): FakeElement[] {
    const match = /^\[([a-z-]+)(?:="([^"]*)")?\]$/.exec(selector);
    const found: FakeElement[] = [];
    const walk = (node: FakeElement) => {
      for (const child of node.children) {
        if (match && child.attributes.has(match[1] as string) && (match[2] === undefined || child.attributes.get(match[1] as string) === match[2])) found.push(child);
        walk(child);
      }
    };
    walk(this);
    return found;
  }
  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  removeEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, (this.listeners.get(type) ?? []).filter((other) => other !== listener));
  }
  /** What a browser does: the event starts at the target and is heard by every listener on the way up. */
  dispatch(type: string, init: Partial<FakeEvent> = {}): FakeEvent {
    const event: FakeEvent = {
      type,
      target: this,
      defaultPrevented: false,
      preventDefault() {
        this.defaultPrevented = true;
      },
      ...init,
    };
    for (const at of this.chain()) (at.listeners.get(type) ?? []).slice().forEach((listener) => listener(event));
    return event;
  }
}

function page() {
  const root = new FakeElement("div", { "data-panel-frame-root": "" });
  const side = new FakeElement("aside", { "data-panel-frame": "side" });
  const timeline = new FakeElement("section", { "data-panel-frame": "timeline" });
  const slots = Object.fromEntries(SIDE_PANEL_IDS.map((id) => [id, new FakeElement("div", { "data-panel-slot": id })])) as Record<(typeof SIDE_PANEL_IDS)[number], FakeElement>;
  const body = Object.fromEntries(SIDE_PANEL_IDS.map((id) => [id, new FakeElement("div", { "data-panel-body": id })])) as Record<(typeof SIDE_PANEL_IDS)[number], FakeElement>;
  const button = (action: string, extra: Record<string, string> = {}) => new FakeElement("button", { "data-action": action, ...extra });
  const controls = {
    hide: button("hide-side-panel"),
    show: button("show-side-panel"),
    full: button("open-side-panel-full-width"),
    normal: button("return-side-panel-to-normal-width"),
    hideTimeline: button("hide-timeline"),
    showTimeline: button("show-timeline"),
    details: button("toggle-details"),
    foldMetrics: button("toggle-fold", { "data-panel": "metrics" }),
    moveUp: button("move-side-panel-up", { "data-panel": "metrics" }),
    moveDown: button("move-side-panel-down", { "data-panel": "metrics" }),
    unknown: button("make-it-pink"),
    sideSash: button("resize", { "data-sash": "side-width" }),
    panelSash: button("resize", { "data-sash": "panel-height", "data-panel": "metrics", "data-from": "200" }),
    timelineSash: button("resize", { "data-sash": "timeline-height" }),
  };
  const header = new FakeElement("div", { "data-panel-header": "metrics" });
  for (const id of SIDE_PANEL_IDS) slots[id].append(body[id]);
  slots.metrics.append(header);
  side.append(...SIDE_PANEL_IDS.map((id) => slots[id]));
  root.append(side, timeline, ...Object.values(controls));
  return { root, side, timeline, slots, body, header, controls };
}

describe("attach: wiring data-action elements to the store, no style set", () => {
  it("each control does what its action does, through one delegated listener on the root it was given", () => {
    const { root, side, timeline, controls, body } = page();
    const store = open();
    const detach = attachPanelFrame(root as unknown as PanelFrameRoot, store);
    expect(root.listeners.get("click")).toHaveLength(1);
    expect(root.listeners.get("keydown")).toHaveLength(1);
    expect(controls.hide.listeners.size).toBe(0);

    controls.hide.dispatch("click");
    expect(store.getState().sideMode).toBe("collapsed");
    expect(side.getAttribute("data-panel-mode")).toBe("collapsed");
    controls.show.dispatch("click");
    expect(side.getAttribute("data-panel-mode")).toBe("normal");
    controls.full.dispatch("click");
    expect(side.getAttribute("data-panel-mode")).toBe("full");
    controls.normal.dispatch("click");
    controls.showTimeline.dispatch("click");
    expect(timeline.getAttribute("data-panel-open")).toBe("true");
    controls.hideTimeline.dispatch("click");
    expect(timeline.getAttribute("data-panel-open")).toBe("false");
    controls.details.dispatch("click");
    expect(store.getState().sideMode).toBe("collapsed");
    controls.details.dispatch("click");
    controls.foldMetrics.dispatch("click");
    expect(store.getState().folded).not.toContain("metrics");
    expect(body.metrics.hidden).toBe(false);
    expect(body.inspector.hidden).toBe(false);
    expect(body["query-builder"].hidden).toBe(true);
    controls.moveDown.dispatch("click");
    expect(store.getState().order).toEqual(["inspector", "query-builder", "metrics", "connections"]);
    controls.moveUp.dispatch("click");
    expect(store.getState().order).toEqual([...SIDE_PANEL_IDS]);
    detach();
  });

  it("a button inside a control (the click lands on a child) is still the control's", () => {
    const { root, controls } = page();
    const store = open();
    attachPanelFrame(root as unknown as PanelFrameRoot, store);
    const label = new FakeElement("span");
    controls.hide.append(label);
    label.dispatch("click");
    expect(store.getState().sideMode).toBe("collapsed");
  });

  it("the keyboard: Alt+Arrow on a panel's header moves it, and the sashes' arrow keys and Home resize", () => {
    const { root, header, controls } = page();
    const store = open();
    attachPanelFrame(root as unknown as PanelFrameRoot, store);
    const down = header.dispatch("keydown", { key: "ArrowDown", altKey: true });
    expect(down.defaultPrevented).toBe(true);
    expect(store.getState().order).toEqual(["inspector", "query-builder", "metrics", "connections"]);
    header.dispatch("keydown", { key: "ArrowUp", altKey: true });
    expect(store.getState().order).toEqual([...SIDE_PANEL_IDS]);
    const plain = header.dispatch("keydown", { key: "ArrowUp", altKey: false });
    expect(plain.defaultPrevented).toBe(false);
    controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: false });
    expect(store.getState().sideWidth).toBe(DEFAULT_SIDE_WIDTH + 16);
    controls.sideSash.dispatch("keydown", { key: "Home" });
    expect(store.getState().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
    controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    expect(store.getState().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT + 64);
    controls.panelSash.dispatch("keydown", { key: "ArrowDown", shiftKey: false });
    expect(store.getState().panelHeights).toEqual({ metrics: 216 });
    expect(controls.panelSash.getAttribute("aria-valuenow")).toBe("216");
  });

  it("wires only elements it is given: an element outside the root, an unknown action and an element with no action do nothing", () => {
    const { root, controls } = page();
    const store = open();
    attachPanelFrame(root as unknown as PanelFrameRoot, store);
    const outside = new FakeElement("button", { "data-action": "hide-side-panel" });
    outside.dispatch("click");
    expect(store.getState().sideMode).toBe("normal");
    const before = JSON.stringify(store.getState());
    controls.unknown.dispatch("click");
    new FakeElement("button").dispatch("click");
    const plainInside = new FakeElement("p");
    root.append(plainInside);
    plainInside.dispatch("click");
    expect(JSON.stringify(store.getState())).toBe(before);
    // A control with an action that needs a panel and names none, or one it does not know: nothing.
    const nameless = new FakeElement("button", { "data-action": "toggle-fold" });
    const ghost = new FakeElement("button", { "data-action": "toggle-fold", "data-panel": "ghost" });
    root.append(nameless, ghost);
    expect(() => {
      nameless.dispatch("click");
      ghost.dispatch("click");
    }).not.toThrow();
    expect(JSON.stringify(store.getState())).toBe(before);
  });

  it("detaching removes both listeners: a later click does nothing", () => {
    const { root, controls } = page();
    const store = open();
    const detach = attachPanelFrame(root as unknown as PanelFrameRoot, store);
    detach();
    expect(root.listeners.get("click")).toHaveLength(0);
    expect(root.listeners.get("keydown")).toHaveLength(0);
    controls.hide.dispatch("click");
    expect(store.getState().sideMode).toBe("normal");
  });

  it("draws the state it is given at once (a reload's kept order, fold and sizes) and again on each change", () => {
    const first = open();
    first.actions.moveSidePanel("connections", "up");
    first.actions.toggleFold("query-builder");
    first.actions.setSideWidth(420);
    const { root, side, slots, body } = page();
    const store = open();
    attachPanelFrame(root as unknown as PanelFrameRoot, store);
    expect(side.getAttribute("data-side-width")).toBe("420");
    expect(body["query-builder"].hidden).toBe(false);
    expect(body.metrics.hidden).toBe(true);
    expect(slots.metrics.getAttribute("aria-expanded") ?? slots.metrics.getAttribute("data-folded")).toBe("true");
    expect(side.children.map((child) => child.getAttribute("data-panel-slot"))).toEqual(["inspector", "metrics", "connections", "query-builder"]);
  });

  it("sets no style: every action, the draw and a detach leave no write to `style` and no style attribute", () => {
    const { root, side, timeline, slots, body, header, controls } = page();
    const store = open();
    const detach = attachPanelFrame(root as unknown as PanelFrameRoot, store);
    for (const control of Object.values(controls)) control.dispatch("click");
    header.dispatch("keydown", { key: "ArrowDown", altKey: true });
    for (const sash of [controls.sideSash, controls.panelSash, controls.timelineSash]) {
      for (const key of ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home"]) sash.dispatch("keydown", { key, shiftKey: true });
    }
    detach();
    const everything = [root, side, timeline, ...Object.values(slots), ...Object.values(body), header, ...Object.values(controls)];
    expect(everything.flatMap((element) => element.styleWrites)).toEqual([]);
    expect(everything.filter((element) => element.hasAttribute("style"))).toEqual([]);
  });

  it("the stand-in does refuse a style: a planted `element.style.width` write and a planted setAttribute('style') are both seen", () => {
    const element = new FakeElement("div");
    element.style.width = "340px";
    element.setAttribute("style", "width: 340px");
    expect(element.styleWrites).toEqual(["width", "setAttribute(style)"]);
  });

  it("an attach given no listener to add (a stand-in with neither method) is refused in words, not by a TypeError later", () => {
    expect(() => attachPanelFrame({} as unknown as PanelFrameRoot, open())).toThrow(/addEventListener/);
  });
});

// ------------------------------------------------------------- the upper limits, from the live window (rounds 2 and 3)

// What the spec table says the frame holds: the timeline between 96px and seven tenths of the window; the column between
// 300 and 480 and leaving the canvas 320; a stacked panel no taller than the window. The store reads the window itself
// at each resize through one injectable function, so a call that omits `maxPx`, and a page whose markup cannot know the
// window's height, are both held.
//
// Round 3: these cases read what a page would see, and never repair it first. `store.getState()` itself brings every size
// down to today's limit (it calls the store's `enforce()`), writes it and redraws, so an assertion made through it
// repairs the very fault it is meant to catch. A real page never calls it after a key press: the attach draws from the
// subscribe path. So each case below reads, straight after the key press and before any `getState()`:
//   - `held()`    the sizes in memory, from `layoutSizes.getLayoutSizes()`, which enforces nothing;
//   - `stored()`  the value in `ospreyflow.layout-sizes`;
//   - the sash's `aria-valuenow` and the frame's data attribute, which the attach drew from the subscribe path.
// `getState()` is used only where a case is about `getState()` itself (named in its title).
// Planted, each shown red on its own (the figures are in the commit message): the keyboard path's clamp removed with
// `enforce()` left in `getState()`; `enforce()` taken out of `resizeByKey`; the three setters unclamped by the live
// limit; the live limit alone removed with `data-max` left in.
describe("the upper limits come from the live window, through the attach path, at each key press", () => {
  let windowHeight = 800;
  let workWidth = 1000;
  const viewport = () => ({ windowHeight, workWidth });
  const stored = () => JSON.parse(localStorage.getItem(LAYOUT_SIZES_KEY) ?? "{}") as { sideWidth?: number; timelineHeight?: number; panelHeights?: Record<string, number> };
  /** The sizes in memory, read without enforcing anything (unlike `store.getState()`). */
  const held = () => getLayoutSizes();
  const attached = () => {
    windowHeight = 800;
    workWidth = 1000;
    const parts = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    return { ...parts, store };
  };

  it("repeated ArrowUp on the timeline sash stops at seven tenths of the window, and the stored value never exceeds it", () => {
    const { controls, timeline } = attached();
    for (let press = 0; press < 80; press += 1) {
      controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: press % 2 === 0 });
      // Straight after the press: what is in memory, what is stored and what is drawn, none of it repaired by a read.
      expect(held().timelineHeight, `memory after press ${press}`).toBeLessThanOrEqual(560);
      expect(stored().timelineHeight ?? 0, `stored after press ${press}`).toBeLessThanOrEqual(560);
      expect(Number(controls.timelineSash.getAttribute("aria-valuenow")), `aria-valuenow after press ${press}`).toBeLessThanOrEqual(560);
      expect(Number(timeline.getAttribute("data-timeline-height")), `data-timeline-height after press ${press}`).toBeLessThanOrEqual(560);
    }
    expect(held().timelineHeight).toBe(560);
    expect(stored().timelineHeight).toBe(560);
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("560");
    expect(timeline.getAttribute("data-timeline-height")).toBe("560");
    // A reload under the same window keeps it; a store given no function reads the real window, which a test has none of.
    forgetLayoutSizesForTest();
    const again = createPanelFrameStore({ viewport });
    live.push(again);
    expect(held().timelineHeight).toBe(560);
  });

  it("one press from just under the limit does not pass it: 559 and ArrowUp is 560, not 575, in memory, in storage and as drawn", () => {
    const { controls, timeline, store } = attached();
    store.actions.setTimelineHeight(559);
    expect(held().timelineHeight).toBe(559);
    controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: false });
    expect(held().timelineHeight).toBe(560);
    expect(stored().timelineHeight).toBe(560);
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("560");
    expect(timeline.getAttribute("data-timeline-height")).toBe("560");
  });

  it("a page's own data-max on the sash may lower the limit and never lift it", () => {
    const { controls, timeline } = attached();
    controls.timelineSash.setAttribute("data-max", "300");
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    expect(held().timelineHeight).toBe(300);
    expect(stored().timelineHeight).toBe(300);
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("300");
    // A data-max above the window's limit lifts nothing: it goes to 560 and stops, in memory, in storage and as drawn.
    controls.timelineSash.setAttribute("data-max", "5000");
    for (let press = 0; press < 20; press += 1) {
      controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
      expect(held().timelineHeight, `memory after press ${press}`).toBeLessThanOrEqual(560);
      expect(stored().timelineHeight ?? 0, `stored after press ${press}`).toBeLessThanOrEqual(560);
    }
    expect(held().timelineHeight).toBe(560);
    expect(stored().timelineHeight).toBe(560);
    expect(timeline.getAttribute("data-timeline-height")).toBe("560");
  });

  it("an explicit maxPx given to an action may only lower the limit: set above the window's, it is held at the window's", () => {
    const { store } = attached();
    store.actions.setTimelineHeight(9000, { maxPx: 9000 });
    expect(held().timelineHeight).toBe(560);
    expect(stored().timelineHeight).toBe(560);
    store.actions.setSideWidth(9000, { maxPx: 9000 });
    expect(held().sideWidth).toBe(480);
    expect(stored().sideWidth).toBe(480);
    store.actions.setPanelHeight("metrics", 9000, { maxPx: 9000 });
    expect(held().panelHeights.metrics).toBe(800);
    expect(stored().panelHeights?.metrics).toBe(800);
    // And lowered: a maxPx under the limit is the limit.
    store.actions.setTimelineHeight(9000, { maxPx: 200 });
    expect(held().timelineHeight).toBe(200);
  });

  it("repeated ArrowLeft on the column's sash stops at 480, or where the canvas keeps 320 of the work area", () => {
    const wide = attached();
    for (let press = 0; press < 40; press += 1) {
      wide.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
      expect(held().sideWidth, `memory after press ${press}`).toBeLessThanOrEqual(480);
    }
    expect(held().sideWidth).toBe(480);
    expect(stored().sideWidth).toBe(480);
    wide.store.actions.resizeByKey("side-width", { key: "Home" });

    // A 700px work area: 700 - 320 = 380 for the column, under 480. The 480 above is not the limit that holds here.
    workWidth = 700;
    for (let press = 0; press < 40; press += 1) {
      wide.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: press % 2 === 0 });
      expect(700 - held().sideWidth, `canvas left in memory after press ${press}`).toBeGreaterThanOrEqual(320);
      expect(700 - (stored().sideWidth ?? 0), `canvas left in storage after press ${press}`).toBeGreaterThanOrEqual(320);
      expect(700 - Number(wide.controls.sideSash.getAttribute("aria-valuenow")), `canvas left as drawn after press ${press}`).toBeGreaterThanOrEqual(320);
      expect(700 - Number(wide.side.getAttribute("data-side-width")), `data-side-width after press ${press}`).toBeGreaterThanOrEqual(320);
    }
    expect(held().sideWidth).toBe(380);
    expect(stored().sideWidth).toBe(380);
    expect(wide.controls.sideSash.getAttribute("aria-valuenow")).toBe("380");

    // So small a work area that 320 for the canvas cannot be kept: the column never goes under 300.
    workWidth = 500;
    for (let press = 0; press < 5; press += 1) wide.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    expect(held().sideWidth).toBe(300);
    expect(stored().sideWidth).toBe(300);
    expect(wide.controls.sideSash.getAttribute("aria-valuenow")).toBe("300");
  });

  it("repeated ArrowDown on a stacked panel's sash stops at the window's height", () => {
    const { controls } = attached();
    for (let press = 0; press < 40; press += 1) {
      controls.panelSash.dispatch("keydown", { key: "ArrowDown", shiftKey: true });
      expect(held().panelHeights.metrics ?? 0, `memory after press ${press}`).toBeLessThanOrEqual(800);
      expect(stored().panelHeights?.metrics ?? 0, `stored after press ${press}`).toBeLessThanOrEqual(800);
      expect(Number(controls.panelSash.getAttribute("aria-valuenow")), `aria-valuenow after press ${press}`).toBeLessThanOrEqual(800);
    }
    expect(held().panelHeights.metrics).toBe(800);
    expect(stored().panelHeights?.metrics).toBe(800);
  });

  it("a shrinking window brings a stored size down on the next key press, as stored and as drawn, before any read", () => {
    const { controls, timeline, side } = attached();
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    for (let press = 0; press < 20; press += 1) controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    expect([held().timelineHeight, held().sideWidth]).toEqual([560, 480]);
    expect([stored().timelineHeight, stored().sideWidth]).toEqual([560, 480]);

    windowHeight = 500;
    workWidth = 650;
    // ArrowUp would have grown 560 to 576 against the old window; against this one it is held at 350.
    controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: false });
    expect(held().timelineHeight).toBe(350);
    expect(stored().timelineHeight).toBe(350);
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("350");
    expect(timeline.getAttribute("data-timeline-height")).toBe("350");
    controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: false });
    expect(held().sideWidth).toBe(330);
    expect(stored().sideWidth).toBe(330);
    expect(controls.sideSash.getAttribute("aria-valuenow")).toBe("330");
    expect(side.getAttribute("data-side-width")).toBe("330");
  });

  it("a shrinking window brings a stored size down on a key press that is not itself a resize (the press enforces, whatever it is)", () => {
    // ArrowDown or ArrowUp would be brought down by the setter's own clamp; a key that moves nothing is where only the
    // enforcing at the start of a key press can bring a size down.
    const { controls, timeline, side } = attached();
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    for (let press = 0; press < 20; press += 1) controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    expect([held().timelineHeight, held().sideWidth]).toEqual([560, 480]);

    windowHeight = 500;
    workWidth = 650;
    controls.timelineSash.dispatch("keydown", { key: "PageUp" });
    expect(held().timelineHeight).toBe(350);
    expect(stored().timelineHeight).toBe(350);
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("350");
    expect(timeline.getAttribute("data-timeline-height")).toBe("350");
    controls.sideSash.dispatch("keydown", { key: "PageUp" });
    expect(held().sideWidth).toBe(330);
    expect(stored().sideWidth).toBe(330);
    expect(controls.sideSash.getAttribute("aria-valuenow")).toBe("330");
    expect(side.getAttribute("data-side-width")).toBe("330");
  });

  it("a stored size above today's limit is read brought down, in memory and in storage; a corrupt one is ignored", () => {
    windowHeight = 500;
    workWidth = 650;
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 480, timelineHeight: 4000, panelHeights: { metrics: 9000, inspector: 120 } }));
    // A page that goes away leaves its listeners behind in other tests; a reload is a read from storage afresh.
    forgetLayoutSizesForTest();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    // Made, not asked: the store brought the stored sizes down when it was made, so no read has to.
    expect([held().timelineHeight, held().sideWidth]).toEqual([350, 330]);
    expect(held().panelHeights).toEqual({ metrics: 500, inspector: 120 });
    expect(stored().timelineHeight).toBe(350);
    expect(stored().sideWidth).toBe(330);
    expect(stored().panelHeights).toEqual({ metrics: 500, inspector: 120 });
    const state = store.getState();
    expect([state.timelineHeight, state.sideWidth]).toEqual([350, 330]);
    expect(state.panelHeights).toEqual({ metrics: 500, inspector: 120 });

    // Corrupt values are ignored, as before, not "clamped" into something that looks chosen.
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: "wide", timelineHeight: null, panelHeights: { metrics: "tall" } }));
    forgetLayoutSizesForTest();
    workWidth = 1000;
    const second = createPanelFrameStore({ viewport });
    live.push(second);
    expect([held().sideWidth, held().timelineHeight, held().panelHeights]).toEqual([DEFAULT_SIDE_WIDTH, DEFAULT_TIMELINE_HEIGHT, {}]);
  });

  it("`getState()` itself reads the window too: one that shrank after the store was made is brought down on the read (this case is about the read)", () => {
    const { controls, store } = attached();
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    windowHeight = 400;
    expect(store.getState().timelineHeight).toBe(280);
    expect(stored().timelineHeight).toBe(280);
  });

  it("with no injected function the store reads the window itself, at each call, as isWide() reads innerWidth", () => {
    vi.stubGlobal("window", { innerWidth: 1400, innerHeight: 600 });
    const store = open();
    store.actions.setTimelineHeight(5000);
    expect(held().timelineHeight).toBe(420);
    expect(stored().timelineHeight).toBe(420);
    store.actions.setSideWidth(5000);
    expect(held().sideWidth).toBe(480);
    expect(stored().sideWidth).toBe(480);
    store.actions.setPanelHeight("metrics", 5000);
    expect(held().panelHeights.metrics).toBe(600);
    expect(stored().panelHeights?.metrics).toBe(600);
    vi.stubGlobal("window", { innerWidth: 700, innerHeight: 300 });
    store.actions.resizeByKey("timeline-height", { key: "ArrowUp", shiftKey: true });
    expect(held().timelineHeight).toBe(210);
    expect(stored().timelineHeight).toBe(210);
    store.actions.resizeByKey("side-width", { key: "ArrowLeft", shiftKey: true });
    expect(held().sideWidth).toBe(380);
    expect(stored().sideWidth).toBe(380);
    store.actions.resizeByKey("panel-height", { key: "ArrowDown", shiftKey: true }, { panel: "metrics" });
    expect(held().panelHeights.metrics).toBe(300);
    expect(stored().panelHeights?.metrics).toBe(300);
  });

  it("with no injected function, repeated ArrowUp through the attach path never stores a size over seven tenths of the window it reads", () => {
    vi.stubGlobal("window", { innerWidth: 1400, innerHeight: 600 });
    const parts = page();
    const store = open();
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    for (let press = 0; press < 40; press += 1) {
      parts.controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
      expect(held().timelineHeight, `memory after press ${press}`).toBeLessThanOrEqual(420);
      expect(stored().timelineHeight ?? 0, `stored after press ${press}`).toBeLessThanOrEqual(420);
      expect(Number(parts.controls.timelineSash.getAttribute("aria-valuenow")), `aria-valuenow after press ${press}`).toBeLessThanOrEqual(420);
    }
    expect(held().timelineHeight).toBe(420);
  });

  it("with no window at all (nothing to read) the limits are still finite: a call that omits maxPx is not unbounded", () => {
    const store = open();
    store.actions.setTimelineHeight(1_000_000);
    store.actions.setPanelHeight("metrics", 1_000_000);
    store.actions.setSideWidth(1_000_000);
    expect(held().timelineHeight).toBeLessThan(2000);
    expect(held().panelHeights.metrics).toBeLessThan(4000);
    expect(held().sideWidth).toBe(480);
    expect(stored().timelineHeight).toBeLessThan(2000);
    expect(stored().panelHeights?.metrics).toBeLessThan(4000);
    expect(stored().sideWidth).toBe(480);
  });

  it("with no window at all, repeated ArrowUp through the attach path stops at the fallback's seven tenths, in memory, stored and drawn", () => {
    const parts = page();
    const store = open();
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    // The fallback window is 768 high: seven tenths is 538.
    for (let press = 0; press < 60; press += 1) {
      parts.controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
      expect(held().timelineHeight, `memory after press ${press}`).toBeLessThanOrEqual(538);
      expect(stored().timelineHeight ?? 0, `stored after press ${press}`).toBeLessThanOrEqual(538);
      expect(Number(parts.controls.timelineSash.getAttribute("aria-valuenow")), `aria-valuenow after press ${press}`).toBeLessThanOrEqual(538);
    }
    expect(held().timelineHeight).toBe(538);
  });

  it("the viewport function is asked at each key press, not once: that is what a resize needs", () => {
    let asked = 0;
    const store = createPanelFrameStore({
      viewport: () => {
        asked += 1;
        return { windowHeight: 800, workWidth: 1000 };
      },
    });
    live.push(store);
    const before = asked;
    store.actions.resizeByKey("timeline-height", { key: "ArrowUp" });
    const afterOne = asked;
    store.actions.resizeByKey("timeline-height", { key: "ArrowUp" });
    expect(afterOne).toBeGreaterThan(before);
    expect(asked).toBeGreaterThan(afterOne);
  });
});

// ---------------------------------------------------------------- one writer (round 4, D225 point 3)
//
// Rounds 1 to 3 each found a path that wrote a size without the live upper limits. This block makes that fault
// impossible by construction and tests that it is, not one path at a time:
//  1. the store has one function, `writeSize`, that applies the minimum and the live upper limit and then writes; every
//     `layoutSizes` setter and reset is called inside it and nowhere else in the store or the attach (the source cases);
//  2. a table walks every entry point (each size writer the store lists in `SIZE_WRITERS`, each key, the pointer's
//     calls, a window resize, the read of a stored value at start, and a direct write to `layoutSizes` while the store
//     is live) against three viewports, and asserts after each call, before any `getState()`, that the size in memory,
//     the stored value and the drawn attributes are within the limits. The table is typed from `SIZE_WRITERS`, and a
//     case fails when `store.actions` has a key that is neither a listed writer nor in the table of actions that write
//     no size: adding a writer without a row is red.
// The pointer's path: the page's drag handler measures the pointer and calls `setSideWidth`, `setTimelineHeight` or
// `setPanelHeight` with the pixel it measured, so those calls, with extreme pixels, are the pointer's rows. (The workspace's
// double-click resets as Home does; the attach has no pointer listener yet: the mounting slice adds the drag and its row.)
// `End` and `PageUp`/`PageDown` are not sash keys in spec/02 or in the workspace: the table presses them so that a later
// author who gives them a meaning is held by the same limits.

type Viewport = { windowHeight: number; workWidth: number };
const VIEWPORTS: Record<string, Viewport> = {
  roomy: { windowHeight: 1200, workWidth: 1600 },
  tight: { windowHeight: 800, workWidth: 600 },
  "below every default": { windowHeight: 100, workWidth: 400 },
};

/** The limits the spec table states, worked out here from the spec and not from the store. */
function limitsOf(v: Viewport) {
  return {
    side: Math.min(480, Math.max(300, v.workWidth - 320)),
    timeline: Math.max(96, Math.round(v.windowHeight * 0.7)),
    panel: Math.max(48, Math.round(v.windowHeight)),
  };
}

describe("one writer: no entry point writes a size above the live limits, read straight after the call", () => {
  let now: Viewport = VIEWPORTS.roomy as Viewport;
  const viewport = () => now;
  const stored = () => JSON.parse(localStorage.getItem(LAYOUT_SIZES_KEY) ?? "{}") as { sideWidth?: number; timelineHeight?: number; panelHeights?: Record<string, number> };

  /** Memory, storage and the drawn attributes, none of them read through `getState()`, against viewport `v`. */
  function expectWithin(v: Viewport, parts: ReturnType<typeof page>, label: string): void {
    const limit = limitsOf(v);
    const kept = getLayoutSizes();
    // A column at 340 or a timeline at 130 is the default, which stands for "nothing chosen": a small window shows it at
    // its limit and does not write it (round 8), so memory and storage may hold it above the limit. What is drawn may not.
    const check = (what: string, value: number | undefined, min: number, max: number, dflt?: number) => {
      if (value === undefined || Number.isNaN(value)) return;
      if (value === dflt && !what.startsWith("drawn")) return;
      expect(value, `${label}: ${what} is ${value}, under its minimum ${min}`).toBeGreaterThanOrEqual(min);
      expect(value, `${label}: ${what} is ${value}, over the limit ${max}`).toBeLessThanOrEqual(max);
    };
    check("memory side width", kept.sideWidth, 300, limit.side, DEFAULT_SIDE_WIDTH);
    check("memory timeline height", kept.timelineHeight, 96, limit.timeline, DEFAULT_TIMELINE_HEIGHT);
    for (const [id, height] of Object.entries(kept.panelHeights)) check(`memory ${id} height`, height, 48, limit.panel);
    const on = stored();
    check("stored side width", on.sideWidth, 300, limit.side, DEFAULT_SIDE_WIDTH);
    check("stored timeline height", on.timelineHeight, 96, limit.timeline, DEFAULT_TIMELINE_HEIGHT);
    for (const [id, height] of Object.entries(on.panelHeights ?? {})) check(`stored ${id} height`, height, 48, limit.panel);
    const number = (value: string | null) => (value === null ? undefined : Number(value));
    check("drawn side sash", number(parts.controls.sideSash.getAttribute("aria-valuenow")), 300, limit.side);
    check("drawn data-side-width", number(parts.side.getAttribute("data-side-width")), 300, limit.side);
    check("drawn timeline sash", number(parts.controls.timelineSash.getAttribute("aria-valuenow")), 96, limit.timeline);
    check("drawn data-timeline-height", number(parts.timeline.getAttribute("data-timeline-height")), 96, limit.timeline);
    if (kept.panelHeights.metrics !== undefined) check("drawn stacked sash", number(parts.controls.panelSash.getAttribute("aria-valuenow")), 48, limit.panel);
  }

  /** A page attached to a store whose window is `start`, with every size pushed to what that window allows. */
  function pageUnder(start: Viewport) {
    now = start;
    const parts = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    store.actions.setSideWidth(5000);
    store.actions.setTimelineHeight(5000);
    store.actions.setPanelHeight("metrics", 5000);
    return { ...parts, store };
  }

  type Setup = ReturnType<typeof pageUnder>;
  const KEYS: KeyLikeRow[] = [
    ...["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].flatMap((key) => [{ key }, { key, shiftKey: true }]),
    { key: "PageUp" },
    { key: "PageDown" },
    { key: "Home" },
    { key: "End" },
  ];
  type KeyLikeRow = { key: string; shiftKey?: boolean };

  /** Every call each size writer takes, with its extreme arguments. Typed from `SIZE_WRITERS`: a writer needs a row. */
  const CALLS: Record<SizeWriter, Array<[string, (s: Setup) => void]>> = {
    // The pointer's calls: a drag measures a pixel and sets it.
    setSideWidth: [0, 340, 481, 5000, Number.MAX_SAFE_INTEGER].flatMap((px) => [
      [`pointer: setSideWidth(${px})`, (s: Setup) => s.store.actions.setSideWidth(px)] as [string, (s: Setup) => void],
      [`pointer: setSideWidth(${px}, maxPx 9000)`, (s: Setup) => s.store.actions.setSideWidth(px, { maxPx: 9000 })],
    ]),
    setPanelHeight: [0, 120, 5000].flatMap((px) => [
      [`pointer: setPanelHeight(${px})`, (s: Setup) => s.store.actions.setPanelHeight("metrics", px)] as [string, (s: Setup) => void],
      [`pointer: setPanelHeight(${px}, maxPx 9000)`, (s: Setup) => s.store.actions.setPanelHeight("metrics", px, { maxPx: 9000 })],
    ]),
    setTimelineHeight: [0, 130, 5000].flatMap((px) => [
      [`pointer: setTimelineHeight(${px})`, (s: Setup) => s.store.actions.setTimelineHeight(px)] as [string, (s: Setup) => void],
      [`pointer: setTimelineHeight(${px}, maxPx 9000)`, (s: Setup) => s.store.actions.setTimelineHeight(px, { maxPx: 9000 })],
    ]),
    resizeByKey: (["side-width", "panel-height", "timeline-height"] as const).flatMap((axis) =>
      KEYS.map((key) => [
        `${axis}: ${key.shiftKey ? "Shift+" : ""}${key.key} by store`,
        (s: Setup) => {
          s.store.actions.resizeByKey(axis, key, { panel: "metrics", from: 200 });
        },
      ] as [string, (s: Setup) => void]),
    ),
    // A window resize: the store is told, and brings what it keeps down to the window it now has.
    fitToWindow: [["window resize: fitToWindow()", (s: Setup) => s.store.actions.fitToWindow()]],
  };

  /** The same keys through the attach, on the sash element, as a page's keyboard user sends them. */
  const SASH_KEYS: Array<[string, (s: Setup, key: KeyLikeRow) => FakeElement]> = [
    ["side sash", (s) => s.controls.sideSash],
    ["stacked sash", (s) => s.controls.panelSash],
    ["timeline sash", (s) => s.controls.timelineSash],
  ];

  const CASES: Array<[string, Viewport, Viewport]> = [];
  // Each viewport twice: the window was already that size, and the window was roomy and then shrank to it.
  for (const [name, v] of Object.entries(VIEWPORTS)) {
    CASES.push([`${name}, window already that size`, v, v]);
    CASES.push([`${name}, window shrank to it`, VIEWPORTS.roomy as Viewport, v]);
  }

  describe.each(CASES)("%s", (_title, startedAs, nowIs) => {
    for (const writer of SIZE_WRITERS) {
      it(`${writer}: every call and key leaves memory, storage and the drawn attributes within the limits`, () => {
        for (const [label, call] of CALLS[writer]) {
          const setup = pageUnder(startedAs);
          now = nowIs;
          call(setup);
          expectWithin(nowIs, setup, label);
          // And again: the second call from wherever the first left it.
          call(setup);
          expectWithin(nowIs, setup, `${label}, twice`);
          setup.store.destroy();
          live = live.filter((other) => other !== setup.store);
          forgetLayoutSizesForTest();
          localStorage.clear?.();
          installStorage(new MemoryStorage());
        }
      });
    }

    it("the keys through the attach, on each sash, held to the limits after every press", () => {
      for (const [sashName, sashOf] of SASH_KEYS) {
        for (const key of KEYS) {
          const setup = pageUnder(startedAs);
          now = nowIs;
          sashOf(setup, key).dispatch("keydown", key);
          expectWithin(nowIs, setup, `${sashName}: ${key.shiftKey ? "Shift+" : ""}${key.key} by attach`);
          setup.store.destroy();
          live = live.filter((other) => other !== setup.store);
          forgetLayoutSizesForTest();
          installStorage(new MemoryStorage());
        }
      }
    });

    it("a direct write to layoutSizes while the store is live is brought down at once, before any read", () => {
      const setup = pageUnder(startedAs);
      now = nowIs;
      // Values that differ from what is held, so that each is a real write and fires the listeners (a set to the size
      // already held is a no-op in `layoutSizes`, and a size a window has since made stale is brought down by the next
      // write, key press or read, or by `fitToWindow`, as the spec says).
      rawSetSideWidth(400);
      expectWithin(nowIs, setup, "layoutSizes.setSideWidth(400)");
      rawSetTimelineHeight(700);
      expectWithin(nowIs, setup, "layoutSizes.setTimelineHeight(700)");
      rawSetPanelHeight("metrics", 700);
      expectWithin(nowIs, setup, "layoutSizes.setPanelHeight(700)");
      rawResetSideWidth();
      expectWithin(nowIs, setup, "layoutSizes.resetSideWidth()");
      rawResetTimelineHeight();
      expectWithin(nowIs, setup, "layoutSizes.resetTimelineHeight()");
    });

    it("the read of a stored value at start: a store made under this window holds what it read to it, in memory and in storage", () => {
      now = nowIs;
      localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 480, timelineHeight: 4000, panelHeights: { metrics: 9000, inspector: 300 } }));
      forgetLayoutSizesForTest();
      const parts = page();
      const store = createPanelFrameStore({ viewport });
      live.push(store);
      // Before it is attached (which reads through getState): what the store itself did when it was made.
      expectWithin(nowIs, parts, "start, before any read");
      attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
      expectWithin(nowIs, parts, "start, attached");
    });
  });

  it("Home on the column in a work area of 600 stores 300, the limit, not the default 340 (the verifier's worked case)", () => {
    now = { windowHeight: 800, workWidth: 600 };
    const parts = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    parts.controls.sideSash.dispatch("keydown", { key: "Home" });
    // The default is shown at the limit and not saved: the analyst chose nothing (round 8).
    expect(localStorage.getItem(LAYOUT_SIZES_KEY)).toBeNull();
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe("300");
    expect(parts.side.getAttribute("data-side-width")).toBe("300");
    // And from a wider column, where Home has a size to change: the default is held to the limit too.
    store.actions.setSideWidth(5000);
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe("300");
    expect(localStorage.getItem(LAYOUT_SIZES_KEY)).toBeNull();
    now = { windowHeight: 800, workWidth: 1000 };
    parts.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    now = { windowHeight: 800, workWidth: 600 };
    parts.controls.sideSash.dispatch("keydown", { key: "Home" });
    expect(getLayoutSizes().sideWidth).toBe(300);
    expect(stored().sideWidth).toBe(300);
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe("300");
  });

  it("Home on the timeline in a window 150 high stores 105, seven tenths of it, not the default 130 (the verifier's worked case)", () => {
    now = { windowHeight: 150, workWidth: 1000 };
    const parts = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    // The default 130 is over the 105 limit, so a store made here already holds the column and the timeline to it.
    parts.controls.timelineSash.dispatch("keydown", { key: "Home" });
    expect(localStorage.getItem(LAYOUT_SIZES_KEY), "the default was written").toBeNull();
    expect(parts.controls.timelineSash.getAttribute("aria-valuenow")).toBe("105");
    expect(parts.timeline.getAttribute("data-timeline-height")).toBe("105");
  });

  it("Home in a roomy window still returns to the default: 340 and 130", () => {
    now = VIEWPORTS.roomy as Viewport;
    const parts = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    store.actions.setSideWidth(450);
    store.actions.setTimelineHeight(500);
    parts.controls.sideSash.dispatch("keydown", { key: "Home" });
    parts.controls.timelineSash.dispatch("keydown", { key: "Home" });
    expect([getLayoutSizes().sideWidth, getLayoutSizes().timelineHeight]).toEqual([DEFAULT_SIDE_WIDTH, DEFAULT_TIMELINE_HEIGHT]);
    expect(stored().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
    expect(stored().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
  });

  it("Home on a stacked panel lets it share the column again, and a window of any size has no height to hold it to", () => {
    now = VIEWPORTS["below every default"] as Viewport;
    const parts = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    store.actions.setPanelHeight("metrics", 90);
    expect(getLayoutSizes().panelHeights.metrics).toBe(90);
    parts.controls.panelSash.dispatch("keydown", { key: "Home" });
    expect(getLayoutSizes().panelHeights.metrics).toBeUndefined();
  });

  // ------------------------------------------------------- a writer added later and not in the table is red

  /** Actions that write no size. A new action must be here or in `SIZE_WRITERS`, or the case below is red. */
  const NO_SIZE: Record<string, (s: PanelFrameStore) => void> = {
    hideSidePanel: (s) => s.actions.hideSidePanel(),
    showSidePanel: (s) => s.actions.showSidePanel(),
    openSidePanelFullWidth: (s) => s.actions.openSidePanelFullWidth(),
    returnSidePanelToNormalWidth: (s) => s.actions.returnSidePanelToNormalWidth(),
    hideTimeline: (s) => s.actions.hideTimeline(),
    showTimeline: (s) => s.actions.showTimeline(),
    moveSidePanel: (s) => s.actions.moveSidePanel("metrics", "up"),
    moveSidePanelByKey: (s) => void s.actions.moveSidePanelByKey("metrics", { key: "ArrowDown", altKey: true }),
    dropSidePanelOn: (s) => s.actions.dropSidePanelOn("metrics", "connections"),
    toggleFold: (s) => s.actions.toggleFold("metrics"),
    toggleDetails: (s) => s.actions.toggleDetails(),
  };

  it("every key of store.actions is a listed size writer or a listed action that writes no size: a writer with no row is red", () => {
    const store = open();
    const listed = [...SIZE_WRITERS, ...Object.keys(NO_SIZE)].sort();
    expect(Object.keys(store.actions).sort()).toEqual(listed);
    expect(new Set(listed).size).toBe(listed.length);
    // And the table has a row for each listed writer, and none for a name that is no writer.
    expect(Object.keys(CALLS).sort()).toEqual([...SIZE_WRITERS].sort());
  });

  /** A store under the window `now` (the stand-in `viewport` is passed in: `open()` gives none, so it reads no window). */
  function openUnder(): PanelFrameStore {
    forgetLayoutSizesForTest();
    forgetSidePanelOrderForTest();
    forgetSidePanelForTest();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    return store;
  }
  const sizesKept = () => [JSON.stringify(getLayoutSizes()), localStorage.getItem(LAYOUT_SIZES_KEY)];

  it("an action listed as writing no size writes none: the sizes in memory and in storage are the same after it, in a window below every default", () => {
    now = VIEWPORTS["below every default"] as Viewport;
    for (const [name, call] of Object.entries(NO_SIZE)) {
      const store = openUnder();
      // The window is really applied: every size starts at its limit (300 and 96), not at its default (340 and 130).
      // (Shown, not stored: a default the window cannot hold is held in memory and drawn at the limit, never written.)
      expect([store.getState().sideWidth, store.getState().timelineHeight], `${name}: the window is applied`).toEqual([300, 96]);
      const before = sizesKept();
      call(store);
      expect(sizesKept(), name).toEqual(before);
    }
  });

  it("the comparison can fail: a planted action that writes a size in storage is seen as a change", () => {
    now = VIEWPORTS["below every default"] as Viewport;
    const store = openUnder();
    const before = sizesKept();
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: DEFAULT_SIDE_WIDTH, timelineHeight: DEFAULT_TIMELINE_HEIGHT }));
    expect(store).toBeDefined();
    expect(sizesKept()).not.toEqual(before);
  });
});

// ---------------------------------------------------------------- round 5: aria-valuemax from the live limit
//
// A sash that has `aria-valuenow` and `aria-valuemin` but no `aria-valuemax` describes a range that does not contain its
// own value (WAI-ARIA gives a focusable separator a maximum of 100 when none is set). The store keeps the live upper
// limit in its state (`limits`, from the one limit function) and the attach draws it as `aria-valuemax` on every sash,
// lowered by the sash's own `data-max` exactly as the writer lowers it, and again when the window changes. Every read
// below is of the drawn attribute straight after the call, never through `getState()`.

describe("aria-valuemax: every sash says the limit the writer applies, under each of the three viewports", () => {
  let now: Viewport = VIEWPORTS.roomy as Viewport;
  const viewport = () => now;

  /** A fake window the attach may hear a resize on, reached as a real element reaches it: `ownerDocument.defaultView`. */
  function fakeWindow() {
    const listeners: Array<() => void> = [];
    return {
      listeners,
      addEventListener: (_type: string, listener: () => void) => void listeners.push(listener),
      removeEventListener: (_type: string, listener: () => void) => void listeners.splice(listeners.indexOf(listener), 1),
      resize: () => listeners.slice().forEach((listener) => listener()),
    };
  }

  function attached(start: Viewport, sashAttributes: Record<string, string> = {}) {
    now = start;
    const parts = page();
    for (const sash of [parts.controls.sideSash, parts.controls.timelineSash, parts.controls.panelSash]) {
      for (const [name, value] of Object.entries(sashAttributes)) sash.attributes.set(name, value);
    }
    const win = fakeWindow();
    Object.defineProperty(parts.root, "ownerDocument", { value: { activeElement: null, defaultView: win } });
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    return { ...parts, store, win };
  }

  const drawnMax = (sash: FakeElement) => sash.getAttribute("aria-valuemax");
  const num = (value: string | null) => (value === null ? NaN : Number(value));

  const CASES5: Array<[string, Viewport, Viewport]> = [];
  for (const [name, v] of Object.entries(VIEWPORTS)) {
    CASES5.push([`${name}, window already that size`, v, v]);
    CASES5.push([`${name}, window shrank to it`, VIEWPORTS.roomy as Viewport, v]);
  }

  describe.each(CASES5)("%s", (_title, startedAs, nowIs) => {
    it("the column's, the timeline's and the stacked panel's sashes draw the limit of the window as it is, from the first draw", () => {
      const page5 = attached(startedAs);
      expect(num(drawnMax(page5.controls.sideSash)), "column, first draw").toBe(limitsOf(startedAs).side);
      expect(num(drawnMax(page5.controls.timelineSash)), "timeline, first draw").toBe(limitsOf(startedAs).timeline);
      expect(num(drawnMax(page5.controls.panelSash)), "stacked, first draw").toBe(limitsOf(startedAs).panel);
      now = nowIs;
      page5.win.resize();
      expect(num(drawnMax(page5.controls.sideSash)), "column, after a window resize").toBe(limitsOf(nowIs).side);
      expect(num(drawnMax(page5.controls.timelineSash)), "timeline, after a window resize").toBe(limitsOf(nowIs).timeline);
      expect(num(drawnMax(page5.controls.panelSash)), "stacked, after a window resize").toBe(limitsOf(nowIs).panel);
    });

    it("the value pushed as far as it goes is the maximum drawn beside it, and the maximum is the limit the writer applies", () => {
      const page5 = attached(startedAs);
      now = nowIs;
      for (let press = 1; press <= 60; press += 1) {
        page5.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
        page5.controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
        page5.controls.panelSash.dispatch("keydown", { key: "ArrowDown", shiftKey: true });
      }
      const side = limitsOf(nowIs).side;
      const timeline = limitsOf(nowIs).timeline;
      const panel = limitsOf(nowIs).panel;
      expect(num(drawnMax(page5.controls.sideSash))).toBe(side);
      expect(num(page5.controls.sideSash.getAttribute("aria-valuenow"))).toBe(side);
      expect(num(drawnMax(page5.controls.timelineSash))).toBe(timeline);
      expect(num(page5.controls.timelineSash.getAttribute("aria-valuenow"))).toBe(timeline);
      expect(num(drawnMax(page5.controls.panelSash))).toBe(panel);
      expect(num(page5.controls.panelSash.getAttribute("aria-valuenow"))).toBe(panel);
      // A range that contains its own value, on every sash.
      for (const sash of [page5.controls.sideSash, page5.controls.timelineSash, page5.controls.panelSash]) {
        expect(num(sash.getAttribute("aria-valuemin"))).toBeLessThanOrEqual(num(sash.getAttribute("aria-valuenow")));
        expect(num(sash.getAttribute("aria-valuenow"))).toBeLessThanOrEqual(num(drawnMax(sash)));
      }
    });

    it("the state carries the limit it was drawn from", () => {
      const page5 = attached(startedAs);
      now = nowIs;
      page5.store.actions.fitToWindow();
      const seen = page5.store.getState().limits;
      expect([seen.sideWidth, seen.timelineHeight, seen.panelHeight]).toEqual([limitsOf(nowIs).side, limitsOf(nowIs).timeline, limitsOf(nowIs).panel]);
    });
  });

  it("a window that changes without changing any size still redraws the maximum (the sizes stayed, the range moved)", () => {
    const page5 = attached({ windowHeight: 1200, workWidth: 1600 });
    expect(num(page5.controls.timelineSash.getAttribute("aria-valuenow"))).toBe(DEFAULT_TIMELINE_HEIGHT);
    expect(num(drawnMax(page5.controls.timelineSash))).toBe(840);
    now = { windowHeight: 1000, workWidth: 1600 };
    page5.win.resize();
    expect(num(page5.controls.timelineSash.getAttribute("aria-valuenow"))).toBe(DEFAULT_TIMELINE_HEIGHT);
    expect(num(drawnMax(page5.controls.timelineSash))).toBe(700);
  });

  it("a page's data-max lowers the maximum drawn, and never lifts it: the drawn maximum is the limit the writer applies", () => {
    const lowerOne = attached(VIEWPORTS.roomy as Viewport, { "data-max": "400" });
    expect(num(drawnMax(lowerOne.controls.sideSash))).toBe(400);
    expect(num(drawnMax(lowerOne.controls.timelineSash))).toBe(400);
    for (let press = 1; press <= 40; press += 1) lowerOne.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    expect(num(lowerOne.controls.sideSash.getAttribute("aria-valuenow"))).toBe(400);
    const liftOne = attached(VIEWPORTS.tight as Viewport, { "data-max": "9000" });
    expect(num(drawnMax(liftOne.controls.sideSash))).toBe(300);
    expect(num(drawnMax(liftOne.controls.timelineSash))).toBe(560);
    // A bound under the minimum never makes the maximum smaller than the minimum.
    const under = attached(VIEWPORTS.roomy as Viewport, { "data-max": "10" });
    expect(num(drawnMax(under.controls.sideSash))).toBe(300);
    expect(num(drawnMax(under.controls.timelineSash))).toBe(96);
  });

  it("the attach stops listening to the window when it is undone, and does not need a window to draw", () => {
    const page5 = attached(VIEWPORTS.roomy as Viewport);
    expect(page5.win.listeners).toHaveLength(1);
    const noWindow = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    const detach = attachPanelFrame(noWindow.root as unknown as PanelFrameRoot, store);
    expect(num(drawnMax(noWindow.controls.sideSash))).toBe(limitsOf(now).side);
    detach();
    const win = fakeWindow();
    const again = page();
    Object.defineProperty(again.root, "ownerDocument", { value: { activeElement: null, defaultView: win } });
    const undo = attachPanelFrame(again.root as unknown as PanelFrameRoot, store);
    expect(win.listeners).toHaveLength(1);
    undo();
    expect(win.listeners).toHaveLength(0);
  });
});

// ---------------------------------------------------------------- round 6: a page's data-max holds on every path
//
// Round 5's verifier: Home on a sash ignored the sash's `data-max`, so it drew `aria-valuenow` above `aria-valuemax`; and a
// stored value, or a set made without `maxPx` (the pointer's), above a sash's `data-max` was drawn out of range too.
// The sash's `data-max` is a bound the writer applies on each of these: the key path passes it (Home as the arrows),
// and the attach, before it draws a state, asks the one writer to hold any size above a sash's bound to that bound.
// Every read below is of memory, storage and the drawn attributes straight after the call, never through `getState()`.

describe("a page's data-max on the sashes holds on every path: keys, Home, the pointer's sets, a stored value, a window resize", () => {
  let now: Viewport = VIEWPORTS.roomy as Viewport;
  const viewport = () => now;
  const BOUND = { side: 320, timeline: 100, panel: 60 };
  const stored = () => JSON.parse(localStorage.getItem(LAYOUT_SIZES_KEY) ?? "{}") as { sideWidth?: number; timelineHeight?: number; panelHeights?: Record<string, number> };

  /** What the writer applies for each sash: the window's limit lowered by the bound, never under the minimum. */
  function boundedOf(v: Viewport) {
    const limit = limitsOf(v);
    return {
      side: Math.max(300, Math.min(limit.side, BOUND.side)),
      timeline: Math.max(96, Math.min(limit.timeline, BOUND.timeline)),
      panel: Math.max(48, Math.min(limit.panel, BOUND.panel)),
    };
  }

  function fakeWindow() {
    const listeners: Array<() => void> = [];
    return {
      listeners,
      addEventListener: (_type: string, listener: () => void) => void listeners.push(listener),
      removeEventListener: (_type: string, listener: () => void) => void listeners.splice(listeners.indexOf(listener), 1),
      resize: () => listeners.slice().forEach((listener) => listener()),
    };
  }

  function bounded(start: Viewport, before?: () => void) {
    now = start;
    before?.();
    const parts = page();
    parts.controls.sideSash.attributes.set("data-max", String(BOUND.side));
    parts.controls.timelineSash.attributes.set("data-max", String(BOUND.timeline));
    parts.controls.panelSash.attributes.set("data-max", String(BOUND.panel));
    const win = fakeWindow();
    Object.defineProperty(parts.root, "ownerDocument", { value: { activeElement: null, defaultView: win } });
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    return { ...parts, store, win };
  }
  type Bounded = ReturnType<typeof bounded>;

  const num = (value: string | null) => (value === null ? NaN : Number(value));

  /** Every sash's value is inside the range it draws, the range is the writer's, and memory and storage agree. */
  function expectHeld(v: Viewport, parts: Bounded, label: string): void {
    const bound = boundedOf(v);
    const kept = getLayoutSizes();
    const on = stored();
    const sashes: Array<[string, FakeElement, FakeElement | null, number, number | undefined, number | undefined]> = [
      ["column", parts.controls.sideSash, parts.side, bound.side, kept.sideWidth, on.sideWidth],
      ["timeline", parts.controls.timelineSash, parts.timeline, bound.timeline, kept.timelineHeight, on.timelineHeight],
      ["stacked", parts.controls.panelSash, null, bound.panel, kept.panelHeights.metrics, on.panelHeights?.metrics],
    ];
    for (const [name, sash, frame, max, inMemory, inStorage] of sashes) {
      const drawnNow = num(sash.getAttribute("aria-valuenow"));
      const drawnMax = num(sash.getAttribute("aria-valuemax"));
      expect(drawnMax, `${label}: ${name} aria-valuemax is the limit the writer applies`).toBe(max);
      if (name !== "stacked" || inMemory !== undefined) {
        expect(drawnNow, `${label}: ${name} aria-valuenow ${drawnNow} is above its aria-valuemax ${drawnMax}`).toBeLessThanOrEqual(drawnMax);
        expect(drawnNow, `${label}: ${name} aria-valuenow is under its aria-valuemin`).toBeGreaterThanOrEqual(num(sash.getAttribute("aria-valuemin")));
      }
      // A column at 340 or a timeline at 130 is the default and stands for "nothing chosen" (round 8): not written, so
      // memory and storage may hold it above a small window's limit; what is drawn, above, may not.
      const isDefault = (value: number) => (name === "column" && value === DEFAULT_SIDE_WIDTH) || (name === "timeline" && value === DEFAULT_TIMELINE_HEIGHT);
      if (inMemory !== undefined && !isDefault(inMemory)) expect(inMemory, `${label}: ${name} in memory is over ${max}`).toBeLessThanOrEqual(max);
      if (inStorage !== undefined && !isDefault(inStorage)) expect(inStorage, `${label}: ${name} in storage is over ${max}`).toBeLessThanOrEqual(max);
      const frameValue = frame?.getAttribute(name === "column" ? "data-side-width" : "data-timeline-height") ?? null;
      if (frameValue !== null) expect(num(frameValue), `${label}: ${name} frame attribute is over ${max}`).toBeLessThanOrEqual(max);
    }
  }

  const KEYS_6 = [
    ...["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].flatMap((key) => [{ key }, { key, shiftKey: true }]),
    { key: "Home" },
    { key: "End" },
  ];

  describe.each(Object.entries(VIEWPORTS))("%s", (_name, v) => {
    it("every key on each sash, from the default and from a size pushed up first, leaves every sash inside its range", () => {
      for (const key of KEYS_6) {
        for (const pushed of [false, true]) {
          forgetLayoutSizesForTest();
          installStorage(new MemoryStorage());
          const parts = bounded(v);
          if (pushed) {
            parts.store.actions.setSideWidth(5000, { maxPx: BOUND.side });
            parts.store.actions.setTimelineHeight(5000, { maxPx: BOUND.timeline });
            parts.store.actions.setPanelHeight("metrics", 5000, { maxPx: BOUND.panel });
          }
          for (const sash of [parts.controls.sideSash, parts.controls.timelineSash, parts.controls.panelSash]) {
            sash.dispatch("keydown", key);
            expectHeld(v, parts, `${key.shiftKey ? "Shift+" : ""}${key.key}, ${pushed ? "pushed" : "default"}`);
            sash.dispatch("keydown", key);
            expectHeld(v, parts, `${key.shiftKey ? "Shift+" : ""}${key.key} twice, ${pushed ? "pushed" : "default"}`);
          }
          parts.store.destroy();
          live = live.filter((other) => other !== parts.store);
        }
      }
    });

    it("the pointer's sets, which carry no maxPx, are held to the sash's data-max before they are drawn", () => {
      const parts = bounded(v);
      for (const px of [0, 340, 481, 5000]) {
        parts.store.actions.setSideWidth(px);
        expectHeld(v, parts, `setSideWidth(${px})`);
        parts.store.actions.setTimelineHeight(px);
        expectHeld(v, parts, `setTimelineHeight(${px})`);
        parts.store.actions.setPanelHeight("metrics", px);
        expectHeld(v, parts, `setPanelHeight(${px})`);
      }
    });

    it("a stored value above the bounds is held to them at the first draw, in memory, in storage and as drawn", () => {
      const parts = bounded(v, () => {
        localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 480, timelineHeight: 500, panelHeights: { metrics: 700 } }));
        forgetLayoutSizesForTest();
      });
      expectHeld(v, parts, "stored value, first draw");
    });

    it("a window resize, from a roomy window to this one, leaves every sash inside its range", () => {
      const parts = bounded(VIEWPORTS.roomy as Viewport);
      parts.store.actions.setSideWidth(5000);
      parts.store.actions.setTimelineHeight(5000);
      parts.store.actions.setPanelHeight("metrics", 5000);
      expectHeld(VIEWPORTS.roomy as Viewport, parts, "before the resize");
      now = v;
      parts.win.resize();
      expectHeld(v, parts, "after the resize");
    });
  });

  it("Home on a sash whose data-max is under the default stores the bound, not the default (the verifier's worked case: 100 and 320 in a roomy window)", () => {
    const parts = bounded({ windowHeight: 1200, workWidth: 1600 });
    parts.controls.timelineSash.dispatch("keydown", { key: "Home" });
    expect(getLayoutSizes().timelineHeight).toBe(100);
    expect(stored().timelineHeight).toBe(100);
    expect(parts.controls.timelineSash.getAttribute("aria-valuenow")).toBe("100");
    expect(parts.controls.timelineSash.getAttribute("aria-valuemax")).toBe("100");
    parts.controls.sideSash.dispatch("keydown", { key: "Home" });
    expect(getLayoutSizes().sideWidth).toBe(320);
    expect(stored().sideWidth).toBe(320);
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe("320");
    // The grow key from there does not shrink the panel.
    parts.controls.timelineSash.dispatch("keydown", { key: "ArrowUp" });
    expect(getLayoutSizes().timelineHeight).toBe(100);
  });

  it("Home through the store alone, given the sash's bound as the key path gives it, stores the bound (no attach to correct it afterwards)", () => {
    now = { windowHeight: 1200, workWidth: 1600 };
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    store.actions.resizeByKey("timeline-height", { key: "Home" }, { maxPx: 100 });
    expect(getLayoutSizes().timelineHeight).toBe(100);
    expect(stored().timelineHeight).toBe(100);
    store.actions.resizeByKey("side-width", { key: "Home" }, { maxPx: 320 });
    expect(getLayoutSizes().sideWidth).toBe(320);
    expect(stored().sideWidth).toBe(320);
    // A bound above the window's limit lifts nothing, and one under the minimum never goes under it.
    store.actions.resizeByKey("timeline-height", { key: "Home" }, { maxPx: 9000 });
    expect(getLayoutSizes().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
    store.actions.resizeByKey("side-width", { key: "Home" }, { maxPx: 10 });
    expect(getLayoutSizes().sideWidth).toBe(300);
  });

  it("a sash with no data-max is not bounded by another sash's: the default still comes back in a roomy window", () => {
    now = VIEWPORTS.roomy as Viewport;
    const parts = page();
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    store.actions.setTimelineHeight(500);
    parts.controls.timelineSash.dispatch("keydown", { key: "Home" });
    expect(getLayoutSizes().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
  });
});

describe("one writer, in the source: every layoutSizes setter and reset is called inside `writeSize` and nowhere else", () => {
  const WRITER_NAMES = ["setSideWidth", "setTimelineHeight", "setPanelHeight", "resetSideWidth", "resetTimelineHeight", "resetPanelHeight"];
  const BEGIN = "// writer: begin";
  const END = "// writer: end";

  /** The source with comments blanked (keeping line numbers). */
  const code = (source: string) =>
    source
      .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
      .split("\n")
      .map((line) => line.replace(/(^|\s)\/\/(?! writer: (begin|end)).*$/, ""))
      .join("\n");

  /** Lines that reach a layoutSizes writer outside the marked region, by a call, a named import or an alias. */
  function writesOutsideTheWriter(source: string): string[] {
    const lines = code(source).split("\n");
    let inside = false;
    let regions = 0;
    const found: string[] = [];
    const calls = new RegExp(`\\bsizeStore\\s*\\.\\s*(${WRITER_NAMES.join("|")})\\b`);
    lines.forEach((line, index) => {
      if (line.includes(BEGIN)) {
        inside = true;
        regions += 1;
      } else if (line.includes(END)) inside = false;
      else if (!inside && calls.test(line)) found.push(`${index + 1}: ${line.trim()}`);
    });
    // A named import of a writer from layoutSizes (even aliased) lets a bare call through, so it is a finding itself.
    for (const match of source.matchAll(/import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*["']\.\/layoutSizes["']/g)) {
      for (const name of WRITER_NAMES) if (new RegExp(`\\b${name}\\b`).test(match[1] as string)) found.push(`import of ${name}`);
    }
    if (regions === 0) found.push("no writer region");
    return found;
  }

  const read = (name: string) => readFileSync(join(HERE, name), "utf8");

  it("the store calls the writers only inside the marked region, and has one", () => {
    expect(writesOutsideTheWriter(read("panelFrameStore.ts"))).toEqual([]);
    const source = read("panelFrameStore.ts");
    expect(source.split("\n").filter((line) => line.includes(BEGIN))).toHaveLength(1);
    const region = source.slice(source.indexOf(BEGIN), source.indexOf(END));
    // The setters and the stacked panel's reset are reached from there: the region is the writer and not an empty marker.
    // (Home on the column and the timeline asks for the default, which is a set held to the limit; their resets are not used.)
    for (const name of ["setSideWidth", "setTimelineHeight", "setPanelHeight", "resetPanelHeight"]) expect(region, name).toContain(`sizeStore.${name}`);
  });

  it("the attach names no writer: it imports only constants from layoutSizes, and calls nothing of it", () => {
    const source = read("panelFrameAttach.ts");
    for (const match of source.matchAll(/import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*["']\.\/layoutSizes["']/g)) {
      for (const name of (match[1] as string).split(",").map((part) => part.trim()).filter(Boolean)) expect(name, "attach imports").toMatch(/^[A-Z_]+$/);
    }
    expect(source).not.toMatch(/import\s*\*\s*as\s+\w+\s+from\s*["']\.\/layoutSizes["']/);
  });

  it("neither file re-exports a layoutSizes writer", () => {
    for (const name of ["panelFrameStore.ts", "panelFrameAttach.ts"]) {
      expect(read(name), name).not.toMatch(/export\s*(\*|\{[^}]*\})\s*from\s*["']\.\/layoutSizes["']/);
    }
  });

  // The shapes the real code would take if a path wrote a size outside the writer (rule 15): the real lines of
  // `resizeByKey`'s Home case and a setter's body, planted one at a time into the real source.
  it.each([
    ["Home calling a reset", "        if (axis === \"side-width\") sizeStore.resetSideWidth();"],
    ["Home calling the timeline's reset", "        else if (axis === \"timeline-height\") sizeStore.resetTimelineHeight();"],
    ["a setter called from an action", "      if (finite(px)) sizeStore.setSideWidth(px);"],
    ["a stacked panel's height", "      sizeStore.setPanelHeight(id, px);"],
  ])("a planted write outside the writer is found: %s", (_name, line) => {
    const real = read("panelFrameStore.ts");
    const planted = real.replace("export function createPanelFrameStore", `function planted(axis: string, px: number, id: SidePanelId) {\n${line}\n}\nexport function createPanelFrameStore`);
    expect(planted).not.toBe(real);
    expect(writesOutsideTheWriter(planted).length).toBeGreaterThan(0);
  });

  it("a planted named import of a setter is found, aliased or not", () => {
    const real = read("panelFrameStore.ts");
    expect(writesOutsideTheWriter(`import { setSideWidth } from "./layoutSizes";\n${real}`)).toContain("import of setSideWidth");
    expect(writesOutsideTheWriter(`import { resetTimelineHeight as raw } from "./layoutSizes";\n${real}`)).toContain("import of resetTimelineHeight");
  });
});

// ------------------------------------------------------------------------------- the source stays clean

const HERE = dirname(fileURLToPath(import.meta.url));

describe("the source: no inline style, no React, no drawing library", () => {
  const files = readdirSync(HERE).filter((name) => /^panelFrame(Store|Attach)\.ts$/.test(name));

  it("reads both files of the frame", () => {
    expect(files.sort()).toEqual(["panelFrameAttach.ts", "panelFrameStore.ts"]);
  });

  it("neither file writes a style: findInlineStyle finds nothing in the real source", () => {
    for (const name of files) expect(findInlineStyle(readFileSync(join(HERE, name), "utf8")), name).toEqual([]);
  });

  // The shapes the real attach code would write if it set a style, planted one at a time (rule 15).
  it.each([
    ["a property write", "  el.style.width = `${px}px`;"],
    ["an element-style assignment", '  frame.style.cssText = "width: 340px";'],
    ["a setProperty call", '  slot.style.setProperty("--w", "340px");'],
    ["a setAttribute", '  node.setAttribute("style", "display: none");'],
    ["a bracket write", '  el["style"].height = "10px";'],
    ["markup carrying one", "  el.innerHTML = '<div style=\"width:1px\"></div>';"],
  ])("findInlineStyle finds %s", (_name, line) => {
    expect(findInlineStyle(`export function f(el: any) {\n${line}\n}\n`).length).toBeGreaterThan(0);
  });

  it("findInlineStyle does not flag a comment that says 'style' or a word that merely contains it", () => {
    expect(findInlineStyle("// sets no inline style\nconst lifestyle = 1;\nconst data = { styleSheet: 1 };\n")).toEqual([]);
  });

  it("neither file imports React, react-dom, a drawing library or the main entry of zustand", () => {
    for (const name of files) {
      const source = readFileSync(join(HERE, name), "utf8");
      const imports = [...source.matchAll(/(?:from|import)\s*\(?\s*["']([^"']+)["']/g)].map((match) => match[1] as string);
      for (const specifier of imports) {
        expect(specifier, `${name} imports ${specifier}`).not.toMatch(/^(react|react-dom|sigma|maplibre-gl|graphology|d3|three)(\/|$)/);
        expect(specifier === "zustand", `${name} imports the main entry of zustand`).toBe(false);
      }
    }
  });

  it("the three layout modules are used, not copied: the store imports each and defines no clamp or normaliser of its own", () => {
    const source = readFileSync(join(HERE, "panelFrameStore.ts"), "utf8");
    for (const module of ["./layoutSizes", "./panelOrder", "./sidePanelState"]) expect(source).toContain(`"${module}"`);
    expect(source).not.toMatch(/function (normaliseLayoutSizes|normaliseSidePanelOrder|clamp)\b/);
  });
});

// ---------------------------------------------------------------- round 7: a bound that is not a whole number, and the root's guard
//
// Round 6's verifier: a sash's `data-max` of 350.5 (any fraction of .5 or more) was held by the writer to 350.5, and
// `layoutSizes` then stored the rounded 351; the attach saw 351 above 350.5, asked for the same write, got no change, and
// returned "wrote" so it never drew. Sizes are whole pixels: a bound is a whole number of them (rounded down, since a
// size above the bound is out of range), so what is written is never above what is drawn as the maximum. And if a write
// ever does change nothing, the state is drawn all the same: a frame is never left undrawn.

describe("a sash's data-max that is not a whole number: held, drawn, and the frame is never left undrawn", () => {
  const stored = () => JSON.parse(localStorage.getItem(LAYOUT_SIZES_KEY) ?? "{}") as { sideWidth?: number; timelineHeight?: number; panelHeights?: Record<string, number> };

  function fractional(bound: { side?: string; timeline?: string; panel?: string }, before?: () => void) {
    before?.();
    const parts = page();
    if (bound.side) parts.controls.sideSash.attributes.set("data-max", bound.side);
    if (bound.timeline) parts.controls.timelineSash.attributes.set("data-max", bound.timeline);
    if (bound.panel) parts.controls.panelSash.attributes.set("data-max", bound.panel);
    const store = createPanelFrameStore({ viewport: () => VIEWPORTS.roomy as Viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    return { ...parts, store };
  }

  describe.each(["350.5", "350.7", "350.2", "350.99"])("a column bound of %s", (text) => {
    const whole = Math.floor(Number(text));
    it("a stored 480 is held to the whole pixels under the bound, the frame is drawn, and later actions still draw", () => {
      const { side, controls, body, store } = fractional({ side: text }, () => {
        localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 480 }));
        forgetLayoutSizesForTest();
      });
      expect(side.getAttribute("data-panel-mode"), "the frame was never drawn").toBe("normal");
      expect(controls.sideSash.getAttribute("aria-valuenow")).toBe(String(whole));
      expect(controls.sideSash.getAttribute("aria-valuemax")).toBe(String(whole));
      expect(side.getAttribute("data-side-width")).toBe(String(whole));
      expect(stored().sideWidth).toBe(whole);
      controls.hide.dispatch("click");
      expect(side.getAttribute("data-panel-mode")).toBe("collapsed");
      controls.foldMetrics.dispatch("click");
      expect(body.metrics.hidden).toBe(false);
      // Growing from the bound stays at it, in memory, storage and as drawn.
      controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
      expect(controls.sideSash.getAttribute("aria-valuenow")).toBe(String(whole));
      expect(stored().sideWidth).toBe(whole);
      store.destroy();
    });
  });

  it("the timeline's and the stacked panel's fractional bounds are held the same way, and the pointer's sets too", () => {
    const { timeline, controls, store } = fractional({ timeline: "130.5", panel: "60.5" });
    store.actions.setTimelineHeight(5000);
    store.actions.setPanelHeight("metrics", 5000);
    expect(timeline.getAttribute("data-timeline-height")).toBe("130");
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("130");
    expect(controls.timelineSash.getAttribute("aria-valuemax")).toBe("130");
    expect(stored().timelineHeight).toBe(130);
    expect(controls.panelSash.getAttribute("aria-valuenow")).toBe("60");
    expect(controls.panelSash.getAttribute("aria-valuemax")).toBe("60");
    expect(stored().panelHeights?.metrics).toBe(60);
    timeline.getAttribute("data-panel-open");
    expect(timeline.getAttribute("data-panel-open")).toBe("false");
  });

  it("Home and the arrows on a sash with a fractional bound never store above the whole pixels under it", () => {
    const { controls } = fractional({ side: "340.5", timeline: "130.5" });
    for (const key of ["Home", "ArrowLeft", "ArrowUp"]) {
      controls.sideSash.dispatch("keydown", { key, shiftKey: true });
      controls.timelineSash.dispatch("keydown", { key, shiftKey: true });
      expect(stored().sideWidth ?? 0, `${key}: column`).toBeLessThanOrEqual(340);
      expect(stored().timelineHeight ?? 0, `${key}: timeline`).toBeLessThanOrEqual(130);
      expect(Number(controls.sideSash.getAttribute("aria-valuenow")), `${key}: column drawn`).toBeLessThanOrEqual(Number(controls.sideSash.getAttribute("aria-valuemax")));
    }
  });

  // The attach draws even when the writer changes nothing (the defence under the rounding above): a store whose writers
  // refuse every set, as one that held the value already would, with a size above the sash's bound in its state.
  it("a writer that changes nothing does not leave the frame undrawn: the state is drawn as it is", () => {
    const { root, side, timeline, controls } = page();
    controls.sideSash.attributes.set("data-max", "350");
    controls.timelineSash.attributes.set("data-max", "100");
    controls.panelSash.attributes.set("data-max", "60");
    const state = {
      sideMode: "normal",
      timelineOpen: true,
      order: [...SIDE_PANEL_IDS],
      folded: [] as string[],
      sideWidth: 480,
      timelineHeight: 400,
      panelHeights: { metrics: 300 },
      limits: { sideWidth: 480, timelineHeight: 560, panelHeight: 1200 },
    };
    const listeners = new Set<(next: typeof state, previous: typeof state) => void>();
    const refusing = {
      getState: () => state,
      subscribe: (listener: (next: typeof state, previous: typeof state) => void) => {
        listeners.add(listener);
        return () => void listeners.delete(listener);
      },
      destroy: () => undefined,
      actions: new Proxy({}, { get: () => () => undefined }),
    } as unknown as PanelFrameStore;
    attachPanelFrame(root as unknown as PanelFrameRoot, refusing);
    expect(side.getAttribute("data-panel-mode"), "the frame was not drawn when the writer changed nothing").toBe("normal");
    expect(timeline.getAttribute("data-panel-open")).toBe("true");
    expect(controls.sideSash.getAttribute("aria-valuenow")).not.toBeNull();
    // Each later state is drawn too, even while a size is still above its bound.
    listeners.forEach((listener) => listener({ ...state, sideMode: "collapsed" }, state));
    expect(side.getAttribute("data-panel-mode")).toBe("collapsed");
  });
});

describe("attach: the root's guard, with the root nested in an element that has an action, a header or a sash of its own", () => {
  /** The root inside a wrapper carrying the attributes a click or a key would otherwise find first. */
  function nested() {
    const parts = page();
    const wrapper = new FakeElement("div", { "data-action": "hide-side-panel", "data-panel-header": "metrics", "data-sash": "side-width" });
    wrapper.append(parts.root);
    const inner = new FakeElement("p");
    parts.root.append(inner);
    const store = open();
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    return { ...parts, wrapper, inner, store };
  }

  it("a click on a plain element inside the root does not run the wrapper's action", () => {
    const { inner, store } = nested();
    inner.dispatch("click");
    expect(store.getState().sideMode).toBe("normal");
  });

  it("Alt+Arrow on a plain element inside the root does not move the panel the wrapper's header names", () => {
    const { inner, store } = nested();
    const event = inner.dispatch("keydown", { key: "ArrowDown", altKey: true });
    expect(event.defaultPrevented).toBe(false);
    expect(store.getState().order).toEqual([...SIDE_PANEL_IDS]);
  });

  it("an arrow key on a plain element inside the root does not resize through the wrapper's sash", () => {
    const { wrapper, inner, store } = nested();
    wrapper.attributes.set("data-action", "resize");
    wrapper.attributes.delete("data-panel-header"); // the header's own path would answer first
    const event = inner.dispatch("keydown", { key: "ArrowLeft" });
    expect(event.defaultPrevented).toBe(false);
    expect(getLayoutSizes().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
    expect(store.getState().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
  });
});

// ------------------------------------------------- round 8 (the verifier's finding on round 7): a default is never saved

// A new store with nothing saved, in a window too small for the default, brought the column and the timeline down and
// wrote the lower size to this browser's storage, so a reload in a roomy window opened at it and not at the spec table's
// 340 and 130. A size the analyst never chose is shown at the window's limit and is not written; a size they did choose
// (a kept one above today's limit, or one asked for that is not just what is shown) still is. Each case reads the
// storage straight after the call, before any `getState()`.

describe("a default the window cannot hold is shown lower and never saved (the spec table: 340px and 130px)", () => {
  const stored = () => localStorage.getItem(LAYOUT_SIZES_KEY);
  const TIGHT_WIDTH: Viewport = { windowHeight: 800, workWidth: 600 }; // the column's limit is 300
  const SHORT: Viewport = { windowHeight: 150, workWidth: 1600 }; // the timeline's limit is 105
  const ROOMY: Viewport = { windowHeight: 1200, workWidth: 1600 };

  function made(viewport: Viewport) {
    forgetLayoutSizesForTest();
    const parts = page();
    const store = createPanelFrameStore({ viewport: () => viewport });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    return { ...parts, store };
  }

  it("a store made at workWidth 600 with nothing saved leaves storage empty and draws 300; a reload at 1600 opens at 340", () => {
    expect(stored()).toBeNull();
    const { controls, side, store } = made(TIGHT_WIDTH);
    expect(stored(), "the default was written to this browser's storage").toBeNull();
    expect(controls.sideSash.getAttribute("aria-valuenow")).toBe("300");
    expect(side.getAttribute("data-side-width")).toBe("300");
    store.destroy();
    const again = made(ROOMY);
    expect(again.controls.sideSash.getAttribute("aria-valuenow")).toBe(String(DEFAULT_SIDE_WIDTH));
    expect(again.side.getAttribute("data-side-width")).toBe("340");
    expect(stored()).toBeNull();
  });

  it("a store made in a window 150 high with nothing saved leaves storage empty and draws 105; a reload in a tall window opens at 130", () => {
    const { controls, timeline, store } = made(SHORT);
    expect(stored(), "the default was written to this browser's storage").toBeNull();
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("105");
    expect(timeline.getAttribute("data-timeline-height")).toBe("105");
    store.destroy();
    const again = made(ROOMY);
    expect(again.controls.timelineSash.getAttribute("aria-valuenow")).toBe(String(DEFAULT_TIMELINE_HEIGHT));
    expect(stored()).toBeNull();
  });

  it("the same through the store's own state, with no page and no storage written", () => {
    const store = createPanelFrameStore({ viewport: () => ({ windowHeight: 150, workWidth: 600 }) });
    live.push(store);
    const state = store.getState();
    expect([state.sideWidth, state.timelineHeight]).toEqual([300, 105]);
    expect(stored()).toBeNull();
  });

  it("a window that shrinks after the page is made, then a fit and a key that changes nothing, still write nothing", () => {
    let now: Viewport = ROOMY;
    forgetLayoutSizesForTest();
    const parts = page();
    const store = createPanelFrameStore({ viewport: () => now });
    live.push(store);
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    now = { windowHeight: 150, workWidth: 600 };
    store.actions.fitToWindow();
    expect(stored(), "a resize wrote the default").toBeNull();
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe("300");
    expect(parts.controls.timelineSash.getAttribute("aria-valuenow")).toBe("105");
    // Growing a column already at its limit, and Home (the default, held to the limit), change what is shown by nothing.
    parts.controls.sideSash.dispatch("keydown", { key: "ArrowLeft" });
    parts.controls.sideSash.dispatch("keydown", { key: "Home" });
    parts.controls.timelineSash.dispatch("keydown", { key: "ArrowUp" });
    parts.controls.timelineSash.dispatch("keydown", { key: "Home" });
    expect(stored(), "a key that changed nothing wrote the default").toBeNull();
    // The window grows again: the default is back, because it was never replaced.
    now = ROOMY;
    store.actions.fitToWindow();
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe("340");
    expect(parts.controls.timelineSash.getAttribute("aria-valuenow")).toBe("130");
  });

  it("a size the analyst kept above today's limit is still brought down in storage (the round-2 rule)", () => {
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 450, timelineHeight: 300, panelHeights: {} }));
    made({ windowHeight: 150, workWidth: 600 });
    expect(JSON.parse(stored() ?? "{}")).toMatchObject({ sideWidth: 300, timelineHeight: 105 });
  });

  it("a size the analyst chooses is written (320 in a window that allows up to 480)", () => {
    const { store } = made({ windowHeight: 800, workWidth: 1000 });
    store.actions.setSideWidth(320);
    expect(JSON.parse(stored() ?? "{}").sideWidth).toBe(320);
  });

  it("a stored default that is over the limit (340, kept explicitly) is held in memory, not rewritten as 300", () => {
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 340, timelineHeight: 130, panelHeights: {} }));
    const { controls } = made({ windowHeight: 150, workWidth: 600 });
    expect(JSON.parse(stored() ?? "{}")).toMatchObject({ sideWidth: 340, timelineHeight: 130 });
    expect(controls.sideSash.getAttribute("aria-valuenow")).toBe("300");
  });
});

// -------------------------------------------- round 9 (the verifier's finding on round 8): a draw never saves a page's bound
//
// A sash whose `data-max` is below the default (320 for the column, 100 for the timeline) had its bound written to this
// browser's storage on the first draw, with nothing done by the analyst: the attach asked the writer to hold the default
// to the bound, and the writer wrote it. Only a size the analyst chose is stored (spec/02), and the workspace reads the
// same key, so its column opened at 320 from then on. A bound a page gives is shown (the default drawn at the bound) and
// not written, by a draw, a fit or a window resize; Home and an arrow key, which are an analyst's act, still store it.
// Every read is of storage and the drawn attributes straight after the call, before any `getState()`.

describe("a page's data-max below the default is shown, and never saved by a draw (the spec table: 340px and 130px)", () => {
  const stored = () => localStorage.getItem(LAYOUT_SIZES_KEY);
  const BELOW = { side: 320, timeline: 100, panel: 60 };
  let now: Viewport = VIEWPORTS.roomy as Viewport;

  function bounds(start: Viewport, before?: () => void) {
    now = start;
    forgetLayoutSizesForTest();
    before?.();
    const parts = page();
    parts.controls.sideSash.attributes.set("data-max", String(BELOW.side));
    parts.controls.timelineSash.attributes.set("data-max", String(BELOW.timeline));
    parts.controls.panelSash.attributes.set("data-max", String(BELOW.panel));
    const store = createPanelFrameStore({ viewport: () => now });
    live.push(store);
    const win = { listeners: [] as Array<() => void> };
    Object.defineProperty(parts.root, "ownerDocument", {
      value: {
        activeElement: null,
        defaultView: {
          addEventListener: (_type: string, listener: () => void) => void win.listeners.push(listener),
          removeEventListener: () => undefined,
        },
      },
    });
    attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
    return { ...parts, store, resize: () => win.listeners.forEach((listener) => listener()) };
  }

  /** The range each sash draws: the window's limit lowered by the page's bound, never under the minimum. */
  const rangeOf = (v: Viewport) => {
    const limit = limitsOf(v);
    return {
      side: Math.max(300, Math.min(limit.side, BELOW.side)),
      timeline: Math.max(96, Math.min(limit.timeline, BELOW.timeline)),
    };
  };

  describe.each(Object.entries(VIEWPORTS))("%s", (_name, v) => {
    it("the first draw with nothing kept writes nothing, and draws the default at the bound", () => {
      const parts = bounds(v);
      expect(stored(), "a draw wrote the page's bound to this browser's storage").toBeNull();
      const range = rangeOf(v);
      expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe(String(range.side));
      expect(parts.controls.sideSash.getAttribute("aria-valuemax")).toBe(String(range.side));
      expect(parts.side.getAttribute("data-side-width")).toBe(String(range.side));
      expect(parts.controls.timelineSash.getAttribute("aria-valuenow")).toBe(String(range.timeline));
      expect(parts.controls.timelineSash.getAttribute("aria-valuemax")).toBe(String(range.timeline));
      expect(parts.timeline.getAttribute("data-timeline-height")).toBe(String(range.timeline));
    });

    it("a window resize to this one, from a roomy one, writes nothing either", () => {
      const parts = bounds(VIEWPORTS.roomy as Viewport);
      now = v;
      parts.resize();
      parts.store.actions.fitToWindow();
      expect(stored(), "a resize wrote the page's bound").toBeNull();
      expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe(String(rangeOf(v).side));
      expect(parts.controls.timelineSash.getAttribute("aria-valuenow")).toBe(String(rangeOf(v).timeline));
    });
  });

  it("a page opened afterwards with no bound opens at the default (a reload after the bounded page)", () => {
    const first = bounds(VIEWPORTS.roomy as Viewport);
    first.store.destroy();
    const again = page();
    const store = createPanelFrameStore({ viewport: () => VIEWPORTS.roomy as Viewport });
    live.push(store);
    attachPanelFrame(again.root as unknown as PanelFrameRoot, store);
    expect(again.controls.sideSash.getAttribute("aria-valuenow")).toBe(String(DEFAULT_SIDE_WIDTH));
    expect(again.controls.timelineSash.getAttribute("aria-valuenow")).toBe(String(DEFAULT_TIMELINE_HEIGHT));
    expect(stored()).toBeNull();
  });

  it("Home on each sash is the analyst's act and stores the bound", () => {
    const parts = bounds(VIEWPORTS.roomy as Viewport);
    parts.controls.sideSash.dispatch("keydown", { key: "Home" });
    parts.controls.timelineSash.dispatch("keydown", { key: "Home" });
    expect(JSON.parse(stored() ?? "{}")).toMatchObject({ sideWidth: BELOW.side, timelineHeight: BELOW.timeline });
  });

  it("an arrow key is the analyst's act and stores what it reaches, held to the bound", () => {
    const parts = bounds(VIEWPORTS.roomy as Viewport);
    parts.controls.sideSash.dispatch("keydown", { key: "ArrowLeft" });
    parts.controls.timelineSash.dispatch("keydown", { key: "ArrowUp" });
    expect(JSON.parse(stored() ?? "{}")).toMatchObject({ sideWidth: BELOW.side, timelineHeight: BELOW.timeline });
  });

  it("a size the analyst kept above the bound is still brought down to it in storage", () => {
    const parts = bounds(VIEWPORTS.roomy as Viewport, () => {
      localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 450, timelineHeight: 300, panelHeights: {} }));
    });
    expect(JSON.parse(stored() ?? "{}")).toMatchObject({ sideWidth: BELOW.side, timelineHeight: BELOW.timeline });
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe(String(BELOW.side));
  });

  it("a stored default (340, 130) is left as it is and drawn at the bound", () => {
    const parts = bounds(VIEWPORTS.roomy as Viewport, () => {
      localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 340, timelineHeight: 130, panelHeights: {} }));
    });
    expect(JSON.parse(stored() ?? "{}")).toMatchObject({ sideWidth: 340, timelineHeight: 130 });
    expect(parts.controls.sideSash.getAttribute("aria-valuenow")).toBe(String(BELOW.side));
    expect(parts.controls.timelineSash.getAttribute("aria-valuenow")).toBe(String(BELOW.timeline));
  });

  it("the store's own calls say what they are: a hold to a bound writes nothing at the default, a set does", () => {
    const store = createPanelFrameStore({ viewport: () => VIEWPORTS.roomy as Viewport });
    live.push(store);
    store.actions.setSideWidth(DEFAULT_SIDE_WIDTH, { maxPx: BELOW.side, fitting: true });
    store.actions.setTimelineHeight(DEFAULT_TIMELINE_HEIGHT, { maxPx: BELOW.timeline, fitting: true });
    expect(stored()).toBeNull();
    store.actions.setSideWidth(DEFAULT_SIDE_WIDTH, { maxPx: BELOW.side });
    expect(JSON.parse(stored() ?? "{}").sideWidth).toBe(BELOW.side);
  });
});
