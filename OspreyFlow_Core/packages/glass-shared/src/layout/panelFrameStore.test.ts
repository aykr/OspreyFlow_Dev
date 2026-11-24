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
import { DEFAULT_SIDE_WIDTH, DEFAULT_TIMELINE_HEIGHT, LAYOUT_SIZES_KEY, MIN_SIDE_WIDTH, forgetLayoutSizesForTest } from "./layoutSizes";
import { SIDE_PANEL_IDS, SIDE_PANEL_ORDER_KEY, forgetSidePanelOrderForTest } from "./panelOrder";
import { attachPanelFrame, type PanelFrameRoot } from "./panelFrameAttach";
import {
  FOLDED_PANELS_KEY,
  PANEL_ACTION_STORAGE,
  SASH_LARGE_STEP,
  SASH_STEP,
  createPanelFrameStore,
  findInlineStyle,
  type PanelFrameStore,
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

// ------------------------------------------------------------- the upper limits, from the live window (round 2)

// What the spec table says the frame holds: the timeline between 96px and seven tenths of the window; the column between
// 300 and 480 and leaving the canvas 320; a stacked panel no taller than the window. The store reads the window itself
// at each resize through one injectable function, so a call that omits `maxPx`, and a page whose markup cannot know the
// window's height, are both held.
describe("the upper limits come from the live window, through the attach path, at each key press", () => {
  let windowHeight = 800;
  let workWidth = 1000;
  const viewport = () => ({ windowHeight, workWidth });
  const stored = () => JSON.parse(localStorage.getItem(LAYOUT_SIZES_KEY) ?? "{}") as { sideWidth?: number; timelineHeight?: number; panelHeights?: Record<string, number> };
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
    const { controls, store } = attached();
    for (let press = 0; press < 80; press += 1) {
      controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: press % 2 === 0 });
      expect(store.getState().timelineHeight).toBeLessThanOrEqual(560);
      expect(stored().timelineHeight ?? 0).toBeLessThanOrEqual(560);
    }
    expect(store.getState().timelineHeight).toBe(560);
    expect(stored().timelineHeight).toBe(560);
    expect(controls.timelineSash.getAttribute("aria-valuenow")).toBe("560");
    expect(reload().getState().timelineHeight).toBe(560);
  });

  it("a page's own data-max on the sash may lower the limit and never lift it", () => {
    const { controls, store } = attached();
    controls.timelineSash.setAttribute("data-max", "300");
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    expect(store.getState().timelineHeight).toBe(300);
    controls.timelineSash.setAttribute("data-max", "5000");
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    expect(store.getState().timelineHeight).toBe(560);
    store.actions.setTimelineHeight(9000, { maxPx: 9000 });
    expect(store.getState().timelineHeight).toBe(560);
    store.actions.setSideWidth(9000, { maxPx: 9000 });
    expect(store.getState().sideWidth).toBe(480);
  });

  it("repeated ArrowLeft on the column's sash stops at 480, or where the canvas keeps 320 of the work area", () => {
    const wide = attached();
    for (let press = 0; press < 40; press += 1) wide.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    expect(wide.store.getState().sideWidth).toBe(480);
    expect(stored().sideWidth).toBe(480);
    wide.store.actions.resizeByKey("side-width", { key: "Home" });

    // A 700px work area: 700 - 320 = 380 for the column, under 480.
    workWidth = 700;
    for (let press = 0; press < 40; press += 1) {
      wide.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: press % 2 === 0 });
      expect(700 - wide.store.getState().sideWidth).toBeGreaterThanOrEqual(320);
      expect(700 - (stored().sideWidth ?? 0)).toBeGreaterThanOrEqual(320);
    }
    expect(wide.store.getState().sideWidth).toBe(380);
    expect(wide.controls.sideSash.getAttribute("aria-valuenow")).toBe("380");

    // So small a work area that 320 for the canvas cannot be kept: the column never goes under 300.
    workWidth = 500;
    for (let press = 0; press < 5; press += 1) wide.controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    expect(wide.store.getState().sideWidth).toBe(300);
  });

  it("repeated ArrowDown on a stacked panel's sash stops at the window's height", () => {
    const { controls, store } = attached();
    for (let press = 0; press < 40; press += 1) controls.panelSash.dispatch("keydown", { key: "ArrowDown", shiftKey: true });
    expect(store.getState().panelHeights.metrics).toBe(800);
    expect(stored().panelHeights?.metrics).toBe(800);
  });

  it("a shrinking window brings a stored size down on the next key press", () => {
    const { controls, store } = attached();
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    for (let press = 0; press < 20; press += 1) controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: true });
    expect([store.getState().timelineHeight, store.getState().sideWidth]).toEqual([560, 480]);

    windowHeight = 500;
    workWidth = 650;
    // ArrowUp would have grown 560 to 576 against the old window; against this one it is held at 350.
    controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: false });
    expect(store.getState().timelineHeight).toBe(350);
    expect(stored().timelineHeight).toBe(350);
    controls.sideSash.dispatch("keydown", { key: "ArrowLeft", shiftKey: false });
    expect(store.getState().sideWidth).toBe(330);
    expect(stored().sideWidth).toBe(330);
  });

  it("a stored size above today's limit is read brought down, in memory and in storage; a corrupt one is ignored", () => {
    windowHeight = 500;
    workWidth = 650;
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 480, timelineHeight: 4000, panelHeights: { metrics: 9000, inspector: 120 } }));
    const store = createPanelFrameStore({ viewport });
    live.push(store);
    const state = store.getState();
    expect([state.timelineHeight, state.sideWidth]).toEqual([350, 330]);
    expect(state.panelHeights).toEqual({ metrics: 500, inspector: 120 });
    expect(stored().timelineHeight).toBe(350);
    expect(stored().sideWidth).toBe(330);

    // Corrupt values are ignored, as before, not "clamped" into something that looks chosen.
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: "wide", timelineHeight: null, panelHeights: { metrics: "tall" } }));
    forgetLayoutSizesForTest();
    const second = createPanelFrameStore({ viewport });
    live.push(second);
    expect([second.getState().sideWidth, second.getState().timelineHeight, second.getState().panelHeights]).toEqual([DEFAULT_SIDE_WIDTH, DEFAULT_TIMELINE_HEIGHT, {}]);
  });

  it("a window that has shrunk after the store was made is read on getState, not only on a key press", () => {
    const { controls, store } = attached();
    for (let press = 0; press < 20; press += 1) controls.timelineSash.dispatch("keydown", { key: "ArrowUp", shiftKey: true });
    windowHeight = 400;
    expect(store.getState().timelineHeight).toBe(280);
  });

  it("with no injected function the store reads the window itself, at each call, as isWide() reads innerWidth", () => {
    vi.stubGlobal("window", { innerWidth: 1400, innerHeight: 600 });
    const store = open();
    store.actions.setTimelineHeight(5000);
    expect(store.getState().timelineHeight).toBe(420);
    store.actions.setSideWidth(5000);
    expect(store.getState().sideWidth).toBe(480);
    vi.stubGlobal("window", { innerWidth: 700, innerHeight: 300 });
    store.actions.resizeByKey("timeline-height", { key: "ArrowUp", shiftKey: true });
    expect(store.getState().timelineHeight).toBe(210);
    store.actions.resizeByKey("side-width", { key: "ArrowLeft", shiftKey: true });
    expect(store.getState().sideWidth).toBe(380);
  });

  it("with no window at all (nothing to read) the limits are still finite: a call that omits maxPx is not unbounded", () => {
    const store = open();
    store.actions.setTimelineHeight(1_000_000);
    store.actions.setPanelHeight("metrics", 1_000_000);
    store.actions.setSideWidth(1_000_000);
    const state = store.getState();
    expect(state.timelineHeight).toBeLessThan(2000);
    expect(state.panelHeights.metrics).toBeLessThan(4000);
    expect(state.sideWidth).toBe(480);
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
