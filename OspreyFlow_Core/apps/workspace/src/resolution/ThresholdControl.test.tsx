// @vitest-environment jsdom
// ADR-097 step 3 (design review item 15): the resolution threshold is named for what an analyst sets
// with it, how strictly two records must match to be drawn as one entity.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

// ADR-124 U2b: the PUT answers a bare `DeltaReproject` today and a `ResolutionOutcome`
// `{delta, merged, split, affected}` once U2c lands; the control tolerates either.
describe("the change summary reads either answer shape", () => {
  const REPROJECT = {
    seq: 2, op: "reproject", reason: "threshold", merged: 4, split: 1, affected: 7, affected_cluster_ids: {},
  };
  const SUMMARY = "Match strictness: Strict — 4 merged, 1 split, 7 affected";

  async function moveToStrict(answer: unknown): Promise<{ summaries: string[]; seq: () => number }> {
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) =>
      init?.method === "PUT"
        ? new Response(JSON.stringify(answer), { status: 200 })
        : new Response(JSON.stringify({ threshold: 0.95 }), { status: 200 }),
    );
    const summaries: string[] = [];
    const { store } = createWorkingSet();
    render(
      <ResolutionThresholdControl
        apiBaseUrl="http://test.invalid"
        bearerToken="unused"
        investigationId="inv-1"
        store={store}
        onChangeSummary={(m) => summaries.push(m)}
      />,
    );
    const slider = await screen.findByRole("slider", { name: "Match strictness" });
    fireEvent.change(slider, { target: { value: "0" } });
    fireEvent.mouseUp(slider);
    await waitFor(() => expect(summaries.length).toBeGreaterThan(0));
    return { summaries, seq: () => store.getState().seq };
  }

  it("the bare DeltaReproject sent today", async () => {
    const { summaries, seq } = await moveToStrict(REPROJECT);
    expect(summaries).toEqual([SUMMARY]);
    expect(seq()).toBe(2);
  });

  it("the new ResolutionOutcome", async () => {
    // The figures are the outcome's own, and differ from any on the delta, so reading the delta's
    // would be seen; the delta carries none, as the new answer's may not.
    const { summaries, seq } = await moveToStrict({
      delta: { seq: 2, op: "reproject", reason: "threshold", affected_cluster_ids: {} },
      merged: 9, split: 8, affected: 6,
    });
    expect(summaries).toEqual(["Match strictness: Strict — 9 merged, 8 split, 6 affected"]);
    expect(seq()).toBe(2);
  });

  it("the outcome's own figures win over any the delta also carries", async () => {
    const { summaries } = await moveToStrict({ delta: REPROJECT, merged: 9, split: 8, affected: 6 });
    expect(summaries).toEqual(["Match strictness: Strict — 9 merged, 8 split, 6 affected"]);
  });
});
