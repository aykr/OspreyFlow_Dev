// @vitest-environment jsdom
// ADR-139 Amendment 2 in the Glass: the legend's composition indicator, the Inspector's composition,
// rarity measure and the raw sum on the client's scale under client parity, a dataset trigger and a
// shared value said in words, the case's composition control and the installation's choices in the
// Monitoring tab, and a rule's strength figure on either scale. Synthetic (rule 9).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Edge, LinkStrength, StrengthInfluencer, StrengthLegend } from "../../../../packages/schemas/generated";
import { emptyDraft, toSentence, fromSentence, unfinished } from "../alerts/sentence";
import { CanvasLegend } from "../canvas/CanvasLegend";
import { PairShared, StrengthExplained } from "../inspector/StrengthExplained";
import { StrengthPanel } from "./StrengthPanel";
import { compositionWords, influencerWords, strengthExplanation, triggerWords } from "./words";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

const PARITY_LINK: LinkStrength = {
  edge_id: "e1", edge_type: "COMMUNICATED_WITH", base_weight: 0.7, strength: 0.6225, parameter_set: "3/COMMUNICATED_WITH",
  heavy: 40, fixed: null, occurrences: 3, last_seen: "2026-04-30T00:00:00Z", composition: "client_parity",
  rarity_term: 0.75, raw_sum: 1.05, dataset: "calls",
  applied: [
    { id: "direct", label: "Direct link", change: "add", size: 0.2, layer: "file", record_kind: null, dataset: null },
    { id: "source-calls", label: "From calls", change: "add", size: 0.1, layer: "installation", record_kind: null, dataset: "calls" },
  ],
}; // prettier-ignore

const LEGEND: StrengthLegend = {
  influencers: [], direct_link_types: [], switched_off: [], rarity_note: "Rarity is over what you may see.",
  composition: "client_parity", composition_layer: "case", rarity_measure: "share",
}; // prettier-ignore

describe("client parity in words", () => {
  it("explains a parity link from its rarity term and adds, and gives the raw sum and the drawn strength", () => {
    const lines = strengthExplanation(PARITY_LINK);
    expect(lines[0]).toContain("Client parity");
    expect(lines.join(" ")).not.toContain("Seen 3 times");
    expect(lines).toContain("Its rarity term 0.7500, in calls: one less its share of the links of its type you can see there.");
    expect(lines).toContain("From calls (installation-wide), because it is in calls: adds 0.1.");
    expect(lines[lines.length - 1]).toBe("Raw sum 1.0500 on the client's scale; drawn at 0.62 on 0 to 1.");
  });

  it("says a dataset trigger and a shared value", () => {
    const byDataset = {
      id: "source-assaults", label: "From assaults", trigger: { kind: "dataset", datasets: ["assaults", "disorders"] },
      link_types: ["IN_CONFLICT_WITH", "SHARED_VALUE"], change: "add", size: 0.3,
    } as unknown as StrengthInfluencer; // prettier-ignore
    expect(triggerWords(byDataset)).toBe("when the link is evidenced in assaults or disorders");
    expect(influencerWords(byDataset)).toBe(
      "IN_CONFLICT_WITH and a pair linked through a shared value: adds 0.3 to the score before the curve, when the link is evidenced in assaults or disorders",
    );
  });

  it("names the composition in force, where it came from, and the rarity measure", () => {
    expect(compositionWords(LEGEND)).toBe(
      "Composition: client parity (this case's own): strength is rarity plus the adds, with no count or recency, drawn on 0 to 1; rarity by share of pair links (the client's).",
    );
    expect(compositionWords({ composition: "standard", composition_layer: "file", rarity_measure: "idf" })).toBe(
      "Composition: standard (shipped with OspreyFlow): strength is the stored weight with the influencers; rarity by inverse frequency (IDF).",
    );
  });
});

describe("the legend's composition indicator", () => {
  it("shows the composition, marked as a case override", () => {
    render(<CanvasLegend types={[{ type: "Person", count: 2, visual: undefined } as never]} strength={LEGEND} />);
    const indicator = screen.getByLabelText("Composition");
    expect(indicator.textContent).toContain("Case override");
    expect(indicator.textContent).toContain("Composition: client parity");
  });
});

describe("the Inspector under client parity", () => {
  const edge = { id: "e1", type: "COMMUNICATED_WITH", source: "a", target: "b" } as unknown as Edge;

  it("names the composition and shows the raw sum on the client's scale", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/connection-strength")
          ? json({ links: [PARITY_LINK], legend: LEGEND })
          : json({ scope: "dataset", node_values: {}, pairs: [], measure: "share", composition: "client_parity" }),
      ),
    );
    render(<StrengthExplained apiBaseUrl="http://x.invalid" bearerToken="t" investigationId="inv-1" edge={edge} />);
    expect((await screen.findByLabelText("Composition")).textContent).toBe("Composition: Client parity");
    expect(screen.getByLabelText("Raw sum on the client's scale").textContent).toContain("1.0500");
  });

  it("says a pair's rarity measure and its parity sum through what they share", async () => {
    const shared = {
      id: "ph1", type: "Endpoint", properties: { value_normalised: "+447700900001" },
      provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
      handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed" },
    }; // prettier-ignore
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({
          scope: "dataset", node_values: {}, measure: "share", composition: "client_parity",
          pairs: [{ a: "a", b: "b", score: 0.8333, dataset: "phones", shared: [{ node: shared, score: 0.8333 }],
            parity_raw: 0.8833, parity_strength: 0.237,
            parity_applied: [{ id: "source-phones", label: "From phones", change: "add", size: 0.05, layer: "installation", dataset: "phones" }] }],
        }), // prettier-ignore
      ),
    );
    render(<PairShared apiBaseUrl="http://x.invalid" bearerToken="t" investigationId="inv-1" a="a" b="b" />);
    expect((await screen.findByText(/measured by share of pair links/)).textContent).toContain("worked out in phones");
    expect(screen.getByLabelText("Client parity through what they share").textContent).toContain("raw sum 0.8833");
  });
});

describe("the Monitoring tab's composition controls", () => {
  function serve(override: unknown = null) {
    const sent: { method: string; url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        sent.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
        if (url.endsWith("/v1/strength-influencers") && method === "GET")
          return json({ versions: [], defaults: [], default_composition: "standard", default_rarity_measure: "share" });
        if (url.endsWith("/v1/strength-influencers"))
          return json({ version: 1, influencers: [], status: "pending", proposed_by: "me", proposed_at: "2026-11-02T00:00:00Z" });
        return json({ legend: { ...LEGEND, composition: "standard", composition_layer: "file" }, override, can_override: true });
      }),
    );
    return sent;
  }
  const props = {
    apiBaseUrl: "http://x.invalid", bearerToken: "t", investigationId: "inv-1", accountId: "me", entityTypes: [],
    edgeTypes: [],
  }; // prettier-ignore

  it("lets the case's Author switch the case to client parity, sent with the override", async () => {
    const sent = serve();
    render(<StrengthPanel {...props} canManage={false} />);
    const select = await screen.findByLabelText("How strength is worked out in this case");
    fireEvent.change(select, { target: { value: "client_parity" } });
    fireEvent.click(screen.getByRole("button", { name: "Save this case's influencers" }));
    await waitFor(() => expect(sent.some((c) => c.method === "PUT")).toBe(true));
    expect(sent.find((c) => c.method === "PUT")?.body).toEqual({
      added: [], switched_off: [], composition: "client_parity", words: "",
    }); // prettier-ignore
  });

  it("reads the case's own composition back into the control", async () => {
    serve({ added: [], switched_off: [], composition: "client_parity", words: "" });
    render(<StrengthPanel {...props} canManage={false} />);
    await waitFor(() =>
      expect((screen.getByLabelText("How strength is worked out in this case") as HTMLSelectElement).value).toBe("client_parity"),
    );
  });

  it("proposes an installation version that chooses its composition and rarity measure", async () => {
    const sent = serve();
    render(<StrengthPanel {...props} canManage />);
    fireEvent.click(await screen.findByRole("button", { name: "Propose a new version" }));
    fireEvent.change(screen.getByLabelText("Composition"), { target: { value: "client_parity" } });
    fireEvent.change(screen.getByLabelText("Rarity measure"), { target: { value: "idf" } });
    fireEvent.click(screen.getByRole("button", { name: "Propose for approval" }));
    await waitFor(() => expect(sent.some((c) => c.method === "POST")).toBe(true));
    expect(sent.find((c) => c.method === "POST")?.body).toMatchObject({ composition: "client_parity", rarity_measure: "idf" });
  });
});

describe("a rule's strength figure on either scale", () => {
  it("sends the client's scale only when chosen, and reads it back", () => {
    const draft = { ...emptyDraft("Person"), strength: "connection_strength" as const, reaches: "1.2" };
    expect(unfinished(draft)).toBe("A connection strength is at most 1; choose the client's scale for a raw sum.");
    const client = { ...draft, strengthScale: "client" as const };
    expect(unfinished(client)).toBeNull();
    const sentence = toSentence(client);
    expect((sentence as unknown as { strength: Record<string, unknown> }).strength).toMatchObject({ reaches: 1.2, scale: "client" });
    expect(fromSentence(sentence).strengthScale).toBe("client");
    const drawn = toSentence({ ...draft, reaches: "0.8" });
    expect((drawn as unknown as { strength: Record<string, unknown> }).strength).not.toHaveProperty("scale");
  });
});
