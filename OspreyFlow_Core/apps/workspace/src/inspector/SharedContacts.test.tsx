// @vitest-environment jsdom
// ADR-100 Amendment 7 decision 4: who shares contacts with the selected node, asked of that node
// alone, by each link type it can have contacts by; the most shared first, saying of how many; a
// pick puts the two and what they share on the canvas with one action; a refusal said in words.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EdgeTypeDef, Node } from "../../../../packages/schemas/generated";
import { SharedContacts } from "./SharedContacts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function node(id: string, type = "Endpoint"): Node {
  return {
    id,
    type,
    properties: { name: id },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  } as unknown as Node;
}

const EDGE_TYPES = [
  { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"] },
  { name: "USES", from: ["Person"], to: ["Endpoint"] },
  { name: "SAME_AS", from: ["*"], to: ["*"], system: true },
] as unknown as EdgeTypeDef[];

function serve(handler: (url: URL, method: string) => Response) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const parsed = new URL(url);
      calls.push(`${init?.method ?? "GET"} ${parsed.pathname}${parsed.search}`);
      return handler(parsed, init?.method ?? "GET");
    }),
  );
  return calls;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function mount(onDelta = vi.fn()) {
  render(
    <SharedContacts
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="c1"
      node={node("alice")}
      edgeTypes={EDGE_TYPES}
      onDelta={onDelta}
    />,
  );
  return onDelta;
}

describe("SharedContacts", () => {
  it("offers only the link types this node can have contacts by", () => {
    serve(() => json(200, { contacts: [], total: 0 }));
    mount();
    expect(screen.getByRole("button", { name: "Who shares two contacts by “Communicated with”?" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Uses/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Same as/ })).toBeNull();
  });

  it("lists the most shared first, says of how many, and puts a pair on the canvas with one action", async () => {
    const delta = { op: "add", seq: 4, nodes: [node("alice"), node("bob")], edges: [] };
    const calls = serve((url, method) => {
      if (method === "POST") return json(200, { delta, added_nodes: 3, added_links: 4 });
      return json(200, { contacts: [{ node: node("bob"), shared: 446 }, { node: node("carol"), shared: 12 }], total: 31 });
    });
    const onDelta = mount();
    fireEvent.click(screen.getByRole("button", { name: "Who shares two contacts by “Communicated with”?" }));
    expect(await screen.findByText("The 2 who share most of 31.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "bob · shares 446" }));
    expect(await screen.findByText("3 nodes and 4 links added.")).toBeTruthy();
    expect(onDelta).toHaveBeenCalledWith(delta);
    expect(calls).toContain("GET /v1/investigations/c1/nodes/alice/shared-contacts?edge_type=COMMUNICATED_WITH");
    expect(calls).toContain("POST /v1/investigations/c1/nodes/alice/shared-contacts/bob/canvas?edge_type=COMMUNICATED_WITH");
  });

  it("says plainly when nobody shares two, and a refusal in words", async () => {
    serve((_, method) => (method === "POST" ? json(409, {}) : json(200, { contacts: [], total: 0 })));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Who shares two contacts by “Communicated with”?" }));
    expect(await screen.findByText("Nobody you can see shares two.")).toBeTruthy();
    cleanup();
    serve(() => json(403, {}));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Who shares two contacts by “Communicated with”?" }));
    expect(await screen.findByText("Who shares contacts could not be read (403).")).toBeTruthy();
  });
});
