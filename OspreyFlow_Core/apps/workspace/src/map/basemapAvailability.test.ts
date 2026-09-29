import { describe, expect, it, vi } from "vitest";

import {
  BasemapUnavailableError,
  checkBasemapAvailable,
} from "./basemapAvailability";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("checkBasemapAvailable", () => {
  it("resolves when the ranged request succeeds (206)", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response(new Uint8Array([1]), { status: 206 }));

    await expect(
      checkBasemapAvailable(
        "http://api/v1/map/local-source/osm-local",
        "tok",
        fetchImpl,
      ),
    ).resolves.toBeUndefined();
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api/v1/map/local-source/osm-local",
      expect.objectContaining({
        headers: { Range: "bytes=0-0", Authorization: "Bearer tok" },
      }),
    );
  });

  it("throws BasemapUnavailableError with the route's own detail on a 404", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(404, {
          detail: "basemap not built — run scripts.build_local_basemap",
        }),
      );

    await expect(
      checkBasemapAvailable(
        "http://api/v1/map/local-source/osm-local",
        "tok",
        fetchImpl,
      ),
    ).rejects.toThrow(BasemapUnavailableError);
    await expect(
      checkBasemapAvailable(
        "http://api/v1/map/local-source/osm-local",
        "tok",
        fetchImpl,
      ),
    ).rejects.toThrow(/basemap not built/);
  });

  it("falls back to a generic detail when the 404 body isn't the expected shape", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response("not json", { status: 404 }));

    await expect(
      checkBasemapAvailable(
        "http://api/v1/map/local-source/osm-local",
        undefined,
        fetchImpl,
      ),
    ).rejects.toThrow(/basemap not built/);
  });

  it("throws a plain error for any other failing status", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response("", { status: 500 }));

    await expect(
      checkBasemapAvailable(
        "http://api/v1/map/local-source/osm-local",
        undefined,
        fetchImpl,
      ),
    ).rejects.toThrow(/500/);
  });

  it("omits the Authorization header when no bearer token is given", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response(new Uint8Array([1]), { status: 206 }));

    await checkBasemapAvailable(
      "http://api/v1/map/local-source/osm-local",
      undefined,
      fetchImpl,
    );

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api/v1/map/local-source/osm-local",
      expect.objectContaining({ headers: { Range: "bytes=0-0" } }),
    );
  });
});
