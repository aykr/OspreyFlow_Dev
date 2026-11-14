// @vitest-environment jsdom
// The App's hold on the batch job's panel (ADR-151): a choice belongs to the case and the person it was made in
// and for. What would fail if it were wrong: a panel following one case's job in another (its readings sent to the
// wrong case), one person's refused figure shown to the next who signs in in place (rule 7), or a second choice
// reusing the first's panel instead of opening its own.
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { BatchExpansionRequest } from "./batchExpansionApi";
import { useBatchExpansion } from "./useBatchExpansion";

const REQUEST: BatchExpansionRequest = {
  nodeId: "n1",
  edgeType: null,
  depth: 1,
  refused: { error: "limit_exceeded", cap_kind: "nodes", cap: 5000, would_be: 6210, options: ["save_as_view", "filter", "promote_to_batch"] },
};

function hold(caseId: string | null, who: string | null) {
  return renderHook(({ caseId, who }) => useBatchExpansion(caseId, who), { initialProps: { caseId, who } });
}

describe("useBatchExpansion", () => {
  it("holds a choice with the case and the person it was made in and for", () => {
    const { result } = hold("c1", "analyst-1");
    act(() => result.current.ask(REQUEST));
    expect(result.current.asked).toMatchObject({ request: REQUEST, caseId: "c1", who: "analyst-1", n: 1 });
  });

  it("drops the choice when another case is opened, and does not bring it back", () => {
    const { result, rerender } = hold("c1", "analyst-1");
    act(() => result.current.ask(REQUEST));
    rerender({ caseId: "c2", who: "analyst-1" });
    expect(result.current.asked).toBeNull();
    rerender({ caseId: "c1", who: "analyst-1" });
    expect(result.current.asked).toBeNull();
  });

  it("drops the choice when someone else signs in in place", () => {
    const { result, rerender } = hold("c1", "analyst-1");
    act(() => result.current.ask(REQUEST));
    rerender({ caseId: "c1", who: "analyst-2" });
    expect(result.current.asked).toBeNull();
  });

  it("gives a choice made again its own panel", () => {
    const { result } = hold("c1", "analyst-1");
    act(() => result.current.ask(REQUEST));
    act(() => result.current.ask({ ...REQUEST, depth: 2 }));
    expect(result.current.asked).toMatchObject({ n: 2, request: { depth: 2 } });
  });

  it("holds nothing with no case open, and nothing once closed", () => {
    const none = hold(null, "analyst-1");
    act(() => none.result.current.ask(REQUEST));
    expect(none.result.current.asked).toBeNull();
    const { result } = hold("c1", "analyst-1");
    act(() => result.current.ask(REQUEST));
    act(() => result.current.close());
    expect(result.current.asked).toBeNull();
  });
});
