// @vitest-environment jsdom
//
// The cap's third choice on the real App (ADR-151; spec/00 §4): *Run as a batch job* hands the refused expansion
// up through `onRunExpansionAsBatch`, and the App opens the batch job's panel, which sends the expansion as it was
// asked for, follows the job, and opens its result as the read-only lens. What would fail if it were wrong: no
// prop passed (the canvas then offers no batch job), the panel not opened, the result not shown as the lens, a
// view already open offering a batch job (an expansion in a view is not the case's), or the panel left following
// a job of the case the reader has left. The canvas's own half, by keyboard, is `keyboard/canvas-batch-expand.spec.ts`.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";
import type { GlassCanvasProps } from "./canvas/GlassCanvas";
import type { LimitExceeded } from "./workingset/models";

const canvasProps: { current: Partial<GlassCanvasProps> | null } = { current: null };
vi.mock("./canvas/GlassCanvas", () => ({
  GlassCanvas: (props: Partial<GlassCanvasProps>) => {
    canvasProps.current = props;
    return <div role="application" aria-label="Network canvas" tabIndex={0} />;
  },
}));
vi.mock("./map/MapView", () => ({ MapView: () => null }));
vi.mock("./timeline/Timeline", () => ({ Timeline: () => null }));

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
const BATCH_VIEW = { id: "v-batch", case_id: "inv-1", name: "Kestrel, expanded", created_by: "analyst-1", created_at: "2026-11-14T10:00:00Z", shared: false, chosen: 1 };
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
    [/\/inv-1\/views\/v-batch$/, { view: BATCH_VIEW, nodes: [kestrel], edges: [], layout: {}, missing: 0 }],
    [/\/inv-1\/batch-expansions$/, { id: "j1", state: "queued", words: "Waiting for the batch expansion to start.", view: null, nodes: null, links: null, refusal: null }],
    [/\/inv-1\/batch-expansions\/j1$/, { id: "j1", state: "done", words: "Saved 6,210 nodes and 9,004 links as your private view “Kestrel, expanded”.", view: BATCH_VIEW, nodes: 6210, links: 9004, refusal: null }],
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


const REFUSED: LimitExceeded = { error: "limit_exceeded", cap_kind: "nodes", cap: 5000, would_be: 6210, options: ["save_as_view", "filter", "promote_to_batch"] };
const ASKED = { nodeId: "p1", edgeType: null, depth: 1, refused: REFUSED };
const panel = () => screen.queryByRole("region", { name: "Batch job: the whole expansion" });

describe("an expansion the cap refused, run as a batch job (ADR-151)", () => {
  test("opens the batch job's panel, sends the expansion as asked, and opens its result as the lens", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    expect(await screen.findByRole("region", { name: "Batch job: the whole expansion" })).toBeTruthy();
    expect(screen.getByText(/The canvas refused 6,210 nodes against its limit of 5,000\./)).toBeTruthy();
    await waitFor(() => expect(sent.find((s) => s.url.endsWith("/inv-1/batch-expansions"))).toBeTruthy());
    expect(sent.find((s) => s.url.endsWith("/inv-1/batch-expansions"))!.body).toEqual({ request: { node_ids: ["p1"], depth: 1, edge_types: null } });
    const lens = await screen.findByRole("region", { name: "Open view" }, { timeout: 5000 });
    expect(within(lens).getByText("Kestrel, expanded")).toBeTruthy();
    expect(screen.getByText("Saved 6,210 nodes and 9,004 links as your private view “Kestrel, expanded”. Its result is open as the view “Kestrel, expanded”.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(panel()).toBeNull());
  });

  test("offers no batch job while a view is open: an expansion there is not the case's", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    await screen.findByRole("region", { name: "Open view" }, { timeout: 5000 });
    await waitFor(() => expect(canvasProps.current?.lens).toBe(true));
    expect(canvasProps.current?.onRunExpansionAsBatch).toBeUndefined();
  });
});
