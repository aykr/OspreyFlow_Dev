// @vitest-environment jsdom
// The search results page (the owner's navigation decision of 13 November 2026, Part A; ADR-145 Amendment 15 Part A),
// built against `packages/schemas/search.py` (SearchPageRequest, SearchPageResponse). What would fail if each part
// were wrong: a request not in the frozen shape; a count the Glass made up rather than the Conduit's (rule 7); a
// result named other than as the canvas names it (nodeLabel); a passage's match not marked; Open offered for a
// non-document; the Ask line sending anything rather than handing the words over; the fallback or uncertain counts
// not said; a refusal hidden; focus not on the heading.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { Node, SearchPageResponse } from "../../../../packages/schemas/generated";
import { nodeLabel } from "../canvas/nodeAttributes";
import { SearchResults } from "./SearchResults";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const node = (id: string, type: string, properties: Record<string, unknown>): Node =>
  ({ id, type, properties, source_system_ids: [], provenance: [], classification: "OFFICIAL", handling: [] }) as unknown as Node;

const PAGE = (over: Partial<SearchPageResponse> = {}): SearchPageResponse =>
  ({
    query: "Kestrel",
    source: "index",
    limited: false,
    limited_reason: null,
    total: 57,
    counts_exact: true,
    groups: [
      { key: "Person", label: "People", count: 12 },
      { key: "Document", label: "Documents", count: 3 },
      { key: "mentions", label: "Mentioned in documents", count: 42 },
    ],
    filters: {
      datasets: [{ id: "ds-1", name: "Fixture Corp", count: 40 }],
      dates: { earliest: "2025-03-02", latest: "2026-10-30" },
    },
    page: 1,
    page_size: 20,
    more: true,
    nodes: [
      node("p1", "Person", { family_name: "Kestrel", given_name: "Ann" }),
      node("p2", "Person", { family_name: "Kestrel", given_name: "Ann" }),
      node("d1", "Document", { title: "Invoice 44" }),
    ],
    results: [
      { node_ids: ["p1", "p2"], type: "Person", match: { band: "name_sounds", why: "Sounds like 'Kestrel'", field: "Family name" }, passage: [], date: null, datasets: ["ds-1"], is_document: false },
      {
        node_ids: ["d1"], type: "Document", match: { band: "mention_phrase", why: "Mentions 'Kestrel'", field: null },
        passage: [{ text: "paid ", match: false }, { text: "Kestrel", match: true }, { text: " for the invoice", match: false }],
        date: "2026-10-30", datasets: ["ds-1"], is_document: true,
      },
    ],
    ...over,
  }) as SearchPageResponse; // prettier-ignore

function serve(...pages: (SearchPageResponse | { status: number; detail: string })[]) {
  const sent: Record<string, unknown>[] = [];
  const urls: string[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    urls.push(url);
    sent.push(JSON.parse(String(init?.body)));
    const next = pages.length > 1 ? pages.shift()! : pages[0]!;
    const refusal = next as { status?: number; detail?: string };
    return typeof refusal.status === "number"
      ? new Response(JSON.stringify({ detail: refusal.detail }), { status: refusal.status })
      : new Response(JSON.stringify(next));
  });
  return { sent, urls };
}

function draw(over: Partial<Parameters<typeof SearchResults>[0]> = {}) {
  const props = {
    apiBaseUrl: "http://conduit.test",
    bearerToken: "t",
    investigationId: "inv-1",
    query: "Kestrel",
    backLabel: "Graph",
    onBack: vi.fn(),
    onShow: vi.fn(),
    onOpenDocument: vi.fn(),
    onAsk: vi.fn(),
    ...over,
  };
  render(<SearchResults {...props} />);
  return props;
}

test("asks the case's search in the frozen shape, page 1 of 20, All and no filters", async () => {
  const { sent, urls } = serve(PAGE());
  draw();
  await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
  expect(urls[0]).toBe("http://conduit.test/v1/investigations/inv-1/search");
  expect(sent[0]).toEqual({ query: "Kestrel", group: null, filters: {}, page: 1, page_size: 20 });
});

test("the heading takes focus and the total is the Conduit's, in records", async () => {
  serve(PAGE());
  draw();
  const heading = await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
  await waitFor(() => expect(document.activeElement).toBe(heading));
  expect(screen.getByText("57 records")).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain("57 records");
});

test("counts that may be incomplete say so", async () => {
  serve(PAGE({ counts_exact: false }));
  draw();
  expect(await screen.findByText("57 records (counts may be incomplete)")).toBeTruthy();
});

test("the groups are All then the Conduit's, each with its count; choosing one asks again for that group", async () => {
  const { sent } = serve(PAGE(), PAGE({ results: [] }));
  draw();
  const groups = within(await screen.findByRole("group", { name: "Group" }));
  // The counts are the Conduit's, never counted from the page (one Person on this page, twelve counted).
  expect(groups.getAllByRole("button").map((b) => b.textContent)).toEqual([
    "All 57", "People 12", "Documents 3", "Mentioned in documents 42",
  ]); // prettier-ignore
  expect(groups.getByRole("button", { name: /^All/ }).getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(groups.getByRole("button", { name: /^People/ }));
  await waitFor(() => expect(sent[1]).toEqual({ query: "Kestrel", group: "Person", filters: {}, page: 1, page_size: 20 }));
  expect(groups.getByRole("button", { name: /^People/ }).getAttribute("aria-pressed")).toBe("true");
});

test("each result is named as the canvas names it, with its type and why it matched", async () => {
  serve(PAGE());
  draw();
  const list = within(await screen.findByRole("list", { name: "Results" }));
  const items = list.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  // nodeLabel's own answer for the first record, whatever the analyst's per-type label choice makes it.
  expect(within(items[0]!).getByRole("heading", { level: 3 }).textContent).toBe(nodeLabel(PAGE().nodes[0]!));
  expect(items[0]!.textContent).toContain("Person");
  expect(items[0]!.textContent).toContain("Sounds like 'Kestrel'");
  expect(within(items[1]!).getByRole("heading", { level: 3 }).textContent).toBe("Invoice 44");
});

test("a document shows its passage with the match marked, and Open; a person has no Open", async () => {
  serve(PAGE());
  const props = draw();
  const items = within(await screen.findByRole("list", { name: "Results" })).getAllByRole("listitem");
  const mark = items[1]!.querySelector("mark");
  expect(mark?.textContent).toBe("Kestrel");
  expect(items[1]!.textContent).toContain("paid Kestrel for the invoice");
  expect(within(items[0]!).queryByRole("button", { name: /^Open/ })).toBeNull();
  fireEvent.click(within(items[1]!).getByRole("button", { name: "Open Invoice 44" }));
  expect(props.onOpenDocument).toHaveBeenCalledWith("d1");
});

test("Show on graph hands over every record the result stands for", async () => {
  serve(PAGE());
  const props = draw();
  const items = within(await screen.findByRole("list", { name: "Results" })).getAllByRole("listitem");
  fireEvent.click(within(items[0]!).getByRole("button", { name: `Show on graph: ${nodeLabel(PAGE().nodes[0]!)}` }));
  expect(props.onShow).toHaveBeenCalledWith([expect.objectContaining({ id: "p1" }), expect.objectContaining({ id: "p2" })]);
});

test("the Ask line hands the words to Ask & Chat and sends nothing itself", async () => {
  const { urls } = serve(PAGE());
  const props = draw();
  await screen.findByRole("list", { name: "Results" });
  fireEvent.click(screen.getByRole("button", { name: "Ask a question about 'Kestrel' instead" }));
  expect(props.onAsk).toHaveBeenCalledWith("Kestrel");
  expect(urls).toHaveLength(1);
});

test("Back to the view the person left calls back", async () => {
  serve(PAGE());
  const props = draw({ backLabel: "Map" });
  fireEvent.click(await screen.findByRole("button", { name: "Back to Map" }));
  expect(props.onBack).toHaveBeenCalled();
});

test("a dataset and a date range filter the search; Clear filters asks again without them", async () => {
  const { sent } = serve(PAGE());
  draw();
  const filters = within(await screen.findByRole("group", { name: "Filters" }));
  fireEvent.click(filters.getByRole("checkbox", { name: "Fixture Corp (40)" }));
  await waitFor(() => expect(sent.at(-1)).toMatchObject({ filters: { datasets: ["ds-1"] }, page: 1 }));
  fireEvent.change(filters.getByLabelText("From"), { target: { value: "2026-01-01" } });
  fireEvent.change(filters.getByLabelText("To"), { target: { value: "2026-02-01" } });
  await waitFor(() =>
    expect(sent.at(-1)).toMatchObject({ filters: { datasets: ["ds-1"], date_from: "2026-01-01", date_to: "2026-02-01" } }),
  );
  expect((filters.getByLabelText("From") as HTMLInputElement).min).toBe("2025-03-02");
  fireEvent.click(filters.getByRole("button", { name: "Clear filters" }));
  await waitFor(() => expect(sent.at(-1)).toMatchObject({ filters: {} }));
});

test("more results are a page away: Next page asks page 2", async () => {
  const { sent } = serve(PAGE(), PAGE({ page: 2, more: false }));
  draw();
  fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
  await waitFor(() => expect(sent[1]).toMatchObject({ page: 2 }));
  expect(await screen.findByRole("button", { name: "Previous page" })).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole("button", { name: "Next page" })).toBeNull());
});

test("no results says so, offers the Ask line, and Clear filters where a filter is on", async () => {
  serve(PAGE(), PAGE({ total: 0, groups: [], results: [], nodes: [], more: false }));
  draw();
  fireEvent.click(within(await screen.findByRole("group", { name: "Filters" })).getByRole("checkbox", { name: "Fixture Corp (40)" }));
  expect(await screen.findByText("No records match 'Kestrel'.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Ask a question about 'Kestrel' instead" })).toBeTruthy();
  expect(screen.getAllByRole("button", { name: "Clear filters" }).length).toBeGreaterThan(0);
});

test("on the fallback one line says the results are limited, in the Conduit's words", async () => {
  serve(PAGE({ source: "fallback", limited: true, limited_reason: "Results are limited: the search index cannot be reached.", counts_exact: false }));
  draw();
  expect(await screen.findByText("Results are limited: the search index cannot be reached.")).toBeTruthy();
});

test("a dataset the fallback cannot count is listed without a count", async () => {
  serve(PAGE({ filters: { datasets: [{ id: "ds-1", name: "Fixture Corp", count: null }], dates: null } }));
  draw();
  const filters = within(await screen.findByRole("group", { name: "Filters" }));
  expect(filters.getByRole("checkbox", { name: "Fixture Corp" })).toBeTruthy();
  expect(filters.queryByLabelText("From")).toBeNull();
});

test("a refusal is said in the Conduit's words", async () => {
  serve({ status: 422, detail: "Narrow the search: only the first 1,000 results can be paged." });
  draw();
  expect((await screen.findByRole("alert")).textContent).toContain("Narrow the search: only the first 1,000 results can be paged.");
});

test("with no Ask & Chat to hand the words to, there is no Ask line", async () => {
  serve(PAGE());
  draw({ onAsk: undefined });
  await screen.findByRole("list", { name: "Results" });
  expect(screen.queryByRole("button", { name: /^Ask a question/ })).toBeNull();
});
