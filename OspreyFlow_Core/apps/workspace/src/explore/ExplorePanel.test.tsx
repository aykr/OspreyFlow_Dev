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

function link(id: string, from: Node, to: Node, occurrences: number) {
  return {
    edge: { id, type: "COMMUNICATED_WITH", source: from.id, target: to.id, occurrences, properties: {} },
    source: from,
    target: to,
  };
}

const ALICE = { ...node("alice", "Endpoint", "alice@enron.com"), properties: { name: "alice@enron.com", endpoint_kind: "email" } } as unknown as Node;
const BOB = node("bob", "Endpoint", "bob@enron.com");

const STARTERS = {
  questions: [
    { id: "chain:A", question: "Person → Endpoint → Endpoint, by “Uses” then “Communicated with”", pattern: { nodes: [], edges: [] } },
    { id: "chain:B", question: "Endpoint → Endpoint → Endpoint, by “Communicated with” then “Communicated with”", pattern: { nodes: [], edges: [] } },
  ],
  total: 7,
};

const WHATS_NEW = {
  loads: [
    { load_id: "load-7", recipe_id: "cdr-carrier-a", recipe_version: 4, nodes: 120, links: 3400, latest: "2026-10-08T14:05:00Z" },
    { load_id: null, recipe_id: null, recipe_version: null, nodes: 21932, links: 233890, latest: "2026-10-07T16:38:00Z" },
  ],
  loads_total: 14,
  confirmed: [{ node: ALICE, confirmed_at: "2026-10-08T10:30:00Z", confirmed_by: "analyst-2" }],
  confirmed_total: 1,
  marked: [{ node: BOB, marked_at: "2026-10-08T11:00:00Z", marked_by: "analyst-3", reason: "a duplicate" }],
  marked_total: 1,
  computed_at: "2026-10-08T14:10:00Z",
};

function standard() {
  return serve((path, q) => {
    if (path === "counts") return json(200, COUNTS);
    if (path === "busiest-links") {
      const offset = Number(q.get("offset"));
      const all = Array.from({ length: 12 }, (_, i) => link(`l${i}`, ALICE, BOB, 50 - i));
      return json(200, { links: all.slice(offset, offset + Number(q.get("limit"))), total: 12, offset });
    }
    if (path === "groups") {
      return json(200, {
        groups: [{ id: "g1", size: 3669, dominant_type: "Endpoint", central: ALICE, central_links: 210 }],
        total_groups: 36,
        not_shown_groups: 35,
        bridges: [{ node: BOB, groups_reached: 5, links: 120 }],
        total_bridges: 812,
      });
    }
    if (path === "whats-new") return json(200, WHATS_NEW);
    if (path === "starter-questions") return json(200, STARTERS);
    if (path === "busiest-days") {
      return json(200, {
        days: [{ start: "2001-05-02T00:00:00Z", end: "2001-05-03T00:00:00Z", count: 1234 }],
        total: 1,
        offset: 0,
      });
    }
    const type = q.get("entity_type");
    const offset = Number(q.get("offset"));
    const limit = Number(q.get("limit"));
    if (type === "Person") return json(200, ranked("Person", "Person", offset, Math.min(limit, 12 - offset), 12));
    if (type === "Organisation") return json(200, ranked("Org", "Organisation", offset, 2, 2));
    return json(200, ranked("Hub", "Person", offset, Math.min(limit, 14 - offset), 14));
  });
}

function mount(onPick = vi.fn(), onPickLink = vi.fn(), onPickDay = vi.fn(), onApplyDelta = vi.fn()) {
  render(
    <ExplorePanel
      onApplyDelta={onApplyDelta}
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="c1"
      edgeTypes={[]}
      onPick={onPick}
      onPickLink={onPickLink}
      onPickDay={onPickDay}
    />,
  );
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

  it("ranks the busiest links by what they stand for, names the pair, and pages", async () => {
    standard();
    const onPickLink = vi.fn();
    mount(vi.fn(), onPickLink);
    const busy = await screen.findByRole("region", { name: "Busiest links" });
    expect(await within(busy).findByText("The 10 busiest of 12.")).toBeTruthy();
    const top = within(busy).getByRole("button", {
      name: "alice@enron.com → bob@enron.com · Communicated with · 50 emails",
    });
    fireEvent.click(top);
    expect(onPickLink.mock.calls[0]?.[0].edge.id).toBe("l0");
    fireEvent.click(within(busy).getByRole("button", { name: "Show 2 more" }));
    expect(await within(busy).findByText("All 12 shown.")).toBeTruthy();
  });

  it("names the busiest days and sets the timeline to one with one action", async () => {
    standard();
    const onPickDay = vi.fn();
    mount(vi.fn(), vi.fn(), onPickDay);
    const days = await screen.findByRole("region", { name: "Busiest days" });
    expect(await within(days).findByText("All 1 shown.")).toBeTruthy();
    fireEvent.click(within(days).getByRole("button", { name: "Wed 2 May 2001 · 1,234 events" }));
    expect(onPickDay).toHaveBeenCalledWith({ start: "2001-05-02T00:00:00Z", end: "2001-05-03T00:00:00Z", count: 1234 });
  });

  it("names the largest groups by their centre and the nodes bridging them, and counts the rest", async () => {
    standard();
    const onPick = mount();
    const groups = await screen.findByRole("region", { name: "Groups and bridges" });
    expect(await within(groups).findByText("The largest 1 of 36 groups; 35 not shown.")).toBeTruthy();
    fireEvent.click(within(groups).getByRole("button", { name: "Group of 3,669 · mostly Endpoint · around alice@enron.com" }));
    expect(onPick.mock.calls[0]?.[0].id).toBe("alice");
    expect(within(groups).getByText("The strongest 1 of 812 bridges.")).toBeTruthy();
    fireEvent.click(within(groups).getByRole("button", { name: "bob@enron.com · reaches 5 other groups · 120 links" }));
    expect(onPick.mock.calls[1]?.[0].id).toBe("bob");
  });

  it("names the latest loads, newest first, and says of how many", async () => {
    standard();
    mount();
    const news = await screen.findByRole("region", { name: "What's new" });
    expect(await within(news).findByText("The latest 2 of 14 loads.")).toBeTruthy();
    const loads = within(news).getByRole("list", { name: "Latest loads" });
    expect(within(loads).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "load-7 · cdr-carrier-a v4 · 120 entities and 3,400 links · latest 8 Oct 2026, 14:05 UTC",
      "Written outside a load · 21,932 entities and 233,890 links · latest 7 Oct 2026, 16:38 UTC",
    ]);
  });

  it("puts a node a colleague confirmed or marked on the canvas with one action", async () => {
    standard();
    const onPick = mount();
    const news = await screen.findByRole("region", { name: "What's new" });
    fireEvent.click(
      await within(news).findByRole("button", {
        name: "alice@enron.com · Endpoint · confirmed by analyst-2 · 8 Oct 2026, 10:30 UTC",
      }),
    );
    expect(onPick.mock.calls[0]?.[0].id).toBe("alice");
    fireEvent.click(
      within(news).getByRole("button", {
        name: "bob@enron.com · Endpoint · marked for suppression by analyst-3 · 8 Oct 2026, 11:00 UTC · “a duplicate”",
      }),
    );
    expect(onPick.mock.calls[1]?.[0].id).toBe("bob");
    expect(within(news).getByText("All 1 confirmed shown.")).toBeTruthy();
    expect(within(news).getByText("All 1 marked shown.")).toBeTruthy();
  });

  it("says plainly when nothing is new", async () => {
    serve((path) => {
      if (path === "counts") return json(200, COUNTS);
      if (path === "whats-new") {
        return json(200, { loads: [], loads_total: 0, confirmed: [], confirmed_total: 0, marked: [], marked_total: 0 });
      }
      return json(200, { nodes: [], links: [], days: [], groups: [], bridges: [], total: 0, offset: 0 });
    });
    mount();
    const news = await screen.findByRole("region", { name: "What's new" });
    expect(await within(news).findByText("No loads you can see.")).toBeTruthy();
    expect(within(news).getByText("Nothing confirmed you can see.")).toBeTruthy();
    expect(within(news).getByText("Nothing marked you can see.")).toBeTruthy();
  });

  it("offers starter questions, says of how many, and runs one onto the canvas with one action", async () => {
    const delta = { op: "add", seq: 3, nodes: [ALICE, BOB], edges: [] };
    const calls = serve((path) => {
      if (path === "counts") return json(200, COUNTS);
      if (path === "starter-questions") return json(200, STARTERS);
      if (path === "starter-questions/chain%3AA/run") return json(200, { delta, added_nodes: 2, added_links: 0 });
      return json(200, { nodes: [], links: [], days: [], groups: [], bridges: [], loads: [], confirmed: [], marked: [], total: 0, offset: 0 });
    });
    const onApplyDelta = vi.fn();
    mount(vi.fn(), vi.fn(), vi.fn(), onApplyDelta);
    const starters = await screen.findByRole("region", { name: "Starter questions" });
    expect(await within(starters).findByText("The first 2 of 7 questions.")).toBeTruthy();
    fireEvent.click(within(starters).getByRole("button", { name: "Person → Endpoint → Endpoint, by “Uses” then “Communicated with”" }));
    expect(await within(starters).findByText("2 nodes and 0 links added.")).toBeTruthy();
    expect(onApplyDelta).toHaveBeenCalledWith(delta);
    expect(calls).toContain("starter-questions/chain%3AA/run?");
  });

  it("says in words when a starter question matches too many, and adds nothing", async () => {
    serve((path) => {
      if (path === "counts") return json(200, COUNTS);
      if (path === "starter-questions") return json(200, STARTERS);
      if (path.endsWith("/run")) return json(409, { error: "too_many_matches", at_least: 1000 });
      return json(200, { nodes: [], links: [], days: [], groups: [], bridges: [], loads: [], confirmed: [], marked: [], total: 0, offset: 0 });
    });
    const onApplyDelta = vi.fn();
    mount(vi.fn(), vi.fn(), vi.fn(), onApplyDelta);
    const starters = await screen.findByRole("region", { name: "Starter questions" });
    fireEvent.click(await within(starters).findByRole("button", { name: /^Endpoint → Endpoint/ }));
    expect(
      await within(starters).findByText(
        "At least 1,000 match, too many to add. Open the Query builder and pin a node to narrow it.",
      ),
    ).toBeTruthy();
    expect(onApplyDelta).not.toHaveBeenCalled();
  });

  it("says a case too large to group in words, never a sample", async () => {
    serve((path) => {
      if (path === "counts") return json(200, COUNTS);
      if (path === "groups") return json(409, { error: "limit_exceeded", cap_kind: "edges", cap: 250000, would_be: 300000 });
      return json(200, { nodes: [], links: [], days: [], total: 0, offset: 0 });
    });
    mount();
    expect(await screen.findByText("Too large to group here: 300,000 links, more than 250,000.")).toBeTruthy();
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
