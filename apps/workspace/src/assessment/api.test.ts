import { afterEach, describe, expect, it, vi } from "vitest";

import { saveJudgement, UnverifiableCitationApiError } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("saveJudgement", () => {
  it("throws UnverifiableCitationApiError naming the specific citation on a 422 unverifiable_citation response", async () => {
    // The invisible-judgement defect's own fix, proven at the fetch-wrapper layer: the server's
    // named-citation error body (`services/api/app.py::_unverifiable_citation_handler`) must
    // reach the caller as a typed error carrying `citationIds`, not a bare "save failed" string a
    // `catch` block could only show generically.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: "unverifiable_citation",
          detail: "judgement j1: citation(s) doc-1 could not be confirmed as a visible graph node",
          citation_ids: ["doc-1"],
        }),
      }),
    );

    await expect(
      saveJudgement("http://localhost:8000", "tok", "inv-1", {
        investigation_id: "inv-1",
        statement: "Statement.",
        probability_band: "likely",
        supporting: ["doc-1"],
      }),
    ).rejects.toBeInstanceOf(UnverifiableCitationApiError);
  });

  it("carries the exact citation_ids array through, not just the message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: "unverifiable_citation",
          detail: "refused",
          citation_ids: ["node-a", "node-b"],
        }),
      }),
    );

    try {
      await saveJudgement("http://localhost:8000", "tok", "inv-1", {
        investigation_id: "inv-1",
        statement: "Statement.",
        probability_band: "likely",
        supporting: ["node-a", "node-b"],
      });
      expect.unreachable("saveJudgement should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(UnverifiableCitationApiError);
      expect((err as UnverifiableCitationApiError).citationIds).toEqual(["node-a", "node-b"]);
    }
  });

  it("a generic 422 with no citation_ids falls back to a plain Error, not the typed one", async () => {
    // Proves the branch above is real, not a catch-all: a companion case feeding a *different*
    // error shape must NOT produce `UnverifiableCitationApiError` — otherwise the type would be
    // meaningless to a caller trying to distinguish "which citation" from "some other failure".
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ error: "no_supporting_reference", detail: "no evidence" }),
      }),
    );

    await expect(
      saveJudgement("http://localhost:8000", "tok", "inv-1", {
        investigation_id: "inv-1",
        statement: "Statement.",
        probability_band: "likely",
        supporting: [],
      }),
    ).rejects.not.toBeInstanceOf(UnverifiableCitationApiError);
  });
});
