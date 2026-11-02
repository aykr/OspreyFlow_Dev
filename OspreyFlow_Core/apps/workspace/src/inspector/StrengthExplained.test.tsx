// @vitest-environment jsdom
// ADR-139 decision 9: the Inspector explains a link's strength (its count against what is heavy, its
// recency, the rule and version, each influencer applied with the kind of record that evidenced it)
// and what its two ends share, rarest first; and, for two nodes selected, what those two share. It
// says only what the reader's own reads gave it: the sent payload has no count to say.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Edge } from "../../../../packages/schemas/generated";
import { PairShared, StrengthExplained } from "./StrengthExplained";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

function node(id: string, type: string, name: string) {
  return {
    id, type, properties: { name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed" },
  }; // prettier-ignore
}

const RARE = node("x1", "Endpoint", "07700 900640");
const COMMON = node("x2", "Endpoint", "07700 900111");

function serve() {
  const sent: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body ?? "null")));
      if (url.endsWith("/connection-strength"))
        return json({
          links: [{
            edge_id: "e1", edge_type: "SHARED_CELL_WITH", base_weight: 0.7, strength: 0.86, parameter_set: "3/SHARED_CELL_WITH",
            heavy: 12, fixed: null, occurrences: 6, last_seen: "2026-04-30T00:00:00Z",
            applied: [
              { id: "direct", label: "Direct link", change: "add", size: 0.1348, layer: "file", record_kind: null },
              { id: "incident-source", label: "Evidenced by an incident", change: "add", size: 0.1348, layer: "installation", record_kind: "Incident" },
            ],
          }],
          legend: { influencers: [], direct_link_types: [], switched_off: [], rarity_note: "" },
        }); // prettier-ignore
      return json({
        scope: "dataset",
        node_values: {},
        pairs: [{ a: "p1", b: "p2", score: 2.4, dataset: "prison-intelligence", shared: [
          { node: RARE, score: 2.4 }, { node: COMMON, score: 0.02 }] }],
      }); // prettier-ignore
    }),
  );
  return sent;
}

const EDGE = { id: "e1", type: "SHARED_CELL_WITH", source: "p1", target: "p2" } as unknown as Edge;

describe("StrengthExplained", () => {
  it("explains the link's strength and ranks what its ends share, rarest first", async () => {
    const sent = serve();
    render(<StrengthExplained apiBaseUrl="http://api.invalid" bearerToken="t" investigationId="c1" edge={EDGE} />);
    const lines = await screen.findByRole("list", { name: "What this link's strength rests on" });
    expect(lines.textContent).toContain("Seen 6 times; 12 is heavy for “SHARED_CELL_WITH”.");
    expect(lines.textContent).toContain("Last seen on 30 April 2026.");
    expect(lines.textContent).toContain("weights version 3, the rule for “SHARED_CELL_WITH”");
    expect(lines.textContent).toContain("Direct link (shipped with OspreyFlow), a direct link");
    expect(lines.textContent).toContain("because an Incident you can see evidences it");
    const shared = await screen.findByRole("list", { name: "Shared attributes, rarest first" });
    expect([...shared.querySelectorAll("li")].map((li) => li.textContent)).toEqual([
      "Endpoint · 07700 9006402.40",
      "Endpoint · 07700 9001110.02",
    ]);
    expect(screen.getByText(/worked out in prison-intelligence, over what you may see/)).toBeTruthy();
    // It asked for this link alone and for its two ends as the pair.
    expect(sent).toContainEqual({ edge_ids: ["e1"] });
    expect(sent).toContainEqual({ scope: "dataset", pairs: [["p1", "p2"]] });
  });

  it("explains two nodes selected together", async () => {
    serve();
    render(<PairShared apiBaseUrl="http://api.invalid" bearerToken="t" investigationId="c1" a="p1" b="p2" />);
    expect(await screen.findByText("What they share, rarest first")).toBeTruthy();
    expect((await screen.findByRole("list", { name: "Shared attributes, rarest first" })).children).toHaveLength(2);
  });
});
