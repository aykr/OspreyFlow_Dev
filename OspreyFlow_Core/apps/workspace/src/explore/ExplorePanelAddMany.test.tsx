// @vitest-environment jsdom
// "Where to start" offers "Add many from a list" (ADR-128 decision 1, B2) beside what the case holds:
// a fold that opens to the paste box and the file choice, and is offered only where there is a canvas
// to draw on (`onApplyDelta`). It is offered for a case that holds nothing yet too, since a list is a
// way to start.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplorePanel } from "./ExplorePanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ nodes: {}, edges: {}, computed_at: null }), { status: 200 })),
  );
}

function mount(onApplyDelta?: () => void) {
  serve();
  render(
    <ExplorePanel
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="c1"
      edgeTypes={[]}
      onPick={vi.fn()}
      onApplyDelta={onApplyDelta}
    />,
  );
}

describe("Where to start's add-many fold", () => {
  it("is offered, folded, when there is a canvas to draw on", async () => {
    mount(vi.fn());
    const header = screen.getByRole("button", { name: "Add many from a list" });
    expect(header.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(header);
    expect(header.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("textbox", { name: /identifiers/i })).toBeTruthy();
    expect(screen.getByLabelText(/\.txt or \.csv file/i)).toBeTruthy();
  });

  it("is not offered with nowhere to draw", () => {
    mount();
    expect(screen.queryByRole("button", { name: "Add many from a list" })).toBeNull();
  });
});
