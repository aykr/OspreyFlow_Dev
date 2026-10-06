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
