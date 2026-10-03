import { describe, expect, it, vi } from "vitest";
import { fetchWouldAdd } from "./expansionPreview";

/** The count an expansion would add, asked of `/expand/preview`. A failed question is
 * "unavailable", never a number. */

function reply(ok: boolean, body: unknown = {}): Response {
  return {
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
  } as unknown as Response;
}

const base = {
  apiBaseUrl: "http://api",
  bearerToken: "tok",
  investigationId: "inv1",
};

describe("fetchWouldAdd", () => {
  it("asks the preview route about the node and relationship types, with the token", async () => {
    const fetcher = vi.fn(async () =>
      reply(true, { candidate_node_count: 10 }),
    );
    await fetchWouldAdd(fetcher, {
      ...base,
      nodeId: "n1",
      edgeTypes: ["USES"],
      currentOrder: 4,
    });
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("http://api/v1/investigations/inv1/expand/preview");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok",
    );
    expect(JSON.parse(String(init.body))).toEqual({
      request: { node_ids: ["n1"], depth: 1, edge_types: ["USES"] },
    });
  });

  it("asks about every relationship type when none is named", async () => {
    const fetcher = vi.fn(async () =>
      reply(true, { candidate_node_count: 10 }),
    );
    await fetchWouldAdd(fetcher, {
      ...base,
      nodeId: "n1",
      edgeTypes: null,
      currentOrder: 4,
    });
    const [, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body)).request.edge_types).toBeNull();
  });

  it("is the working set's size after the expansion minus its size now", async () => {
    const fetcher = vi.fn(async () =>
      reply(true, { candidate_node_count: 1095 }),
    );
    expect(
      await fetchWouldAdd(fetcher, {
        ...base,
        nodeId: "n1",
        edgeTypes: null,
        currentOrder: 5,
      }),
    ).toBe(1090);
  });

  it("is 'unavailable' when the server refuses", async () => {
    const fetcher = vi.fn(async () => reply(false));
    expect(
      await fetchWouldAdd(fetcher, {
        ...base,
        nodeId: "n1",
        edgeTypes: null,
        currentOrder: 5,
      }),
    ).toBe("unavailable");
  });

  it("is 'unavailable' when the request fails outright", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("offline");
    });
    expect(
      await fetchWouldAdd(fetcher, {
        ...base,
        nodeId: "n1",
        edgeTypes: null,
        currentOrder: 5,
      }),
    ).toBe("unavailable");
  });

  it("asks about one step unless told to look further, and passes the depth it is given", async () => {
    const fetcher = vi.fn(async () => reply(true, { candidate_node_count: 10 }));
    await fetchWouldAdd(fetcher, { ...base, nodeId: "n1", edgeTypes: null, currentOrder: 4 });
    await fetchWouldAdd(fetcher, { ...base, nodeId: "n1", edgeTypes: null, currentOrder: 4, depth: 3 });
    const depthOf = (call: number) =>
      JSON.parse(((fetcher.mock.calls[call] as unknown as [string, RequestInit])[1].body as string)).request.depth;
    expect(depthOf(0)).toBe(1);
    expect(depthOf(1)).toBe(3);
  });
});
