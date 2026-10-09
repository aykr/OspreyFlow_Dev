// @vitest-environment jsdom
// ADR-097 step 3 (design review item 15): the resolution threshold is named for what an analyst sets
// with it, how strictly two records must match to be drawn as one entity.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createWorkingSet } from "../workingset/store";
import { ResolutionThresholdControl } from "./ThresholdControl";

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
    render(
      <ResolutionThresholdControl
        apiBaseUrl="http://test.invalid"
        bearerToken="unused"
        investigationId="inv-1"
        store={createWorkingSet().store}
      />,
    );
    expect(await screen.findByRole("slider", { name: "Match strictness" })).toBeTruthy();
    expect(screen.getByText("Match strictness")).toBeTruthy();
    expect(screen.queryByText(/Resolution/)).toBeNull();
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
    render(
      <ResolutionThresholdControl
        apiBaseUrl="http://test.invalid"
        bearerToken="unused"
        investigationId="inv-1"
        store={createWorkingSet().store}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("slider", { name: "Match strictness" })).toBeNull();
  });
});
