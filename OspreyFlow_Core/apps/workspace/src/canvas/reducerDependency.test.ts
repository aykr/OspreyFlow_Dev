import { describe, expect, it } from "vitest";

import { declareReducersReadItemStateOnly } from "./reducerDependency";

// The shape Sigma 4.0 gives a renderer with reducers: both analyses forced to "graph-state".
function renderer() {
  return {
    internals: { nodeStyleAnalysis: { dependency: "graph-state", xAttribute: "x", yAttribute: "y" } },
    edgeStyleAnalysis: { dependency: "graph-state", xAttribute: null, yAttribute: null },
  };
}

describe("declareReducersReadItemStateOnly", () => {
  it("tells the renderer its node and link reducers read each item's own state only", () => {
    const sigma = renderer();
    declareReducersReadItemStateOnly(sigma);
    expect(sigma.internals.nodeStyleAnalysis.dependency).toBe("item-state");
    expect(sigma.edgeStyleAnalysis.dependency).toBe("item-state");
  });

  it("refuses a renderer whose analysis is not where Sigma 4.0 keeps it", () => {
    expect(() => declareReducersReadItemStateOnly({ edgeStyleAnalysis: { dependency: "graph-state" } })).toThrow(
      /reducerDependency/,
    );
    expect(() => declareReducersReadItemStateOnly({ internals: { nodeStyleAnalysis: { dependency: "graph-state" } } })).toThrow();
  });

  it("refuses one whose analysis no longer marks the reducers as reading graph state", () => {
    const sigma = renderer();
    sigma.edgeStyleAnalysis.dependency = "static";
    expect(() => declareReducersReadItemStateOnly(sigma)).toThrow();
  });
});
