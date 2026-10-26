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

  it("names the new case when asked to, and only then (ADR-098 decision 4)", async () => {
    const fetcher = reply(201, { id: "b-1", name: "Questions on 2 documents" });
    await branchSelection(fetcher, { ...base, nodeIds: ["d1", "d2"], name: "Questions on 2 documents" });
    const [, init] = (fetcher as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(JSON.parse(init.body)).toEqual({ node_ids: ["d1", "d2"], name: "Questions on 2 documents" });
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

  // ADR-128 decision 2 (B3): after Select what is lit, with the window still set, the window goes
  // with the selection and the server derives the slice from it.
  it("sends the window with the nodes when one is given, and not otherwise", async () => {
    const fetcher = reply(201, { id: "b-1", name: "5 Jan – 30 Apr 2026, selected" });
    await branchSelection(fetcher, {
      ...base,
      nodeIds: ["a", "b"],
      name: "5 Jan – 30 Apr 2026, selected",
      window: { validFrom: "2026-01-05T00:00:00Z", validTo: "2026-05-01T00:00:00Z" },
    });
    const [, init] = (fetcher as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(JSON.parse(init.body)).toEqual({
      node_ids: ["a", "b"],
      name: "5 Jan – 30 Apr 2026, selected",
      window: { valid_from: "2026-01-05T00:00:00Z", valid_to: "2026-05-01T00:00:00Z" },
    });
  });

  it("sends a window with no end as an open end", async () => {
    const fetcher = reply(201, { id: "b-1", name: "x" });
    await branchSelection(fetcher, {
      ...base,
      nodeIds: ["a"],
      window: { validFrom: "2026-01-05T00:00:00Z", validTo: null },
    });
    const [, init] = (fetcher as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(JSON.parse(init.body).window).toEqual({
      valid_from: "2026-01-05T00:00:00Z",
      valid_to: null,
    });
  });

  it("says what a slice over the working-set cap came to, and that no tab was made", async () => {
    const result = await branchSelection(
      reply(409, {
        error: "limit_exceeded",
        cap_kind: "nodes",
        cap: 50000,
        would_be: 61234,
        options: ["branch", "filter", "promote_to_batch"],
      }),
      { ...base, nodeIds: ["a"], window: { validFrom: "2026-01-05T00:00:00Z", validTo: null } },
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.message).toContain("61,234");
      expect(result.message).toContain("50,000");
      expect(result.message).toMatch(/no tab was made/i);
    }
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
