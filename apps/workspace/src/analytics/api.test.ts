import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSightings } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchSightings", () => {
  it("posts the request to /v1/analytics/sightings and returns the ordered sightings", async () => {
    const sightings = [
      { occurred_at: "2026-01-01T08:00:00Z", lat: 51.5, lon: -0.1 },
      { occurred_at: "2026-01-01T09:00:00Z", lat: 51.6, lon: -0.2 },
    ];
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => sightings,
    });
    vi.stubGlobal("fetch", fetchMock);

    const request = {
      filter: { investigation_scope: "inv-1", window: null, node_ids: ["n1"], edge_types: [] },
    };
    const result = await fetchSightings("http://localhost:8000", "tok", request);

    expect(result).toEqual(sightings);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/v1/analytics/sightings",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
      }),
    );
  });

  it("throws on a non-OK response, the same shape every other fetch wrapper in this module uses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));

    await expect(
      fetchSightings("http://localhost:8000", "tok", {
        filter: { investigation_scope: "inv-1", window: null, node_ids: [], edge_types: [] },
      }),
    ).rejects.toThrow(/sightings failed: 403/);
  });
});
