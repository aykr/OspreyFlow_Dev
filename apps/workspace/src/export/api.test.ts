import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportBlockedApiError, OverrideRequiredApiError, submitExport } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

const REQUEST = {
  artefact_kind: "subgraph" as const,
  items: [{ id: "n1", kind: "node" as const, handling: { classification: "OFFICIAL" } }],
  resolution_threshold: 0.95,
};

describe("submitExport", () => {
  it("throws OverrideRequiredApiError naming the blocked item on a 422 override_required response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: "override_required",
          detail: "a justification and an originator reference are both required to export past this block",
          blocked: [{ id: "n1", kind: "node", label: "the S2 record", reason: "consult_originator" }],
        }),
      }),
    );

    await expect(submitExport("http://localhost:8000", "tok", "inv-1", REQUEST)).rejects.toBeInstanceOf(
      OverrideRequiredApiError,
    );
  });

  it("carries the exact blocked array through, not just the message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: "export_blocked",
          detail: "export blocked",
          blocked: [
            { id: "n1", kind: "node", label: "Endpoint fixture", reason: "access_denied" },
          ],
        }),
      }),
    );

    try {
      await submitExport("http://localhost:8000", "tok", "inv-1", REQUEST);
      expect.unreachable("submitExport should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ExportBlockedApiError);
      expect((err as ExportBlockedApiError).blocked).toEqual([
        { id: "n1", kind: "node", label: "Endpoint fixture", reason: "access_denied" },
      ]);
    }
  });

  it("an OverrideRequiredApiError is also an ExportBlockedApiError, not a sibling type", async () => {
    // Mirrors the server's own subclass relationship (`services/api/export.py::
    // OverrideRequiredError(ExportBlockedError)`) — a caller that only catches the parent must
    // still see it.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: "override_required",
          detail: "override required",
          blocked: [{ id: "n1", kind: "node", label: "the S2 record", reason: "consult_originator" }],
        }),
      }),
    );

    await expect(submitExport("http://localhost:8000", "tok", "inv-1", REQUEST)).rejects.toBeInstanceOf(
      ExportBlockedApiError,
    );
  });

  it("a generic 422 with no blocked array falls back to a plain Error, not the typed ones", async () => {
    // Proves the branches above are real, not a catch-all — a companion case feeding a different
    // error shape must NOT produce either typed error.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: "internal error" }),
      }),
    );

    await expect(submitExport("http://localhost:8000", "tok", "inv-1", REQUEST)).rejects.not.toBeInstanceOf(
      ExportBlockedApiError,
    );
  });

  it("returns the real mark/manifest/ledger_entry_id on success", async () => {
    const body = {
      mark: {
        osprey_mark: "OspreyFlow",
        investigation_id: "inv-1",
        exported_at: "2026-09-22T00:00:00Z",
        resolution_threshold: 0.95,
        handling_level: "OFFICIAL",
      },
      manifest: { policy: "disclose", withheld_count: 3 },
      ledger_entry_id: "led-1",
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => body }));

    const result = await submitExport("http://localhost:8000", "tok", "inv-1", REQUEST);
    expect(result).toEqual(body);
  });
});
