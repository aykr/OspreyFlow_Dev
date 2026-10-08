// @vitest-environment jsdom
// ADR-100: where an analyst new to a case's data starts. The panel shows what the Conduit counts
// and ranks (each figure the analyst's own) and nothing more; a ranking says of how many and pages
// rather than stops (rule 2); every item puts its node on the canvas with one action; a refusal is
// said in words.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { ExplorePanel } from "./ExplorePanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function node(id: string, type: string, name: string): Node {
  return {
    id,
    type,
    properties: { name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  } as unknown as Node;
}

const COUNTS = {
  nodes: { Person: 12, Organisation: 2, Location: 0 },
  edges: { ASSOCIATE_OF: 30 },
  computed_at: "2026-10-08T09:05:00Z",
};

function ranked(prefix: string, type: string, offset: number, count: number, total: number) {
  return {
    nodes: Array.from({ length: count }, (_, i) => ({
      node: node(`${prefix}${offset + i}`, type, `${prefix} ${offset + i}`),
      degree: 100 - offset - i,
    })),
    total,
    offset,
  };
}

function serve(handler: (path: string, query: URLSearchParams) => Response) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const parsed = new URL(url);
      const path = parsed.pathname.replace("/v1/investigations/c1/explore/", "");
      calls.push(`${path}?${parsed.searchParams.toString()}`);
      return handler(path, parsed.searchParams);
    }),
  );
  return calls;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function standard() {
  return serve((path, q) => {
    if (path === "counts") return json(200, COUNTS);
    const type = q.get("entity_type");
    const offset = Number(q.get("offset"));
    const limit = Number(q.get("limit"));
    if (type === "Person") return json(200, ranked("Person", "Person", offset, Math.min(limit, 12 - offset), 12));
    if (type === "Organisation") return json(200, ranked("Org", "Organisation", offset, 2, 2));
    return json(200, ranked("Hub", "Person", offset, Math.min(limit, 14 - offset), 14));
  });
}

function mount(onPick = vi.fn()) {
  render(<ExplorePanel apiBaseUrl="http://api" bearerToken="t" investigationId="c1" edgeTypes={[]} onPick={onPick} />);
  return onPick;
}

describe("ExplorePanel", () => {
  it("says what the case's data holds, by type, most first, and leaves out a type with none", async () => {
    standard();
    mount();
    const holds = await screen.findByRole("region", { name: "What this case holds" });
    expect(within(holds).getByText("14 entities and 30 links")).toBeTruthy();
    const rows = within(holds).getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toEqual(["Person · 12", "Organisation · 2", "Associate of · 30"]);
  });

  it("says when the figures were counted, since they are kept (ADR-100 Amendment 3)", async () => {
    standard();
    mount();
    expect(await screen.findByText("Counted at 09:05 UTC, and again after any change.")).toBeTruthy();
  });

  it("ranks the most connected and says of how many", async () => {
    standard();
    mount();
    const top = await screen.findByRole("region", { name: "Most connected" });
    expect(await within(top).findByText("The 10 most connected of 14.")).toBeTruthy();
    expect(within(top).getAllByRole("button", { name: /links$/ })).toHaveLength(10);
    expect(within(top).getByRole("button", { name: "Hub 0 · Person · 100 links" })).toBeTruthy();
  });

  it("pages the ranking rather than stopping, and says when all are shown", async () => {
    const calls = standard();
    mount();
    const top = await screen.findByRole("region", { name: "Most connected" });
    fireEvent.click(await within(top).findByRole("button", { name: "Show 4 more" }));
    expect(await within(top).findByText("All 14 shown.")).toBeTruthy();
    expect(within(top).getAllByRole("button", { name: /links$/ })).toHaveLength(14);
    expect(within(top).queryByRole("button", { name: /^Show \d+ more$/ })).toBeNull();
    expect(calls).toContain("most-connected?limit=4&offset=10");
  });

  it("puts a node on the canvas with one action", async () => {
    standard();
    const onPick = mount();
    const top = await screen.findByRole("region", { name: "Most connected" });
    fireEvent.click(await within(top).findByRole("button", { name: "Hub 3 · Person · 97 links" }));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0]?.[0].id).toBe("Hub3");
  });

  it("opens a type to its five most connected, then pages it", async () => {
    const calls = standard();
    const onPick = mount();
    const byType = await screen.findByRole("region", { name: "By entity type" });
    const person = await within(byType).findByRole("button", { name: "Person · 12" });
    expect(person.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(person);
    expect(person.getAttribute("aria-expanded")).toBe("true");
    expect(await within(byType).findByText("The 5 most connected of 12.")).toBeTruthy();
    expect(calls).toContain("most-connected?limit=5&offset=0&entity_type=Person");
    fireEvent.click(within(byType).getByRole("button", { name: "Show 7 more" }));
    expect(await within(byType).findByText("All 12 shown.")).toBeTruthy();
    fireEvent.click(within(byType).getByRole("button", { name: "Person 11 · Person · 89 links" }));
    expect(onPick.mock.calls[0]?.[0].id).toBe("Person11");
    // A type with none is not offered.
    expect(within(byType).queryByRole("button", { name: /^Location/ })).toBeNull();
  });

  it("says a refusal in words, and an empty case plainly", async () => {
    serve(() => json(403, {}));
    mount();
    expect(await screen.findByText("What this case holds could not be read (403).")).toBeTruthy();
    cleanup();
    serve((path) => (path === "counts" ? json(200, { nodes: {}, edges: {} }) : json(200, { nodes: [], total: 0, offset: 0 })));
    mount();
    expect(await screen.findByText("This case's data holds nothing you can see yet.")).toBeTruthy();
  });
});
