import { describe, expect, it, vi } from "vitest";
import { removeFromWorkingSet } from "./removeNodes";

const base = {
  apiBaseUrl: "http://api",
  bearerToken: "tok",
  investigationId: "inv-1",
};

function reply(status: number, body: unknown = {}): typeof fetch {
  return vi.fn(async () => new Response(JSON.stringify(body), { status }));
}

describe("removeFromWorkingSet", () => {
  it("sends a DELETE for exactly the chosen nodes, with the bearer token", async () => {
    const fetcher = reply(200, { seq: 7 });
    await removeFromWorkingSet(fetcher, { ...base, nodeIds: ["a", "b"] });
    const [url, init] = (fetcher as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("http://api/v1/investigations/inv-1/nodes");
    expect(init.method).toBe("DELETE");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(JSON.parse(init.body)).toEqual({ node_ids: ["a", "b"] });
  });

  it("returns the sequence number the server gave, so the caller can apply the removal", async () => {
    const result = await removeFromWorkingSet(reply(200, { seq: 7 }), {
      ...base,
      nodeIds: ["a"],
    });
    expect(result).toEqual({ ok: true, seq: 7 });
  });

  it("asks the server nothing when there is nothing to remove", async () => {
    const fetcher = reply(200, { seq: 1 });
    const result = await removeFromWorkingSet(fetcher, { ...base, nodeIds: [] });
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.ok).toBe(false);
  });

  it("never reports success when the server refuses", async () => {
    const result = await removeFromWorkingSet(reply(403), {
      ...base,
      nodeIds: ["a"],
    });
    expect(result).toEqual({
      ok: false,
      message: expect.stringContaining("403"),
    });
  });

  it("never reports success when the request cannot be sent", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("network down");
    }) as unknown as typeof fetch;
    const result = await removeFromWorkingSet(fetcher, {
      ...base,
      nodeIds: ["a"],
    });
    expect(result.ok).toBe(false);
  });

  it("treats a reply without a sequence number as a failure, not a success", async () => {
    const result = await removeFromWorkingSet(reply(200, {}), {
      ...base,
      nodeIds: ["a"],
    });
    expect(result.ok).toBe(false);
  });
});
