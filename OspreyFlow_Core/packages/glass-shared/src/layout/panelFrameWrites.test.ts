// What the panel frame writes to `ospreyflow.layout-sizes`, for every panel action, bound and starting state (slice PL8a,
// round 13; the owner's ruling of 25 November 2026: "a size is written only when it is the size the analyst's own action
// asked for, never a clamped value; one test over every panel action x bound x starting state").
//
// Rounds 9, 10 and 11 each found a path that wrote a size nobody chose (the window's limit, or a page's `data-max`): a
// draw, a fit, a window resize, Home. The React workspace reads the same key, so such a write is an analyst's 450 lost for
// good. This table is the one test that crosses them all:
//
//   each of the ten ids in `PANEL_FRAME_ACTIONS`            (typed from the registry: a new id needs a row, or this fails)
//   x each bound   none; the window's limit (a narrow window, and one below every default); a page's `data-max` under the default
//   x each start   nothing stored; a size stored above the bound; a size stored below it
//
// and, beside the ten, the paths that are not an action but could write (the store being made, the first draw, a window
// resize). After each, for every size, what is stored is either what it was or exactly the size the call asked for; it is
// never the bound or the limit. A clamp changes what is drawn, never what is stored: the drawn value is read too.
//
// The oracle is not the store's: what a call "asked for" is worked out here from the size the sash showed before the call
// (a key's step from it, Home's default, a pointer's pixel), held only to the range `layoutSizes` itself keeps (300 to 480
// for the column; the minimums), which is the analyst's own range and not a window's or a page's.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PANEL_FRAME_ACTIONS } from "../keyboard/actionRegistry";
import { DEFAULT_SIDE_WIDTH, DEFAULT_TIMELINE_HEIGHT, LAYOUT_SIZES_KEY, forgetLayoutSizesForTest } from "./layoutSizes";
import { attachPanelFrame, type PanelFrameRoot } from "./panelFrameAttach";
import { createPanelFrameStore, type PanelFrameActionId, type PanelFrameStore } from "./panelFrameStore";
import { SIDE_PANEL_IDS, forgetSidePanelOrderForTest } from "./panelOrder";
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

class FakeElement {
  readonly attributes = new Map<string, string>();
  readonly classes = new Set<string>();
  readonly children: FakeElement[] = [];
  readonly listeners = new Map<string, Listener[]>();
  parent: FakeElement | null = null;
  ownerDocument: unknown = { activeElement: null, defaultView: null };
  readonly classList = {
    toggle: (name: string, force?: boolean) => {
      const on = force ?? !this.classes.has(name);
      if (on) this.classes.add(name);
      else this.classes.delete(name);
      return on;
    },
  };
  constructor(attributes: Record<string, string> = {}) {
    for (const [name, value] of Object.entries(attributes)) this.attributes.set(name, value);
  }
  append(...nodes: FakeElement[]): void {
    for (const node of nodes) {
      node.parent?.children.splice(node.parent.children.indexOf(node), 1);
      node.parent = this;
      this.children.push(node);
    }
  }
  setAttribute(name: string, value: string): void {
    this.attributes.set(name, value);
  }
  getAttribute(name: string): string | null {
    return this.attributes.get(name) ?? null;
  }
  set hidden(value: boolean) {
    if (value) this.attributes.set("hidden", "");
    else this.attributes.delete("hidden");
  }
  get hidden(): boolean {
    return this.attributes.has("hidden");
  }
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
  dispatch(type: string, init: Partial<FakeEvent> = {}): FakeEvent {
    const event: FakeEvent = { type, target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...init };
    for (const at of this.chain()) (at.listeners.get(type) ?? []).slice().forEach((listener) => listener(event));
    return event;
  }
}

function fakeWindow() {
  const listeners: Array<() => void> = [];
  return {
    addEventListener: (_type: string, listener: () => void) => void listeners.push(listener),
    removeEventListener: (_type: string, listener: () => void) => void listeners.splice(listeners.indexOf(listener), 1),
    resize: () => listeners.slice().forEach((listener) => listener()),
  };
}

type Viewport = { windowHeight: number; workWidth: number };

/** A page: the frames, a panel's slot, its header, every control, and three sashes (each with the page's bound, if any). */
function buildPage(bound: Bound) {
  const root = new FakeElement({ "data-panel-frame-root": "" });
  const side = new FakeElement({ "data-panel-frame": "side" });
  const timeline = new FakeElement({ "data-panel-frame": "timeline" });
  const slots = SIDE_PANEL_IDS.map((id) => new FakeElement({ "data-panel-slot": id }));
  const button = (action: string, extra: Record<string, string> = {}) => new FakeElement({ "data-action": action, ...extra });
  const dataMax = (axis: keyof NonNullable<Bound["dataMax"]>): Record<string, string> => (bound.dataMax ? { "data-max": String(bound.dataMax[axis]) } : {});
  const controls = {
    hide: button("hide-side-panel"),
    show: button("show-side-panel"),
    full: button("open-side-panel-full-width"),
    normal: button("return-side-panel-to-normal-width"),
    hideTimeline: button("hide-timeline"),
    showTimeline: button("show-timeline"),
    details: button("toggle-details"),
    fold: button("toggle-fold", { "data-panel": "metrics" }),
    up: button("move-side-panel-up", { "data-panel": "metrics" }),
    down: button("move-side-panel-down", { "data-panel": "metrics" }),
    sideSash: button("resize", { "data-sash": "side-width", ...dataMax("side") }),
    panelSash: button("resize", { "data-sash": "panel-height", "data-panel": "metrics", "data-from": "200", ...dataMax("panel") }),
    timelineSash: button("resize", { "data-sash": "timeline-height", ...dataMax("timeline") }),
  };
  const header = new FakeElement({ "data-panel-header": "metrics" });
  slots[SIDE_PANEL_IDS.indexOf("metrics")]?.append(header);
  side.append(...slots);
  root.append(side, timeline, ...Object.values(controls));
  const win = fakeWindow();
  root.ownerDocument = { activeElement: null, defaultView: win };
  return { root, side, timeline, controls, header, win };
}
type Page = ReturnType<typeof buildPage> & { store: PanelFrameStore; setViewport(v: Viewport): void };

// ---------------------------------------------------------------------------------------- bounds and start states

interface Bound {
  name: string;
  viewport: Viewport;
  /** A page's `data-max` on each sash. */
  dataMax?: { side: number; timeline: number; panel: number };
}

const BOUNDS: Bound[] = [
  { name: "none (a roomy window)", viewport: { windowHeight: 1200, workWidth: 1600 } },
  // Limits: column 420, timeline 280, stacked 400.
  { name: "the window's limit (a narrow window)", viewport: { windowHeight: 400, workWidth: 740 } },
  // Limits: column 300, timeline 105 (under the default 130), stacked 150.
  { name: "the window's limit, under every default", viewport: { windowHeight: 150, workWidth: 600 } },
  { name: "a page's data-max under the default", viewport: { windowHeight: 1200, workWidth: 1600 }, dataMax: { side: 320, timeline: 100, panel: 60 } },
];

interface Start {
  name: string;
  /** What is in storage before the page opens: undefined is no entry at all. */
  stored?: { sideWidth: number; timelineHeight: number; panelHeights: Record<string, number> };
}
const STARTS: Start[] = [
  { name: "nothing stored" },
  { name: "a size stored above the bound", stored: { sideWidth: 480, timelineHeight: 600, panelHeights: { metrics: 700 } } },
  { name: "a size stored below the bound", stored: { sideWidth: 310, timelineHeight: 98, panelHeights: { metrics: 50 } } },
];

// -------------------------------------------------------------------------------------------------- the oracle

interface Sizes {
  sideWidth?: number;
  timelineHeight?: number;
  panelHeight?: number;
}
/** What storage holds, field by field; an entry that is not there is undefined. */
function readStored(): Sizes {
  const raw = localStorage.getItem(LAYOUT_SIZES_KEY);
  if (raw === null) return {};
  const parsed = JSON.parse(raw) as { sideWidth?: number; timelineHeight?: number; panelHeights?: Record<string, number> };
  return { sideWidth: parsed.sideWidth, timelineHeight: parsed.timelineHeight, panelHeight: parsed.panelHeights?.metrics };
}

/** What a call asked for, per size; `undefined` in a list is "no size of its own" (Home on a stacked panel). */
type Asked = { sideWidth?: Array<number | undefined>; timelineHeight?: Array<number | undefined>; panelHeight?: Array<number | undefined> };

/** The range `layoutSizes` keeps for the analyst's own request: not a window's limit, not a page's bound. */
const keptRange = {
  sideWidth: (px: number) => Math.min(480, Math.max(300, Math.round(px))),
  timelineHeight: (px: number) => Math.max(96, Math.round(px)),
  panelHeight: (px: number) => Math.max(48, Math.round(px)),
};

const DEFAULT_OF: Record<keyof Sizes, number | undefined> = {
  sideWidth: DEFAULT_SIDE_WIDTH,
  timelineHeight: DEFAULT_TIMELINE_HEIGHT,
  panelHeight: undefined,
};

/**
 * The whole rule, as a function so that it can be shown to fail: every size in `after` is what it was in `before`, or
 * exactly what the call asked for. A size absent before and a default after is `layoutSizes` writing the whole record
 * around one change, not a size anyone chose, so it counts as unchanged.
 */
function storageBreaks(before: Sizes, after: Sizes, asked: Asked): string[] {
  const broken: string[] = [];
  for (const field of ["sideWidth", "timelineHeight", "panelHeight"] as const) {
    const was = before[field] ?? DEFAULT_OF[field];
    const now = after[field] ?? DEFAULT_OF[field];
    if (now === was) continue;
    if (asked[field]?.some((wanted) => (wanted ?? DEFAULT_OF[field]) === now)) continue;
    broken.push(`${field}: was ${String(before[field])}, now ${String(after[field])}, and the call asked for ${JSON.stringify(asked[field] ?? "nothing")}`);
  }
  return broken;
}

const shownOf = (page: Page): Required<Sizes> => ({
  sideWidth: Number(page.controls.sideSash.getAttribute("aria-valuenow")),
  timelineHeight: Number(page.controls.timelineSash.getAttribute("aria-valuenow")),
  panelHeight: Number(page.controls.panelSash.getAttribute("aria-valuenow")),
});

// ------------------------------------------------------------------------------------------ the ten actions' calls

interface Call {
  label: string;
  run: (page: Page) => void;
  asks: (shownBefore: Required<Sizes>) => Asked;
}

const noSize = (label: string, run: (page: Page) => void): Call => ({ label, run, asks: () => ({}) });
const click = (label: string, control: (page: Page) => FakeElement): Call => noSize(label, (page) => void control(page).dispatch("click"));

const KEY_VARIANTS = [{ shiftKey: false }, { shiftKey: true }];

/** A sash's arrow keys: the key moves by a step from what the sash showed, and Home asks for the default. */
function sashCalls(
  axis: keyof Sizes,
  sash: (page: Page) => FakeElement,
  grows: string,
  shrinks: string,
  home: number | undefined,
): Call[] {
  const step = (shift: boolean) => (shift ? 64 : 16);
  const calls: Call[] = [];
  for (const { shiftKey } of KEY_VARIANTS) {
    for (const [key, sign] of [[grows, 1], [shrinks, -1]] as const) {
      calls.push({
        label: `${axis}: ${shiftKey ? "Shift+" : ""}${key}`,
        run: (page) => void sash(page).dispatch("keydown", { key, shiftKey }),
        asks: (shown) => ({ [axis]: [keptRange[axis](shown[axis] + sign * step(shiftKey))] }),
      });
    }
  }
  calls.push({
    label: `${axis}: Home`,
    run: (page) => void sash(page).dispatch("keydown", { key: "Home" }),
    asks: () => ({ [axis]: [home] }),
  });
  return calls;
}

/** The pointer's path: a drag measures a pixel and sets it. Its asked-for size is that pixel. */
function pointerCalls(axis: keyof Sizes): Call[] {
  return [0, 330, 450, 5000].map((px) => ({
    label: `${axis}: a pointer set to ${px}`,
    run: (page: Page) => {
      if (axis === "sideWidth") page.store.actions.setSideWidth(px);
      else if (axis === "timelineHeight") page.store.actions.setTimelineHeight(px);
      else page.store.actions.setPanelHeight("metrics", px);
    },
    asks: () => ({ [axis]: [keptRange[axis](px)] }),
  }));
}

/** One row per id in the registry, typed from it: a new id with no row is a type error and a failed case. */
const CALLS: Record<PanelFrameActionId, Call[]> = {
  "hide-and-show-the-side-panel-by-keyboard": [click("hide", (p) => p.controls.hide), click("show", (p) => p.controls.show)],
  "open-the-side-panel-to-the-full-width-and-return-by-keyboard": [click("full width", (p) => p.controls.full), click("return", (p) => p.controls.normal)],
  "hide-and-show-the-timeline-by-keyboard": [click("hide", (p) => p.controls.hideTimeline), click("show", (p) => p.controls.showTimeline)],
  "move-a-side-panel-up-and-down-by-keyboard": [click("up", (p) => p.controls.up), click("down", (p) => p.controls.down)],
  "move-a-side-panel-with-alt-arrows-by-keyboard": ["ArrowUp", "ArrowDown"].map((key) =>
    noSize(`Alt+${key}`, (page) => void page.header.dispatch("keydown", { key, altKey: true })),
  ),
  "fold-a-side-panel-by-keyboard": [click("fold", (p) => p.controls.fold)],
  "resize-the-side-panel-by-keyboard": [
    ...sashCalls("sideWidth", (p) => p.controls.sideSash, "ArrowLeft", "ArrowRight", DEFAULT_SIDE_WIDTH),
    ...pointerCalls("sideWidth"),
  ],
  "resize-a-stacked-panel-by-keyboard": [
    ...sashCalls("panelHeight", (p) => p.controls.panelSash, "ArrowDown", "ArrowUp", undefined),
    ...pointerCalls("panelHeight"),
  ],
  "resize-the-timeline-by-keyboard": [
    ...sashCalls("timelineHeight", (p) => p.controls.timelineSash, "ArrowUp", "ArrowDown", DEFAULT_TIMELINE_HEIGHT),
    ...pointerCalls("timelineHeight"),
  ],
  "close-and-open-the-details-panel-by-keyboard": [click("details", (p) => p.controls.details)],
};

/** Not actions, but paths that could write: the window changing under the page. They ask for nothing. */
const NOT_ACTIONS: Call[] = [
  noSize("a window resize to a tight window", (page) => {
    page.setViewport({ windowHeight: 150, workWidth: 600 });
    page.win.resize();
  }),
  noSize("a window resize to a roomy window", (page) => {
    page.setViewport({ windowHeight: 1200, workWidth: 1600 });
    page.win.resize();
  }),
  noSize("fitToWindow, called by the page", (page) => page.store.actions.fitToWindow()),
  noSize("a read of the state", (page) => void page.store.getState()),
];

// ----------------------------------------------------------------------------------------------------- the runs

let live: PanelFrameStore[] = [];

beforeEach(() => {
  vi.stubGlobal("localStorage", new MemoryStorage());
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

/** Opens a page under `bound` with `start` already in storage: the store is made and the first draw done. */
function open(bound: Bound, start: Start): { page: Page; before: Sizes } {
  if (start.stored) localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify(start.stored));
  forgetLayoutSizesForTest();
  forgetSidePanelOrderForTest();
  forgetSidePanelForTest();
  const before = readStored();
  let now = bound.viewport;
  const parts = buildPage(bound);
  const store = createPanelFrameStore({ viewport: () => now });
  live.push(store);
  attachPanelFrame(parts.root as unknown as PanelFrameRoot, store);
  return { page: { ...parts, store, setViewport: (v) => void (now = v) }, before };
}

const cases = BOUNDS.flatMap((bound) => STARTS.map((start) => [`${bound.name}, ${start.name}`, bound, start] as const));

describe("the table covers the registry", () => {
  it("has a row for each of the ten ids in the registry and for no other", () => {
    expect(Object.keys(CALLS).sort()).toEqual([...PANEL_FRAME_ACTIONS].sort());
    expect(PANEL_FRAME_ACTIONS).toHaveLength(10);
    for (const id of PANEL_FRAME_ACTIONS) expect(CALLS[id].length, id).toBeGreaterThan(0);
  });
});

describe("the rule can fail: a planted clamped write is reported", () => {
  it("a stored limit, a stored bound, and a size nobody asked for are each reported; the asked-for size and an unchanged one are not", () => {
    expect(storageBreaks({ sideWidth: 450 }, { sideWidth: 380 }, {})).toHaveLength(1); // the window's limit written over the analyst's 450
    expect(storageBreaks({ sideWidth: 450 }, { sideWidth: 320 }, { sideWidth: [434] })).toHaveLength(1); // the page's bound, asked for 434
    expect(storageBreaks({}, { timelineHeight: 100 }, {})).toHaveLength(1); // a bound written on a first draw
    expect(storageBreaks({ sideWidth: 450 }, { sideWidth: 434 }, { sideWidth: [434] })).toEqual([]);
    expect(storageBreaks({ sideWidth: 450 }, { sideWidth: 450 }, {})).toEqual([]);
    expect(storageBreaks({}, { sideWidth: 340, timelineHeight: 130 }, {})).toEqual([]); // the record's defaults around nothing
    expect(storageBreaks({ panelHeight: 90 }, {}, { panelHeight: [undefined] })).toEqual([]); // Home forgets a stacked height
  });
});

describe.each(cases)("%s", (title, bound, start) => {

  it(`${title}: the store being made and the first draw write nothing the analyst did not ask for`, () => {
    const { page, before } = open(bound, start);
    expect(storageBreaks(before, readStored(), {}), "the first draw").toEqual([]);
    // What is drawn is held to the limit and the bound; what is stored is untouched by that.
    const shown = shownOf(page);
    expect(shown.sideWidth).toBeGreaterThanOrEqual(300);
  });

  for (const [id, calls] of Object.entries(CALLS) as Array<[PanelFrameActionId, Call[]]>) {
    it(`${title}: ${id}: storage is what it was or exactly what each call asked for`, () => {
      for (const call of calls) {
        const { page, before } = open(bound, start);
        const shownBefore = shownOf(page);
        call.run(page);
        // Read straight after the call, before anything reads the state.
        expect(storageBreaks(before, readStored(), call.asks(shownBefore)), `${id}: ${call.label}`).toEqual([]);
        // And a second press, from wherever the first left it.
        const middle = readStored();
        const shownMiddle = shownOf(page);
        call.run(page);
        expect(storageBreaks(middle, readStored(), call.asks(shownMiddle)), `${id}: ${call.label}, again`).toEqual([]);
        page.store.destroy();
        live = live.filter((store) => store !== page.store);
        forgetLayoutSizesForTest();
        localStorage.removeItem(LAYOUT_SIZES_KEY);
      }
    });
  }

  it(`${title}: the paths that are not an action (a window resize, fitToWindow, a read) write nothing`, () => {
    for (const call of NOT_ACTIONS) {
      const { page, before } = open(bound, start);
      call.run(page);
      expect(storageBreaks(before, readStored(), {}), call.label).toEqual([]);
      page.store.destroy();
      live = live.filter((store) => store !== page.store);
      forgetLayoutSizesForTest();
      localStorage.removeItem(LAYOUT_SIZES_KEY);
    }
  });
});

describe("a kept size is not lost by opening a page that cannot show it (the verifier's worked cases)", () => {
  it("a 450 kept, a window whose work area is 700: the column limit is 380 and the store, made there, leaves 450", () => {
    localStorage.setItem(LAYOUT_SIZES_KEY, JSON.stringify({ sideWidth: 450, timelineHeight: 130, panelHeights: {} }));
    forgetLayoutSizesForTest();
    const store = createPanelFrameStore({ viewport: () => ({ windowHeight: 900, workWidth: 700 }) });
    live.push(store);
    expect(readStored().sideWidth).toBe(450);
    expect(store.getState().sideWidth, "drawn at the limit").toBe(380);
  });

  it("a 450 kept, a page whose sash has data-max 320: the first draw shows 320 and leaves 450", () => {
    const bound = BOUNDS[3] as Bound;
    const { page } = open(bound, { name: "450 kept", stored: { sideWidth: 450, timelineHeight: 130, panelHeights: {} } });
    expect(readStored().sideWidth).toBe(450);
    expect(page.controls.sideSash.getAttribute("aria-valuenow")).toBe("320");
    expect(page.side.getAttribute("data-side-width")).toBe("320");
  });

  it("Home from a kept 360 on a page with data-max 320 does not store 320; the same for the timeline's 400 and data-max 100", () => {
    const bound = BOUNDS[3] as Bound;
    const { page } = open(bound, { name: "kept", stored: { sideWidth: 360, timelineHeight: 400, panelHeights: {} } });
    page.controls.sideSash.dispatch("keydown", { key: "Home" });
    page.controls.timelineSash.dispatch("keydown", { key: "Home" });
    expect(readStored().sideWidth).not.toBe(320);
    expect(readStored().timelineHeight).not.toBe(100);
    expect(readStored().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
    expect(readStored().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
  });
});
