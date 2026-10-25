// @vitest-environment jsdom
// ADR-124 decision 2 (U6b round 2): the one gate that shows the over-cap dialog, puts it away and
// brings it back, joined to the working-set store. `App.tsx` and the keyboard harness both render
// it, so what `keyboard/view-over-cap.spec.ts` exercises is what the Glass runs.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DeltaSnapshot, LimitExceeded } from "./models";
import { createWorkingSet } from "./store";
import { applyRestoredSnapshot, ViewOverCapGate } from "./ViewOverCapGate";

afterEach(cleanup);

const wouldBe: LimitExceeded = {
  error: "limit_exceeded",
  cap_kind: "nodes",
  cap: 50_000,
  would_be: 50_001,
  options: ["branch", "filter", "promote_to_batch"],
};
const snapshot: DeltaSnapshot = { seq: 9, op: "snapshot", nodes: [], edges: [] };

function mount() {
  const { store } = createWorkingSet();
  const requestResync = vi.fn();
  const onBranchOpened = vi.fn();
  render(
    <ViewOverCapGate
      store={store}
      requestResync={requestResync}
      entityTypes={["Person", "Vehicle"]}
      apiBaseUrl="http://api.invalid"
      bearerToken="token"
      investigationId="c1"
      onBranchOpened={onBranchOpened}
    />,
  );
  return { store, requestResync, onBranchOpened };
}

const DIALOG = { name: "Your view of this case is too large" };
const REOPEN = { name: "Your view of this case is too large. Choose what to do" };

describe("the gate", () => {
  it("shows nothing until the server says the view is over the cap", () => {
    mount();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("button", REOPEN)).toBeNull();
  });

  it("shows the dialog when the store is set, and a snapshot takes it away", () => {
    const { store } = mount();
    act(() => store.getState().setViewOverCap(wouldBe));
    expect(screen.getByRole("dialog", DIALOG)).toBeTruthy();

    act(() => store.getState().applyDelta(snapshot));

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("puts the dialog away on Escape behind a button that is focused, and the button brings it back", () => {
    const { store } = mount();
    act(() => store.getState().setViewOverCap(wouldBe));

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    const reopen = screen.getByRole("button", REOPEN);
    expect(document.activeElement).toBe(reopen);
    fireEvent.click(reopen);
    expect(screen.getByRole("dialog", DIALOG)).toBeTruthy();
    expect(screen.queryByRole("button", REOPEN)).toBeNull();
  });

  it("shows the dialog again when a new figure arrives after it was put away", () => {
    const { store } = mount();
    act(() => store.getState().setViewOverCap(wouldBe));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();

    act(() => store.getState().setViewOverCap({ ...wouldBe, would_be: 50_002 }));

    expect(screen.getByRole("dialog", DIALOG).textContent).toContain("50,002");
  });

  it("Try again asks for a resync with no last sequence", () => {
    const { store, requestResync } = mount();
    act(() => store.getState().setViewOverCap(wouldBe));

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(requestResync).toHaveBeenCalledTimes(1);
    expect(requestResync).toHaveBeenCalledWith(null);
  });

  it("goes away with the case", () => {
    const { store } = mount();
    act(() => store.getState().setViewOverCap(wouldBe));

    act(() => store.getState().resetCase());

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("button", REOPEN)).toBeNull();
  });
});

describe("a snapshot that did not come from the socket", () => {
  it("clears the over-cap state and asks the server to count again, since the socket is still stuck", () => {
    const { store } = createWorkingSet();
    store.getState().setViewOverCap(wouldBe);
    const requestResync = vi.fn();

    applyRestoredSnapshot(store, requestResync, snapshot);

    expect(store.getState().viewOverCap).toBeNull();
    expect(store.getState().seq).toBe(9);
    expect(requestResync).toHaveBeenCalledTimes(1);
    expect(requestResync).toHaveBeenCalledWith(null);
  });

  it("asks nothing of the server when the view was not over the cap", () => {
    const { store } = createWorkingSet();
    const requestResync = vi.fn();

    applyRestoredSnapshot(store, requestResync, snapshot);

    expect(store.getState().seq).toBe(9);
    expect(requestResync).not.toHaveBeenCalled();
  });
});
