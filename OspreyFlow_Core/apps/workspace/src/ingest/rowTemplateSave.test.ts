// ADR-081 step D: Map's save of a recipe naming a Probabilistic type is refused with each problem
// named; the analyst is told those words, not a bare status.
import { afterEach, describe, expect, it, vi } from "vitest";

import { RowTemplateSaveError, updateRowTemplate } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("updateRowTemplate", () => {
  it("says what the recipe rules refused, problem by problem", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 422,
        json: async () => ({
          error: "recipe_rule",
          problems: ["'SAME_AS' is a Probabilistic relationship type.", "'X' is not a relationship type."],
        }),
      })),
    );
    const failure = await updateRowTemplate("http://api", "t", "r1", { entities: [], edges: [] }, []).catch(
      (e: unknown) => e,
    );
    expect(failure).toBeInstanceOf(RowTemplateSaveError);
    expect((failure as Error).message).toBe(
      "'SAME_AS' is a Probabilistic relationship type. 'X' is not a relationship type.",
    );
  });
});
