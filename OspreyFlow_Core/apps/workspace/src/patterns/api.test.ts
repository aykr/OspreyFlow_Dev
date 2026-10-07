import { afterEach, describe, expect, it, vi } from "vitest";

import type { SavedPattern } from "../../../../packages/schemas/generated";
import { listPatterns, loadPattern, savePattern } from "./api";

// `savePattern`/`listPatterns`/`loadPattern` are otherwise-thin `fetch` wrappers (`site/api.ts`'s
// own `api.test.ts` leaves those untested elsewhere in this codebase) — but their `!response.ok`
// check is exactly the branch `GlassCanvas.tsx`'s `findPaths` was found to get wrong (`if
// (!response.ok) return;`, silently dropping a failed save/load with nothing surfaced to the
// analyst). These pin down that each of the three new calls throws instead, so a failed save or
// load produces an error `QueryBuilderPanel.tsx` can show rather than a call that looks like it
// worked.

const SAVED: SavedPattern = {
  id: "row-1",
  pattern_id: "pattern-1",
  version: 1,
  name: "Common contacts",
  owner_id: "analyst-1",
  created_at: "2026-01-01T00:00:00Z",
  definition: { nodes: [], edges: [], limit: 1000 },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("savePattern", () => {
  it("returns the parsed SavedPattern on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => SAVED }),
    );
    const result = await savePattern("http://localhost:8000", "tok", "inv-1", {
      pattern_id: null,
      name: "Common contacts",
      definition: { nodes: [], edges: [], limit: 1000 },
    });
    expect(result).toEqual(SAVED);
  });

  it("throws — does not silently drop a failed save — on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(
      savePattern("http://localhost:8000", "tok", "inv-1", {
        pattern_id: null,
        name: "Common contacts",
        definition: { nodes: [], edges: [], limit: 1000 },
      }),
    ).rejects.toThrow("POST .../patterns/save failed: 500");
  });
});

describe("listPatterns", () => {
  it("unwraps the { patterns } envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ patterns: [SAVED] }) }),
    );
    const result = await listPatterns("http://localhost:8000", "tok", "inv-1");
    expect(result).toEqual([SAVED]);
  });

  it("throws on a non-ok response rather than returning an empty list indistinguishable from 'none saved'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));
    await expect(listPatterns("http://localhost:8000", "tok", "inv-1")).rejects.toThrow(
      "GET .../patterns failed: 401",
    );
  });
});

describe("loadPattern", () => {
  it("returns the parsed SavedPattern on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => SAVED }));
    const result = await loadPattern("http://localhost:8000", "tok", "inv-1", "pattern-1");
    expect(result).toEqual(SAVED);
  });

  it("throws — does not silently drop a failed load — on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(loadPattern("http://localhost:8000", "tok", "inv-1", "pattern-1")).rejects.toThrow(
      "GET .../patterns/pattern-1 failed: 404",
    );
  });
});

describe("ADR-099 Amendment 3: saved patterns are asked of the case", () => {
  it("saves, lists and loads under the case, since a pattern belongs to its dataset", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...SAVED, patterns: [SAVED] }) });
    vi.stubGlobal("fetch", fetcher);
    await savePattern("http://api", "tok", "inv-1", {
      pattern_id: null,
      name: "x",
      definition: { nodes: [], edges: [], limit: 1000 },
    });
    await listPatterns("http://api", "tok", "inv-1");
    await loadPattern("http://api", "tok", "inv-1", "p 1");
    expect(fetcher.mock.calls.map((c) => c[0])).toEqual([
      "http://api/v1/investigations/inv-1/patterns/save",
      "http://api/v1/investigations/inv-1/patterns",
      "http://api/v1/investigations/inv-1/patterns/p%201",
    ]);
  });
});

