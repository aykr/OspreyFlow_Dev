import { afterEach, describe, expect, it, vi } from "vitest";

import { extractDocument } from "./readerApi";

afterEach(() => vi.unstubAllGlobals());

describe("extractDocument refusals (ADR-095)", () => {
  it("says the server's own sentence when the model cannot answer yet, not a status number", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => ({ error: "model_unavailable", detail: "The model is still downloading." }),
      })),
    );
    await expect(extractDocument("http://api.test", "tok", "inv-1", "doc-1")).rejects.toThrow(
      "The model is still downloading.",
    );
  });

  it("still says a status when there is no sentence to give", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => { throw new Error("no body"); } })));
    await expect(extractDocument("http://api.test", "tok", "inv-1", "doc-1")).rejects.toThrow("(500)");
  });
});
