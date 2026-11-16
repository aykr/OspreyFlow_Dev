// @vitest-environment jsdom
// ADR-097 step 3 (design review item 15): the resolution threshold is named for what an analyst sets
// with it, how strictly two records must match to be drawn as one entity.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CanvasToolbarCompact } from "../canvas/toolbarCompact";
import { createWorkingSet } from "../workingset/store";
import { ResolutionThresholdControl } from "./ThresholdControl";

function renderControl(props: { compact?: boolean; onChangeSummary?: (m: string) => void; store?: ReturnType<typeof createWorkingSet>["store"] } = {}) {
  return render(
    <CanvasToolbarCompact.Provider value={props.compact ?? false}>
      <ResolutionThresholdControl
        apiBaseUrl="http://test.invalid"
        bearerToken="unused"
        investigationId="inv-1"
        store={props.store ?? createWorkingSet().store}
        onChangeSummary={props.onChangeSummary}
      />
    </CanvasToolbarCompact.Provider>,
  );
}

async function openSlider(): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole("button", { name: /^Match strictness:/ }));
  return screen.getByRole("slider", { name: "Match strictness" });
}

beforeEach(() => {
  // The control shows nothing until the case's threshold has loaded.
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ threshold: 0.95 }), { status: 200 }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ResolutionThresholdControl", () => {
  it("is called Match strictness, on the slider and in what the bar shows", async () => {
    renderControl();
    expect(await openSlider()).toBeTruthy();
    expect(screen.queryByText(/Resolution/)).toBeNull();
  });
});

// v0.6.1 glass-rows A (ADR-145 Amendment 19 decision 5; the owner's rulings of 16 November 2026): a compact
// control in the canvas toolbar, its name and setting on a button that opens the same slider.
describe("strictness as a toolbar control (Amendment 19 decision 5)", () => {
  it("is one button naming the setting, closed, the slider not drawn until it is pressed", async () => {
    renderControl();
    const button = await screen.findByRole("button", { name: "Match strictness: Balanced" });
    expect(button.textContent).toBe("Match strictness: Balanced ▾");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("slider")).toBeNull();
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    const slider = screen.getByRole("slider", { name: "Match strictness" });
    const panel = document.getElementById(button.getAttribute("aria-controls") ?? "");
    expect(panel?.contains(slider)).toBe(true);
    // The three stops, as before: nothing about resolution changes.
    expect([slider.getAttribute("min"), slider.getAttribute("max"), (slider as HTMLInputElement).value]).toEqual(["0", "2", "1"]);
  });

  it("closes on Escape and on its button, focus back on the button", async () => {
    renderControl();
    const slider = await openSlider();
    slider.focus();
    fireEvent.keyDown(slider, { key: "Escape" });
    const button = screen.getByRole("button", { name: "Match strictness: Balanced" });
    expect(screen.queryByRole("slider")).toBeNull();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    fireEvent.click(button);
    expect(screen.queryByRole("slider")).toBeNull();
  });

  it("shows a value none of the stops name as Custom on the button", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ threshold: 0.9 }), { status: 200 }));
    renderControl();
    expect(await screen.findByRole("button", { name: "Match strictness: Custom (0.90)" })).toBeTruthy();
  });

  it("on a narrow toolbar shows the shorter words, keeping the whole name for a screen reader and in its title", async () => {
    renderControl({ compact: true });
    const button = await screen.findByRole("button", { name: "Match strictness: Balanced" });
    expect(button.textContent).toBe("Strictness: Balanced ▾");
    expect(button.getAttribute("title")).toBe("Match strictness: Balanced");
  });
});

// 9 October 2026: signed in as a second account with the first account's case still open, the
// threshold route answered 404 `{"error": "investigation_not_found"}`. The control took
// `body.threshold` (undefined) as the threshold, its `=== null` guard let it through, `.toFixed`
// threw, and the whole Glass went blank.
describe("a refused threshold", () => {
  it("shows no control and does not throw", async () => {
    vi.stubGlobal(
      "fetch",
      async () => new Response(JSON.stringify({ error: "investigation_not_found" }), { status: 404 }),
    );
    renderControl();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("button", { name: /Match strictness/ })).toBeNull();
    expect(screen.queryByRole("slider", { name: "Match strictness" })).toBeNull();
  });
});

// ADR-124 decision 1 (U2c): the PUT answers a `ResolutionOutcome` `{delta, merged, split, affected}`:
// the figures are the acting analyst's own, on the answer and not on the delta.
describe("the change summary reads the outcome", () => {
  const SUMMARY = "Match strictness: Strict — 9 merged, 8 split, 6 affected";

  async function moveToStrict(answer: unknown): Promise<{ summaries: string[]; seq: () => number }> {
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) =>
      init?.method === "PUT"
        ? new Response(JSON.stringify(answer), { status: 200 })
        : new Response(JSON.stringify({ threshold: 0.95 }), { status: 200 }),
    );
    const summaries: string[] = [];
    const { store } = createWorkingSet();
    renderControl({ store, onChangeSummary: (m) => summaries.push(m) });
    const slider = await openSlider();
    fireEvent.change(slider, { target: { value: "0" } });
    fireEvent.mouseUp(slider);
    await waitFor(() => expect(summaries.length).toBeGreaterThan(0));
    return { summaries, seq: () => store.getState().seq };
  }

  it("shows the outcome's figures and applies the delta inside it", async () => {
    const { summaries, seq } = await moveToStrict({
      delta: { seq: 2, op: "reproject", reason: "threshold", affected_cluster_ids: {} },
      merged: 9,
      split: 8,
      affected: 6,
    });
    expect(summaries).toEqual([SUMMARY]);
    expect(seq()).toBe(2);
    // The button follows the new setting.
    expect(await screen.findByRole("button", { name: "Match strictness: Strict" })).toBeTruthy();
  });
});

describe("a key released on the slider without moving it", () => {
  it("sends nothing: the setting it already has is not re-projected", async () => {
    const puts: string[] = [];
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") puts.push(String(init.body));
      return new Response(JSON.stringify({ threshold: 0.95 }), { status: 200 });
    });
    renderControl();
    const slider = await openSlider();
    fireEvent.keyUp(slider, { key: "Tab" });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(puts).toEqual([]);
  });
});

// The lane-reviewer's item 10: the guard against re-sending compared with the value read when the control opened, so a
// stop a colleague had moved away from could not be chosen again. What is sent is decided by whether the slider moved.
describe("a stop chosen after the slider moved", () => {
  it("is sent, even where it is the stop this control last read", async () => {
    const puts: string[] = [];
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        puts.push(String(init.body));
        return new Response(JSON.stringify({ delta: { seq: 2, op: "reproject", reason: "threshold", affected_cluster_ids: {} }, merged: 0, split: 0, affected: 0 }), { status: 200 });
      }
      return new Response(JSON.stringify({ threshold: 0.95 }), { status: 200 });
    });
    renderControl();
    const slider = await openSlider();
    // Away and back to Balanced in one gesture (a colleague's Strict is what the case holds now).
    fireEvent.change(slider, { target: { value: "0" } });
    fireEvent.change(slider, { target: { value: "1" } });
    fireEvent.keyUp(slider, { key: "ArrowRight" });
    await waitFor(() => expect(puts).toEqual([JSON.stringify({ threshold: 0.95 })]));
  });
});
