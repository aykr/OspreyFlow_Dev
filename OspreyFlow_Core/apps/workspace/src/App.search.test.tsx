// @vitest-environment jsdom
//
// The search results page on the real App (the owner's navigation decision of 13 November 2026, Part A; ADR-145
// Amendment 15 Part A). What would fail if each part were wrong: Enter not opening the results, or opening them over a
// suggestion the person moved to; a view still current while results show; Back not returning to the view left, or
// focus not back in the search box; choosing a view not leaving the results; a rail panel closing them; the Ask line
// sending a question rather than carrying the words into Ask & Chat; Show on graph not seeding every record.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";

vi.mock("./canvas/GlassCanvas", () => ({
  // The canvas's *Ask the model about these…* (ADR-144 decision 4), as App hands it, for the Ask page's own case.
  GlassCanvas: ({ onAskInView }: { onAskInView?: (saved: { id: string; name: string }) => void }) => (
    <>
      <div role="application" aria-label="Network canvas" tabIndex={0} />
      <button type="button" onClick={() => onAskInView?.({ id: "v-asked", name: "Questions on 1 item" })}>Ask the model about these…</button>
    </>
  ),
}));
vi.mock("./map/MapView", () => ({ MapView: () => null }));
vi.mock("./timeline/Timeline", () => ({ Timeline: () => null }));
// Superset's address (`deploymentReportsUrl`), none unless a case sets one (the owner's "Build a report", Amendment 15).
vi.mock("./auth/oidcConfig", async () => {
  const actual = await vi.importActual<typeof import("./auth/oidcConfig")>("./auth/oidcConfig");
  return { ...actual, deploymentReportsUrl: vi.fn(() => null) };
});

let App!: typeof AppComponent;
beforeAll(async () => {
  const g = globalThis as { WebGL2RenderingContext?: unknown; WebGLRenderingContext?: unknown };
  g.WebGL2RenderingContext ??= class {};
  g.WebGLRenderingContext ??= class {};
  ({ App } = await import("./App"));
});

vi.mock("./auth/userManager", async () => {
  const actual = await vi.importActual<typeof import("./auth/userManager")>("./auth/userManager");
  return {
    ...actual,
    isSignInRedirectCallback: vi.fn(() => true),
    completeSignInFromRedirect: vi.fn(),
    clearRedirectCallbackParams: vi.fn(),
    getUserManager: vi.fn(() => ({ signinRedirect: vi.fn() }) as never),
    renewSilently: vi.fn(() => new Promise(() => undefined)),
    signInAgainInPlace: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
  };
});
vi.mock("./ontology/schema", async () => {
  const actual = await vi.importActual<typeof import("./ontology/schema")>("./ontology/schema");
  return { ...actual, fetchOntologyRegistry: vi.fn() };
});
vi.mock("./map/providers", async () => {
  const actual = await vi.importActual<typeof import("./map/providers")>("./map/providers");
  return { ...actual, fetchMapConfig: vi.fn(() => new Promise(() => undefined)) };
});

import * as userManager from "./auth/userManager";
import * as ontologySchema from "./ontology/schema";


const RIGHTS = ["investigate", "read_alert_queue", "triage_alerts", "ask_model", "read_reports", "trace_ownership"];

const kestrel = { id: "p1", type: "Person", properties: { family_name: "Kestrel" }, source_system_ids: [], provenance: { sources: [] }, classification: "OFFICIAL", handling: [] };
const kestrel2 = { ...kestrel, id: "p2" };
const VIEW = { id: "v-shared", case_id: "inv-1", name: "Payments in March", created_by: "analyst-2", created_at: "2026-11-08T10:00:00Z", shared: true, chosen: 1 };
const invoice = { id: "d1", type: "Document", properties: { title: "Invoice 44" }, source_system_ids: [], provenance: { sources: [] }, classification: "OFFICIAL", handling: [] };
const PAGE = {
  query: "Kestrel", source: "index", limited: false, limited_reason: null, total: 1, counts_exact: true,
  groups: [{ key: "Person", label: "People", count: 1 }], filters: { datasets: [], dates: null }, page: 1, page_size: 20, more: false,
  nodes: [kestrel, kestrel2, invoice],
  results: [
    { node_ids: ["p1", "p2"], type: "Person", match: { band: "name_exact", why: "Name is 'Kestrel'", field: "Family name" }, passage: [], date: null, datasets: [], is_document: false },
    { node_ids: ["d1"], type: "Document", match: { band: "mention_phrase", why: "Mentions 'Kestrel'", field: null }, passage: [{ text: "Kestrel", match: true }], date: null, datasets: [], is_document: true },
  ],
}; // prettier-ignore

const sent: { url: string; body: unknown }[] = [];

beforeEach(() => {
  sent.length = 0;
  RIGHTS.splice(0, RIGHTS.length, "investigate", "read_alert_queue", "triage_alerts", "ask_model", "read_reports", "trace_ownership", "edit_pipelines");
  vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
    access_token: "a-token",
    profile: { sub: "analyst-1", username: "osprey-demo-analyst", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] },
  } as never); // prettier-ignore
  vi.mocked(ontologySchema.fetchOntologyRegistry).mockResolvedValue(
    new ontologySchema.OntologyRegistry({ entity_types: [], edge_types: [] } as never),
  );
  sessionStorage.setItem("ospreyflow.investigationId", "inv-1");
  localStorage.setItem("ospreyflow.welcome-closed.analyst-1", "1");
  const answers: [RegExp, unknown][] = [
    [/\/v1\/me\/rights$/, { rights: RIGHTS }],
    [/\/v1\/me$/, { id: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] }],
    [/\/v1\/ontology$/, { entity_types: [], edge_types: [] }],
    [/\/v1\/handling-scheme$/, { name: "test", classification: ["OFFICIAL"], handling_codes: {} }],
    [/\/v1\/investigations$/, [{ id: "inv-1", name: "Kestrel case", level: "author", created_at: "2026-11-01T09:00:00Z", created_by: "a" }]],
    [/\/inv-1\/datasets$/, [{ id: "ds-1", name: "Prison intel", owning_unit: "unit-1", created_at: "2026-11-01T09:00:00Z", created_by: "a" }]],
    [/\/inv-1\/search$/, PAGE],
    [/\/inv-1\/suggest$/, { nodes: [kestrel], more: false }],
    [/\/inv-1\/seed$/, { nodes: [kestrel], edges: [] }],
    [/\/inv-1\/views$/, [VIEW]],
    [/\/inv-1\/views\/v-shared$/, { view: VIEW, nodes: [kestrel], edges: [], layout: {}, missing: 0 }],
    [/\/v1\/documents\/d1$|\/documents\/d1$/, { id: "d1", title: "Invoice 44", text: "Kestrel paid", mentions: [] }],
    // The case's one answered question, for the Ask page's cases: it draws on Invoice 44 and cites one graph fact.
    [/\/inv-1\/questions$/, [ANSWERED]],
    // Show all on graph's read by id (v0.6.0 #5), nothing new to add.
    [/\/inv-1\/working-set\/add-by-ids$/, { outcome: { delta: { seq: 2, op: "add", nodes: [], edges: [] }, links_among: "not_asked" }, not_shown: 0 }],
  ]; // prettier-ignore
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input).split("?")[0]!;
    sent.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const found = answers.find(([pattern]) => pattern.test(url));
    return found ? Promise.resolve(new Response(JSON.stringify(found[1]))) : new Promise<Response>(() => undefined);
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

const ANSWERED = {
  id: "q-1", author: "analyst-1", question: "Who paid?", answer: "Kestrel paid [G-1].",
  citations: [{ document_id: "d1", title: "Invoice 44" }], candidates: [], unplaced: 0, created_at: "2026-11-14T10:00:00Z",
  graph_citations: [{ number: 1, label: "[G-1]", about: "Kestrel, paid, Invoice 44", node_ids: ["n-k"], link_ids: [] }],
}; // prettier-ignore

const box = () => screen.getByRole("combobox", { name: "Search entities, identifiers, documents" });
const group = () => screen.getByRole("group", { name: "View" });
const pressed = () => within(group()).queryAllByRole("button", { pressed: true }).map((b) => b.textContent);

async function openResults(): Promise<HTMLElement> {
  render(<App />);
  await screen.findByRole("application", { name: "Network canvas" });
  fireEvent.change(box(), { target: { value: "Kestrel" } });
  fireEvent.keyDown(box(), { key: "Enter" });
  return screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
}

describe("the search results page (ADR-145 Amendment 15 Part A)", () => {
  test("Enter in the search box opens the results in the main area, the heading focused, no view current", async () => {
    const heading = await openResults();
    await waitFor(() => expect(document.activeElement).toBe(heading));
    // The results start at All with no filter: the search box's own Filters shape its suggestions alone (§2.0c).
    expect(sent.find((s) => s.url.endsWith("/inv-1/search"))?.body).toEqual({ query: "Kestrel", group: null, filters: {}, page: 1, page_size: 20 });
    expect(pressed()).toEqual([]);
    expect(screen.getByRole("button", { name: /^More ways to show the case/ }).className).not.toContain("menu-button--pressed");
    // The view left stays as it was beneath, out of reach while the results show.
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).not.toBeNull();
  });

  test("Back to Graph returns to the graph as it was, and focus to the search box", async () => {
    render(<App />);
    const canvasBefore = await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.change(box(), { target: { value: "Kestrel" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
    fireEvent.click(await screen.findByRole("button", { name: "Back to Graph" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    expect(pressed()).toEqual(["Graph"]);
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
    expect(document.activeElement).toBe(box());
    // Exactly as it was: the same canvas, never drawn again.
    expect(screen.getByRole("application", { name: "Network canvas" })).toBe(canvasBefore);
  });

  test("the back link names the view the person left", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(within(group()).getByRole("button", { name: "Map" }));
    await waitFor(() => expect(pressed()).toEqual(["Map"]));
    fireEvent.change(box(), { target: { value: "Kestrel" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(await screen.findByRole("button", { name: "Back to Map" })).toBeTruthy();
  });

  test("choosing a view leaves the results, that view current", async () => {
    await openResults();
    fireEvent.click(within(group()).getByRole("button", { name: "Map" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    expect(pressed()).toEqual(["Map"]);
  });

  test("a rail panel opens beside the results and leaves them showing", async () => {
    await openResults();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "History" }));
    await screen.findByRole("dialog", { name: "History" });
    expect(screen.getByRole("heading", { name: "Search results for 'Kestrel'" })).toBeTruthy();
  });

  test("the Ask line opens Ask & Chat with the words carried over, and nothing is asked of a model", async () => {
    await openResults();
    fireEvent.click(await screen.findByRole("button", { name: "Ask a question about 'Kestrel' instead" }));
    // Ask & Chat's page replaces the results (v0.6.0 #4).
    const panel = await screen.findByRole("region", { name: "Ask & Chat" });
    expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull();
    const question = within(panel).getByRole("textbox") as HTMLTextAreaElement;
    expect(question.value).toBe("Kestrel");
    expect(document.activeElement).toBe(question);
    // Opening the panel lists the case's conversation (a read); no question is sent until the person presses Ask.
    expect(sent.filter((s) => /\/(questions|ask)/.test(s.url) && s.body !== undefined)).toEqual([]);
  });

  test("Show on graph seeds every record the result stands for and returns to the graph", async () => {
    await openResults();
    fireEvent.click(await screen.findByRole("button", { name: "Show on graph: Kestrel" }));
    await waitFor(() => expect(sent.some((s) => s.url.endsWith("/inv-1/seed"))).toBe(true));
    const seed = sent.find((s) => s.url.endsWith("/inv-1/seed"))!.body as { node_ids?: string[] };
    // Every record the result stands for, both of the merged entity's.
    expect(JSON.stringify(seed)).toContain("p1");
    expect(JSON.stringify(seed)).toContain("p2");
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    expect(pressed()).toEqual(["Graph"]);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("application", { name: "Network canvas" })));
  });

  test("the keys panel shown by itself on a first visit stays with the graph: not over the results, covering their actions", async () => {
    // Found by the live check (14 November 2026): an account that had never closed it searched, and the panel shown by
    // itself lay over the first result's Show on graph.
    localStorage.removeItem("ospreyflow.welcome-closed.analyst-1");
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    expect(await screen.findByRole("dialog", { name: "Welcome back" })).toBeTruthy();
    fireEvent.change(box(), { target: { value: "Kestrel" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
    expect(screen.queryByRole("dialog", { name: "Welcome back" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Back to Graph" }));
    expect(await screen.findByRole("dialog", { name: "Welcome back" })).toBeTruthy();
  });

  test("Help's keys panel opens over the results, in reach", async () => {
    await openResults();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Help" }));
    const keys = await screen.findByRole("dialog", { name: "Welcome back" });
    expect(keys.closest("[inert]")).toBeNull();
    expect(screen.getByRole("heading", { name: "Search results for 'Kestrel'" })).toBeTruthy();
  });

  test("Open reads a document over the view, the results kept beneath and shown again when it closes", async () => {
    await openResults();
    fireEvent.click(await screen.findByRole("button", { name: "Open Invoice 44" }));
    // Hidden, not gone: the group, the filters and the page chosen are still there when the reader closes.
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    const kept = document.querySelector("section.search-results");
    expect(kept?.hasAttribute("hidden")).toBe(true);
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
  });

  test("someone not offered Ask & Chat (no ask_model) has no Ask line", async () => {
    RIGHTS.splice(0, RIGHTS.length, "investigate", "read_alert_queue");
    await openResults();
    await screen.findByRole("list", { name: "Results" });
    expect(screen.queryByRole("button", { name: "Ask a question about 'Kestrel' instead" })).toBeNull();
  });

  test("closing a document read from the results shows them again, focus in them, never on the view beneath", async () => {
    await openResults();
    fireEvent.click(await screen.findByRole("button", { name: "Open Invoice 44" }));
    const reader = await screen.findByRole("dialog", { name: /^Reading/ });
    fireEvent.click(within(reader).getByRole("button", { name: "Close" }));
    const heading = await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(document.activeElement?.closest("[inert]")).toBeNull();
  });

  test("another place leaves the results: back in the Glass they are gone", async () => {
    await openResults();
    const places = screen.getByRole("navigation", { name: "Places" });
    fireEvent.click(within(places).getByRole("button", { name: /^Ingest Studio$/ }));
    await screen.findByRole("region", { name: "You are in the Ingest Studio" });
    fireEvent.click(within(places).getByRole("button", { name: /^The Glass$/ }));
    await screen.findByRole("region", { name: "You are in the Glass" });
    expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull();
    expect(pressed()).toEqual(["Graph"]);
  });

  test("a saved view opened from the Cases panel leaves the results, the graph current under the view", async () => {
    await openResults();
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    fireEvent.click(within(region).getByRole("button", { name: /^Saved views/ }));
    const panel = await screen.findByRole("dialog", { name: "Saved views" }); // ADR-145 Amendment 17
    fireEvent.click(await within(panel).findByRole("button", { name: /^Open/ }));
    await screen.findByText(/^Saved view:/);
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    expect(pressed()).toEqual(["Graph"]);
  });

  test("the words carried to Ask & Chat are carried once: closed and opened again from the rail, its box is empty", async () => {
    await openResults();
    fireEvent.click(await screen.findByRole("button", { name: "Ask a question about 'Kestrel' instead" }));
    const panel = await screen.findByRole("region", { name: "Ask & Chat" });
    fireEvent.click(within(panel).getByRole("button", { name: "Back to Graph" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Ask & Chat" }));
    // Opened again from the rail: the drawer (ADR-145 Amendment 20), its box empty.
    const again = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect((within(again).getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
  });

  // ADR-145 Amendment 18 (v0.6.0 #4): Ask & Chat's page is over the view, and the two pages replace each other.
  // Amendment 20: the rail opens its drawer beside the results; Expand makes it the page, which replaces them.
  test("the rail's Ask & Chat over the results opens its drawer beside them; expanded it replaces them, its heading focused, the view inert beneath; Back returns to the view, not the results", async () => {
    await openResults();
    const rail = screen.getByRole("navigation", { name: "Workspace" });
    fireEvent.click(within(rail).getByRole("button", { name: "Ask & Chat" }));
    const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect(screen.getByRole("heading", { name: "Search results for 'Kestrel'" })).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "Expand Ask & Chat to the full page" }));
    const page = await screen.findByRole("region", { name: "Ask & Chat" });
    expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(within(page).getByRole("heading", { name: "Ask & Chat" })));
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).not.toBeNull();
    // The Back link is the page's first control.
    expect(page.querySelector("button, a, textarea, input, select")).toBe(within(page).getByRole("button", { name: "Back to Graph" }));
    fireEvent.click(within(page).getByRole("button", { name: "Back to Graph" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull();
    expect(pressed()).toEqual(["Graph"]);
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
    expect(document.activeElement).toBe(within(rail).getByRole("button", { name: "Ask & Chat" }));
  });

  test("a search from the Ask & Chat page replaces it with the results", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await expandAsk();
    fireEvent.change(box(), { target: { value: "Kestrel" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
    expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull();
  });

  test("choosing a view leaves the Ask & Chat page, that view current", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await expandAsk();
    fireEvent.click(within(group()).getByRole("button", { name: "Map" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    expect(pressed()).toEqual(["Map"]);
  });

  test("the same words searched again ask again and take focus back to the heading", async () => {
    const heading = await openResults();
    await waitFor(() => expect(document.activeElement).toBe(heading));
    box().focus();
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(sent.filter((s) => s.url.endsWith("/inv-1/search"))).toHaveLength(2));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Search results for 'Kestrel'"));
  });

  test("a suggestion moved to with the arrow keys is still chosen by Enter, as before", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.change(box(), { target: { value: "Kestrel" } });
    await screen.findByRole("option", { name: /Kestrel/ }, { timeout: 2000 });
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(sent.some((s) => s.url.endsWith("/inv-1/seed"))).toBe(true));
    expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull();
    expect(sent.some((s) => s.url.endsWith("/inv-1/search"))).toBe(false);
  });
});

// ADR-145 Amendment 18 decisions 3 and 5 (v0.6.0 #4): what the drawer did, the page does, and every way out of the
// results leaves it too.
describe("the Ask & Chat page (ADR-145 Amendment 18)", () => {
  /** The page: the rail's drawer, expanded (Amendment 20). */
  async function openAsk(): Promise<HTMLElement> {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    return expandAsk();
  }

  test("a document opened from an answer is read over the view, the page hidden, and shown again when it closes, focus on its heading", async () => {
    const page = await openAsk();
    fireEvent.click(await within(page).findByRole("button", { name: "Invoice 44" }));
    const reader = await screen.findByRole("dialog", { name: /^Reading/ });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    expect(document.querySelector("section.ask-page")?.hasAttribute("hidden")).toBe(true);
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
    fireEvent.click(within(reader).getByRole("button", { name: "Close" }));
    const again = await screen.findByRole("region", { name: "Ask & Chat" });
    await waitFor(() => expect(document.activeElement).toBe(within(again).getByRole("heading", { name: "Ask & Chat" })));
  });

  test("a marker in an answer leaves the page for the graph, focus on the canvas", async () => {
    await openAsk();
    fireEvent.click(within(group()).getByRole("button", { name: "Map" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    // Left from the Map, so the Graph being current afterwards is the marker's doing.
    const page = await expandAsk();
    fireEvent.click(await within(page).findByRole("button", { name: "Show on the graph: Kestrel, paid, Invoice 44, [G-1]" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull();
    expect(pressed()).toEqual(["Graph"]);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("application", { name: "Network canvas" })));
  });

  test("Show all on graph under an answer leaves the page for the graph, reads the answer's items by id, focus on the canvas (v0.6.0 #5 on the page)", async () => {
    // Left from the Map, so the Graph being current afterwards is Show all's doing, not where the page was opened.
    await openAsk();
    fireEvent.click(within(group()).getByRole("button", { name: "Map" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    const page = await expandAsk();
    fireEvent.click(await within(page).findByRole("button", { name: "Show all on graph" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    expect(pressed()).toEqual(["Graph"]);
    await waitFor(() => expect(sent.filter((s) => s.url.endsWith("/inv-1/working-set/add-by-ids")).map((s) => s.body)).toEqual([{ node_ids: ["n-k"], link_ids: [] }]));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("application", { name: "Network canvas" })));
  });

  test("Show all on graph closes a saved view open beneath the page first: the items go on the case", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    fireEvent.click(within(region).getByRole("button", { name: /^Saved views/ }));
    const panel = await screen.findByRole("dialog", { name: "Saved views" });
    fireEvent.click(await within(panel).findByRole("button", { name: /^Open/ }));
    await screen.findByText(/^Saved view:/);
    const page = await expandAsk();
    fireEvent.click(await within(page).findByRole("button", { name: "Show all on graph" }));
    await waitFor(() => expect(screen.queryByText(/^Saved view:/)).toBeNull());
    await waitFor(() => expect(sent.some((s) => s.url.endsWith("/inv-1/working-set/add-by-ids"))).toBe(true));
  });

  // The orchestrator, 15 November 2026: a page opened while a document is read over the view shows at once; the reader
  // closes, as the page takes the view's place (the results page the same).
  test("the rail's Ask & Chat while a document read from the results is open shows its drawer at once, the reader closed", async () => {
    await openResults();
    fireEvent.click(await screen.findByRole("button", { name: "Open Invoice 44" }));
    await screen.findByRole("dialog", { name: /^Reading/ });
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Ask & Chat" }));
    // The drawer, beside the results shown again (Amendment 20), which keep the view out of reach.
    const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect(screen.queryByRole("dialog", { name: /^Reading/ })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(within(drawer).getByRole("heading", { name: "Ask & Chat" })));
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).not.toBeNull();
  });

  test("a search while a document read from an answer is open shows the results at once, the reader closed", async () => {
    const page = await openAsk();
    fireEvent.click(await within(page).findByRole("button", { name: "Invoice 44" }));
    await screen.findByRole("dialog", { name: /^Reading/ });
    fireEvent.change(box(), { target: { value: "Kestrel" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    const heading = await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
    expect(screen.queryByRole("dialog", { name: /^Reading/ })).toBeNull();
    expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });

  // The orchestrator, 15 November 2026: focus stays where the analyst put it. Help asked over the page, then a document
  // read from an answer: the reader has focus, not Help's panel drawn again beside the view.
  test("a document read from an answer with Help's panel open keeps focus in the reader", async () => {
    const page = await openAsk();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Help" }));
    await screen.findByRole("dialog", { name: "Welcome back" });
    fireEvent.click(await within(page).findByRole("button", { name: "Invoice 44" }));
    const reader = await screen.findByRole("dialog", { name: /^Reading/ });
    await waitFor(() => expect(reader.contains(document.activeElement)).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(reader.contains(document.activeElement)).toBe(true);
  });

  // Case's re-check of 8153cae (must-fix): the page hidden for a document read from an answer is not shown, so the
  // rail's Ask & Chat says so (not expanded) and one press shows it, the reader closed, focus on its heading.
  test("the rail's Ask & Chat while a document read from an answer is open shows the page in one press, the reader closed", async () => {
    const page = await openAsk();
    fireEvent.click(await within(page).findByRole("button", { name: "Invoice 44" }));
    await screen.findByRole("dialog", { name: /^Reading/ });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    const opener = within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Ask & Chat" });
    expect(opener.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(opener);
    const again = await screen.findByRole("region", { name: "Ask & Chat" });
    expect(screen.queryByRole("dialog", { name: /^Reading/ })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(within(again).getByRole("heading", { name: "Ask & Chat" })));
    expect(opener.getAttribute("aria-expanded")).toBe("true");
  });

  // Case's review of 052e265 (n1): while a document read from an answer is open, the hidden page kept a Help panel in
  // its `beside` and App drew another over the view. One is mounted, never two, and one again when the reader closes.
  test("Help's panel is mounted once while a document read from an answer is open, and once when it closes", async () => {
    const page = await openAsk();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Help" }));
    await screen.findByRole("dialog", { name: "Welcome back" });
    expect(document.querySelectorAll(".workspace-welcome")).toHaveLength(1);
    fireEvent.click(await within(page).findByRole("button", { name: "Invoice 44" }));
    const reader = await screen.findByRole("dialog", { name: /^Reading/ });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    expect(document.querySelectorAll(".workspace-welcome")).toHaveLength(1);
    fireEvent.click(within(reader).getByRole("button", { name: "Close" }));
    const again = await screen.findByRole("region", { name: "Ask & Chat" });
    expect(document.querySelectorAll(".workspace-welcome")).toHaveLength(1);
    expect(within(again).getByRole("dialog", { name: "Welcome back" })).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(within(again).getByRole("heading", { name: "Ask & Chat" })));
  });

  test("Help's panel is mounted once while a document read from the results is open", async () => {
    await openResults();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Help" }));
    await screen.findByRole("dialog", { name: "Welcome back" });
    fireEvent.click(await screen.findByRole("button", { name: "Open Invoice 44" }));
    await screen.findByRole("dialog", { name: /^Reading/ });
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    expect(document.querySelectorAll(".workspace-welcome")).toHaveLength(1);
  });

  test("Help's panel keeps the focus it took through App's later renders (it takes focus once, as it is asked for)", async () => {
    const { rerender } = render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    // Pressed as a person presses it, focus on Help first, so the panel has an opener to give focus back to on closing.
    const help = within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Help" });
    help.focus();
    fireEvent.click(help);
    const keys = await screen.findByRole("dialog", { name: "Welcome back" });
    await waitFor(() => expect(keys.contains(document.activeElement)).toBe(true));
    // Any later render of App (a fetch landing, a count changing), here the same App drawn again.
    rerender(<App />);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(keys.contains(document.activeElement)).toBe(true);
  });

  test("Help's keys panel opens over the page, in reach", async () => {
    await openAsk();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Help" }));
    const keys = await screen.findByRole("dialog", { name: "Welcome back" });
    expect(keys.closest("[inert]")).toBeNull();
    expect(screen.getByRole("region", { name: "Ask & Chat" })).toBeTruthy();
  });

  test("another place leaves the page: back in the Glass it is gone", async () => {
    await openAsk();
    const places = screen.getByRole("navigation", { name: "Places" });
    fireEvent.click(within(places).getByRole("button", { name: /^Ingest Studio$/ }));
    await screen.findByRole("region", { name: "You are in the Ingest Studio" });
    fireEvent.click(within(places).getByRole("button", { name: /^The Glass$/ }));
    await screen.findByRole("region", { name: "You are in the Glass" });
    expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull();
  });

  test("a saved view opened from the case line leaves the page", async () => {
    await openAsk();
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    fireEvent.click(within(region).getByRole("button", { name: /^Saved views/ }));
    const panel = await screen.findByRole("dialog", { name: "Saved views" });
    fireEvent.click(await within(panel).findByRole("button", { name: /^Open/ }));
    await screen.findByText(/^Saved view:/);
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
  });

  test("the case line's cross-link to the Ingest Studio leaves the page: back in the Glass by the cross-link it is gone", async () => {
    await openAsk();
    fireEvent.click(screen.getByRole("button", { name: /Open (this case's data )?in the Ingest Studio/ }));
    await screen.findByRole("region", { name: "You are in the Ingest Studio" });
    // Back by the Studio's own cross-link, not Places (whose Glass leaves the pages itself, and would hide the link's).
    fireEvent.click(screen.getByRole("button", { name: /Back to (the )?(case .* in the )?Glass/ }));
    await screen.findByRole("region", { name: "You are in the Glass" });
    expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull();
  });

  test("Escape on the page does nothing: it is a page, not a dialog, and only Back or the rail leave it", async () => {
    const page = await openAsk();
    const heading = within(page).getByRole("heading", { name: "Ask & Chat" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    fireEvent.keyDown(heading, { key: "Escape" });
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.getByRole("region", { name: "Ask & Chat" })).toBe(page);
    expect(document.activeElement).toBe(heading);
  });

  // Amendment 20 decision 4: each opening is the drawer; only the results' Ask line opens the page.
  test("a case opened to ask the model (the hand-off's view=questions, ADR-098 decision 4) opens on the drawer", async () => {
    sessionStorage.setItem("ospreyflow.launcherHandoff", JSON.stringify({ view: "questions", at: Date.now() }));
    render(<App />);
    const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect(within(drawer).getByRole("button", { name: "Expand Ask & Chat to the full page" })).toBeTruthy();
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
  });

  test("the canvas's Ask the model about these… opens the drawer beside the graph, asking in the saved view", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(screen.getByRole("button", { name: "Ask the model about these…" }));
    const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect(within(drawer).getByText(/Questions on 1 item/)).toBeTruthy();
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
  });
});

/** The rail's Ask & Chat, then the drawer's Expand: Amendment 18's page (ADR-145 Amendment 20). */
async function expandAsk(): Promise<HTMLElement> {
  fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Ask & Chat" }));
  const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
  fireEvent.click(within(drawer).getByRole("button", { name: "Expand Ask & Chat to the full page" }));
  return screen.findByRole("region", { name: "Ask & Chat" });
}

// ADR-145 Amendment 20 (v0.6.1, the owner, 16 November 2026): the rail opens Ask & Chat as a drawer beside the view;
// Expand makes it Amendment 18's page, Show as a drawer returns, and the panel inside is the same one throughout.
describe("Ask & Chat's drawer (ADR-145 Amendment 20)", () => {
  async function openDrawer(): Promise<HTMLElement> {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(railAsk());
    return screen.findByRole("dialog", { name: "Ask & Chat" });
  }
  const railAsk = () => within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Ask & Chat" });

  test("the rail opens the drawer beside the view: its heading focused, the view in reach, the opener a dialog's, expanded", async () => {
    const drawer = await openDrawer();
    await waitFor(() => expect(document.activeElement).toBe(within(drawer).getByRole("heading", { name: "Ask & Chat" })));
    expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull();
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
    expect(railAsk().getAttribute("aria-haspopup")).toBe("dialog");
    expect(railAsk().getAttribute("aria-expanded")).toBe("true");
    expect(drawer.classList.contains("drawer")).toBe(true);
  });

  test("Escape inside the drawer closes it, focus on the rail's opener", async () => {
    const drawer = await openDrawer();
    await waitFor(() => expect(document.activeElement).toBe(within(drawer).getByRole("heading", { name: "Ask & Chat" })));
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull());
    expect(document.activeElement).toBe(railAsk());
    expect(railAsk().getAttribute("aria-expanded")).toBe("false");
  });

  // The orchestrator's ruling, 16 November 2026: Escape anywhere closes a drawer, as Explore's and History's do; focus
  // stays where the analyst has it (the canvas), as a drawer leaves it.
  test("Escape from the canvas closes the drawer, focus left on the canvas", async () => {
    await openDrawer();
    const canvas = screen.getByRole("application", { name: "Network canvas" });
    canvas.focus();
    fireEvent.keyDown(canvas, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull());
    expect(document.activeElement).toBe(canvas);
  });

  test("while it is the page, the rail's opener announces no dialog and stays expanded; as the drawer it announces one", async () => {
    const drawer = await openDrawer();
    expect(railAsk().getAttribute("aria-haspopup")).toBe("dialog");
    fireEvent.click(within(drawer).getByRole("button", { name: "Expand Ask & Chat to the full page" }));
    await screen.findByRole("region", { name: "Ask & Chat" });
    expect(railAsk().getAttribute("aria-haspopup")).toBeNull();
    expect(railAsk().getAttribute("aria-expanded")).toBe("true");
  });

  // The orchestrator's ruling R1: a marker or Show all on graph keeps the drawer beside the graph (ADR-129 decision 1).
  test("a marker in an answer in the drawer shows it on the graph, the drawer kept, focus on the canvas", async () => {
    const drawer = await openDrawer();
    fireEvent.click(within(group()).getByRole("button", { name: "Map" }));
    fireEvent.click(await within(drawer).findByRole("button", { name: "Show on the graph: Kestrel, paid, Invoice 44, [G-1]" }));
    await waitFor(() => expect(pressed()).toEqual(["Graph"]));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("application", { name: "Network canvas" })));
    expect(screen.getByRole("dialog", { name: "Ask & Chat" })).toBe(drawer);
  });

  test("Show all on graph in the drawer reads the answer's items, the drawer kept, focus on the canvas", async () => {
    const drawer = await openDrawer();
    fireEvent.click(await within(drawer).findByRole("button", { name: "Show all on graph" }));
    await waitFor(() => expect(sent.some((s) => s.url.endsWith("/inv-1/working-set/add-by-ids"))).toBe(true));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("application", { name: "Network canvas" })));
    expect(screen.getByRole("dialog", { name: "Ask & Chat" })).toBe(drawer);
  });

  // The orchestrator's ruling R2: closing returns focus to what opened it where it is still there, else the rail.
  test("opened by the canvas's Ask the model about these…, closing returns focus to that button", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    const asker = screen.getByRole("button", { name: "Ask the model about these…" });
    asker.focus();
    fireEvent.click(asker);
    const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
    fireEvent.click(within(drawer).getByRole("button", { name: "Close Ask & Chat" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Ask the model about these…" })));
  });

  test("Expand over the results leaves them for the page, focus on its heading", async () => {
    await openResults();
    fireEvent.click(railAsk());
    const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect(screen.getByRole("heading", { name: "Search results for 'Kestrel'" })).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "Expand Ask & Chat to the full page" }));
    const page = await screen.findByRole("region", { name: "Ask & Chat" });
    expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(within(page).getByRole("heading", { name: "Ask & Chat" })));
  });

  test("the results' Ask line used with the drawer open beside them opens the page, the words in its box, the box focused", async () => {
    await openResults();
    fireEvent.click(railAsk());
    await screen.findByRole("dialog", { name: "Ask & Chat" });
    fireEvent.click(await screen.findByRole("button", { name: "Ask a question about 'Kestrel' instead" }));
    const page = await screen.findByRole("region", { name: "Ask & Chat" });
    const box = within(page).getByRole("textbox") as HTMLTextAreaElement;
    await waitFor(() => expect(box.value).toBe("Kestrel"));
    await waitFor(() => expect(document.activeElement).toBe(box));
    expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull();
  });

  test("the results' Show on graph keeps the drawer beside the graph", async () => {
    await openResults();
    fireEvent.click(railAsk());
    const drawer = await screen.findByRole("dialog", { name: "Ask & Chat" });
    fireEvent.click(await screen.findByRole("button", { name: "Show on graph: Kestrel" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    expect(screen.getByRole("dialog", { name: "Ask & Chat" })).toBe(drawer);
  });

  test("a saved view opened from the case line keeps the drawer", async () => {
    const drawer = await openDrawer();
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    fireEvent.click(within(region).getByRole("button", { name: /^Saved views/ }));
    const panel = await screen.findByRole("dialog", { name: "Saved views" });
    fireEvent.click(await within(panel).findByRole("button", { name: /^Open/ }));
    await screen.findByText(/^Saved view:/);
    expect(screen.getByRole("dialog", { name: "Ask & Chat" })).toBe(drawer);
  });

  test("the case line's cross-link to the Ingest Studio closes the drawer: back in the Glass it is gone", async () => {
    await openDrawer();
    fireEvent.click(screen.getByRole("button", { name: /Open (this case's data )?in the Ingest Studio/ }));
    await screen.findByRole("region", { name: "You are in the Ingest Studio" });
    fireEvent.click(screen.getByRole("button", { name: /Back to (the )?(case .* in the )?Glass/ }));
    await screen.findByRole("region", { name: "You are in the Glass" });
    expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull();
  });

  test("a document opened from the results with the drawer open gives focus back to their heading, not the drawer", async () => {
    await openResults();
    fireEvent.click(railAsk());
    await screen.findByRole("dialog", { name: "Ask & Chat" });
    fireEvent.click(await screen.findByRole("button", { name: "Open Invoice 44" }));
    const reader = await screen.findByRole("dialog", { name: /^Reading/ });
    fireEvent.click(within(reader).getByRole("button", { name: "Close" }));
    await screen.findByRole("dialog", { name: "Ask & Chat" });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Search results for 'Kestrel'" })));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Search results for 'Kestrel'" }));
  });

  test("Expand keeps the question typed in the same panel, never mounted again; Show as a drawer returns, focus on Expand", async () => {
    const drawer = await openDrawer();
    const question = within(drawer).getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(question, { target: { value: "Who paid Kestrel?" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Expand Ask & Chat to the full page" }));
    const page = await screen.findByRole("region", { name: "Ask & Chat" });
    expect(within(page).getByRole("textbox")).toBe(question);
    expect(question.value).toBe("Who paid Kestrel?");
    await waitFor(() => expect(document.activeElement).toBe(within(page).getByRole("heading", { name: "Ask & Chat" })));
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).not.toBeNull();
    expect(railAsk().getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(within(page).getByRole("button", { name: "Show as a drawer" }));
    const again = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect(within(again).getByRole("textbox")).toBe(question);
    expect(question.value).toBe("Who paid Kestrel?");
    await waitFor(() => expect(document.activeElement).toBe(within(again).getByRole("button", { name: "Expand Ask & Chat to the full page" })));
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).toBeNull();
  });

  test("the shape is not remembered: closed from the page, the next opening is the drawer", async () => {
    await openDrawer();
    fireEvent.click(screen.getByRole("button", { name: "Expand Ask & Chat to the full page" }));
    const page = await screen.findByRole("region", { name: "Ask & Chat" });
    fireEvent.click(within(page).getByRole("button", { name: "Back to Graph" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ask & Chat" })).toBeNull());
    expect(document.activeElement).toBe(railAsk());
    fireEvent.click(railAsk());
    expect(await screen.findByRole("dialog", { name: "Ask & Chat" })).toBeTruthy();
  });

  test("a view chosen keeps the drawer beside the new view, as Explore and History are kept", async () => {
    const drawer = await openDrawer();
    fireEvent.click(within(group()).getByRole("button", { name: "Map" }));
    await waitFor(() => expect(pressed()).toEqual(["Map"]));
    expect(screen.getByRole("dialog", { name: "Ask & Chat" })).toBe(drawer);
  });

  test("a search keeps the drawer beside the results", async () => {
    const drawer = await openDrawer();
    fireEvent.change(box(), { target: { value: "Kestrel" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
    expect(screen.getByRole("dialog", { name: "Ask & Chat" })).toBe(drawer);
  });

  test("another place closes the drawer: back in the Glass it is gone", async () => {
    await openDrawer();
    const places = screen.getByRole("navigation", { name: "Places" });
    fireEvent.click(within(places).getByRole("button", { name: /^Ingest Studio$/ }));
    await screen.findByRole("region", { name: "You are in the Ingest Studio" });
    fireEvent.click(within(places).getByRole("button", { name: /^The Glass$/ }));
    await screen.findByRole("region", { name: "You are in the Glass" });
    expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull();
  });

  test("a document opened from an answer in the drawer hides it, and closing the reader shows it again, focus on its heading", async () => {
    const drawer = await openDrawer();
    fireEvent.click(await within(drawer).findByRole("button", { name: "Invoice 44" }));
    const reader = await screen.findByRole("dialog", { name: /^Reading/ });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull());
    fireEvent.click(within(reader).getByRole("button", { name: "Close" }));
    const again = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect(again).toBe(drawer);
    await waitFor(() => expect(document.activeElement).toBe(within(again).getByRole("heading", { name: "Ask & Chat" })));
  });

  test("Help's keys panel with the drawer open is drawn once, over the view, not inside the drawer", async () => {
    const drawer = await openDrawer();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Help" }));
    const keys = await screen.findByRole("dialog", { name: "Welcome back" });
    expect(document.querySelectorAll(".workspace-welcome")).toHaveLength(1);
    expect(drawer.contains(keys)).toBe(false);
  });
});

