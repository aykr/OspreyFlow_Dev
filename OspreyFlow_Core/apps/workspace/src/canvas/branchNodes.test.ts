import { describe, expect, it, vi } from "vitest";
import { branchSelection } from "./branchNodes";

const base = { apiBaseUrl: "http://api", bearerToken: "tok", investigationId: "inv-1" };

function reply(status: number, body: unknown = {}): typeof fetch {
  return vi.fn(async () => new Response(JSON.stringify(body), { status }));
}

describe("branchSelection", () => {
  it("posts exactly the chosen nodes to the case's branch route, with the bearer token", async () => {
    const fetcher = reply(201, { id: "b-1", name: "Fixture Corp · 2 selected" });
    await branchSelection(fetcher, { ...base, nodeIds: ["a", "b"] });
    const [url, init] = (fetcher as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("http://api/v1/investigations/inv-1/branch");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(JSON.parse(init.body)).toEqual({ node_ids: ["a", "b"] });
  });

  it("returns the new case so the caller can open it", async () => {
    const result = await branchSelection(reply(201, { id: "b-1", name: "Tab" }), {
      ...base,
      nodeIds: ["a"],
    });
    expect(result).toEqual({ ok: true, id: "b-1", name: "Tab" });
  });

  it("asks the server nothing when nothing is chosen", async () => {
    const fetcher = reply(201, { id: "b-1", name: "x" });
    const result = await branchSelection(fetcher, { ...base, nodeIds: [] });
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.ok).toBe(false);
  });

  it("says when none of the chosen nodes could be branched, without saying why", async () => {
    const result = await branchSelection(reply(422, { error: "nothing_to_branch" }), {
      ...base,
      nodeIds: ["a"],
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.message).toMatch(/none of the selected nodes could be branched/i);
      expect(result.message).not.toMatch(/hidden|clearance|permission/i);
    }
  });

  it("explains a refusal for lack of access", async () => {
    const result = await branchSelection(reply(403, {}), { ...base, nodeIds: ["a"] });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.message).toMatch(/editor/i);
  });

  it("never reports success when the reply is not a case", async () => {
    const result = await branchSelection(reply(201, {}), { ...base, nodeIds: ["a"] });
    expect(result.ok).toBe(false);
  });

  it("reports a network failure instead of throwing", async () => {
    const failing = vi.fn(async () => {
      throw new Error("offline");
    }) as unknown as typeof fetch;
    const result = await branchSelection(failing, { ...base, nodeIds: ["a"] });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.message).toContain("offline");
  });
});
