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
  GlassCanvas: () => <div role="application" aria-label="Network canvas" tabIndex={0} />,
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
    expect(screen.getByRole("button", { name: /^More views/ }).className).not.toContain("menu-button--pressed");
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
    const panel = await screen.findByRole("dialog", { name: "Ask & Chat" });
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
    fireEvent.click(within(region).getByRole("button", { name: "Views in this case" }));
    const panel = await screen.findByRole("dialog", { name: "Cases" });
    fireEvent.click(await within(panel).findByRole("button", { name: /^Open/ }));
    await screen.findByRole("region", { name: "Open view" });
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Search results for 'Kestrel'" })).toBeNull());
    expect(pressed()).toEqual(["Graph"]);
  });

  test("the words carried to Ask & Chat are carried once: closed and opened again from the rail, its box is empty", async () => {
    await openResults();
    fireEvent.click(await screen.findByRole("button", { name: "Ask a question about 'Kestrel' instead" }));
    const panel = await screen.findByRole("dialog", { name: "Ask & Chat" });
    fireEvent.click(within(panel).getByRole("button", { name: "Close Ask & Chat" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Ask & Chat" })).toBeNull());
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Ask & Chat" }));
    const again = await screen.findByRole("dialog", { name: "Ask & Chat" });
    expect((within(again).getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
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
