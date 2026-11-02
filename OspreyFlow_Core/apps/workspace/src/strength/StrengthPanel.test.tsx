// @vitest-environment jsdom
// ADR-139 decision 3 in the Monitoring place: the influencers in force; a case's own, changed by its
// Author alone (an Editor is shown them, not offered the change); the installation-wide set, whose
// waiting version a second holder of the right approves or sends back, never its proposer; and a
// new version proposed for approval. The data is synthetic (rule 9).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EdgeTypeDef, EntityTypeDef } from "../../../../packages/schemas/generated";
import { StrengthPanel } from "./StrengthPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const DIRECT = { id: "direct", label: "Direct link", link_types: ["VISITED"], change: "add", size: 0.1348, trigger: null, enabled: true };
const SOURCE = {
  id: "incident-source", label: "Evidenced by an incident", link_types: ["IN_CONFLICT_WITH"], change: "add", size: 0.1348,
  trigger: { entity_type: "Incident", property: "category", values: ["assault"] }, enabled: true,
}; // prettier-ignore

function legend(canOverride: boolean) {
  return {
    legend: {
      influencers: [
        { influencer: DIRECT, layer: "file", version: null },
        { influencer: SOURCE, layer: "file", version: null },
      ],
      direct_link_types: ["VISITED"],
      switched_off: [],
      rarity_note: "Shared-attribute rarity is worked out over what you may see.",
    },
    override: null,
    can_override: canOverride,
  };
}

const PENDING = {
  version: 2, influencers: [DIRECT], status: "pending", proposed_by: "maker", proposed_at: "2026-11-02T09:00:00Z",
  words: "the client's sizes", in_force: false, proposed_by_name: "Mo Maker",
}; // prettier-ignore

type Call = { method: string; path: string; body: unknown };
function serve(history: unknown, canOverride = true) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ method, path, body });
      if (path === "/v1/investigations/c1/strength-influencers") return json(200, legend(canOverride));
      if (path === "/v1/strength-influencers" && method === "GET") return json(200, history);
      if (path === "/v1/strength-influencers" && method === "POST")
        return json(201, { ...PENDING, version: 3, influencers: body.influencers });
      if (path.endsWith("/approve")) return json(200, { ...PENDING, status: "approved", in_force: true });
      if (path.endsWith("/send-back")) return json(200, { ...PENDING, status: "sent_back" });
      return json(404, {});
    }),
  );
  return calls;
}

const ENTITIES = [
  { name: "Incident", pole_class: "event", properties: [{ name: "category", type: "enum", values: ["assault", "find"] }] },
] as unknown as EntityTypeDef[];
const EDGES = [
  { name: "VISITED", label: "Visited", from: ["Person"], to: ["Person"] },
  { name: "IN_CONFLICT_WITH", label: "In conflict with", from: ["Person"], to: ["Person"] },
] as unknown as EdgeTypeDef[];

function panel(accountId: string, canManage: boolean) {
  return render(
    <StrengthPanel
      apiBaseUrl="http://api.invalid"
      bearerToken="t"
      investigationId="c1"
      accountId={accountId}
      canManage={canManage}
      entityTypes={ENTITIES}
      edgeTypes={EDGES}
    />,
  );
}

describe("StrengthPanel", () => {
  it("lists the influencers in force and the direct link types", async () => {
    serve({ versions: [], defaults: [DIRECT, SOURCE] });
    panel("reader", false);
    const list = await screen.findByRole("list", { name: "Influencers in force" });
    expect(list.textContent).toContain("Visited: adds 0.13 to the score before the curve, always (these are direct links)");
    expect(screen.getByText(/Direct links: Visited\./)).toBeTruthy();
    expect(screen.queryByText("Installation-wide influencers")).toBeNull();
  });

  it("offers a second holder Approve, and sends the approval", async () => {
    const calls = serve({ versions: [PENDING], defaults: [DIRECT, SOURCE] });
    panel("checker", true);
    const approve = await screen.findByRole("button", { name: "Approve version 2" });
    expect((approve as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(approve);
    await screen.findByText("Version 2 is approved and in force.");
    expect(calls.some((c) => c.method === "POST" && c.path === "/v1/strength-influencers/2/approve")).toBe(true);
  });

  it("never offers its proposer the approval, and says why; they may withdraw it", async () => {
    const calls = serve({ versions: [PENDING], defaults: [DIRECT, SOURCE] });
    panel("maker", true);
    const approve = await screen.findByRole("button", { name: "Approve version 2" });
    expect((approve as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("You proposed it, so a second person with the right must approve it.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Why it goes back (required)"), { target: { value: "wrong sizes" } });
    fireEvent.click(screen.getByRole("button", { name: "Withdraw it" }));
    await screen.findByText("Version 2 is sent back.");
    expect(calls.find((c) => c.path.endsWith("/send-back"))?.body).toEqual({ words: "wrong sizes" });
  });

  it("proposes a new version starting from what is in force, with an influencer added", async () => {
    const calls = serve({ versions: [], defaults: [DIRECT, SOURCE] });
    panel("maker", true);
    fireEvent.click(await screen.findByRole("button", { name: "Propose a new version" }));
    const forms = screen.getAllByLabelText("Label in the legend");
    const form = forms[forms.length - 1]!;
    fireEvent.change(form, { target: { value: "Find in a cell" } });
    const visited = screen.getAllByRole("checkbox", { name: "Visited" });
    fireEvent.click(visited[visited.length - 1]!);
    const adds = screen.getAllByRole("button", { name: "Add this influencer" });
    fireEvent.click(adds[adds.length - 1]!);
    fireEvent.click(screen.getByRole("button", { name: "Propose for approval" }));
    await screen.findByText("Version 3 is proposed; it waits for a second person's approval.");
    const sent = calls.find((c) => c.method === "POST" && c.path === "/v1/strength-influencers")?.body as {
      influencers: { id: string }[];
    };
    expect(sent.influencers.map((i) => i.id)).toEqual(["direct", "incident-source", "find-in-a-cell"]);
  });

  it("offers the case's own override to its Author, and saves what is switched off", async () => {
    const calls = serve({ versions: [], defaults: [] }, true);
    panel("author", false);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Direct link" }));
    fireEvent.click(screen.getByRole("button", { name: "Save this case's influencers" }));
    await screen.findByText("This case's influencers are saved.");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ added: [], switched_off: ["direct"], words: "" });
  });

  it("shows an Editor the influencers in force but no override to change", async () => {
    serve({ versions: [], defaults: [] }, false);
    panel("editor", false);
    await screen.findByRole("list", { name: "Influencers in force" });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save this case's influencers" })).toBeNull());
  });
});
