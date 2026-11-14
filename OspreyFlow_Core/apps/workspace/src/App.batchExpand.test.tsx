// @vitest-environment jsdom
//
// The cap's third choice on the real App (ADR-151; spec/00 §4): *Run as a batch job* hands the refused expansion
// up through `onRunExpansionAsBatch`, and the App opens the batch job's panel, which sends the expansion as it was
// asked for and follows the job; *Open the view* shows its result as the read-only lens, never unasked. What would
// fail if it were wrong: no prop passed (the canvas then offers no batch job), the panel not opened, the result
// opened unasked or not shown as the lens, a view already open offering a batch job (an expansion in a view is not
// the case's), or a second choice not given its own panel. The panel held to its case and person is
// `workingset/useBatchExpansion.test.ts`; the canvas's half, by keyboard, is `keyboard/canvas-expand-cap.spec.ts`.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";
import type { GlassCanvasProps } from "./canvas/GlassCanvas";
import type { ReactElement } from "react";
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
/** A case's own answer, asked before the table: a Response, a promise of one, or null for the table's. */
let answerFirst: ((url: string, method: string) => Response | Promise<Response> | null) | null = null;

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
    const special = answerFirst?.(url, init?.method ?? "GET");
    if (special) return Promise.resolve(special);
    const found = answers.find(([pattern]) => pattern.test(url));
    return found ? Promise.resolve(new Response(JSON.stringify(found[1]))) : new Promise<Response>(() => undefined);
  });
});

afterEach(() => {
  answerFirst = null;
  vi.mocked(userManager.renewSilently).mockImplementation(() => new Promise(() => undefined));
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});


const REFUSED: LimitExceeded = { error: "limit_exceeded", cap_kind: "nodes", cap: 5000, would_be: 6210, options: ["save_as_view", "filter", "promote_to_batch"] };
const ASKED = { nodeId: "p1", edgeType: null, depth: 1, refused: REFUSED };
// The panel asks where the job is every 2 s (ADR-151), on real timers: each case waits up to 5 s for the result, in a
// test given 15 s, so a result never opened fails on its own words, not the test's timeout.
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
    const open = await screen.findByRole("button", { name: "Open the view" }, { timeout: 5000 });
    expect(screen.queryByRole("region", { name: "Open view" })).toBeNull();
    fireEvent.click(open);
    const lens = await screen.findByRole("region", { name: "Open view" });
    expect(within(lens).getByText("Kestrel, expanded")).toBeTruthy();
    // Its work done, the panel closes; the lens says what is open.
    await waitFor(() => expect(panel()).toBeNull());
   }, 15_000);

  test("offers no batch job while a view is open: an expansion there is not the case's", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    fireEvent.click(await screen.findByRole("button", { name: "Open the view" }, { timeout: 5000 }));
    await screen.findByRole("region", { name: "Open view" });
    await waitFor(() => expect(canvasProps.current?.lens).toBe(true));
    expect(canvasProps.current?.onRunExpansionAsBatch).toBeUndefined();
   }, 15_000);

  test("a second choice while the first runs opens its own panel, which asks the Conduit again", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    const posts = () => sent.filter((s) => s.url.endsWith("/inv-1/batch-expansions"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    await waitFor(() => expect(posts()).toHaveLength(1));
    act(() => canvasProps.current!.onRunExpansionAsBatch!({ ...ASKED, depth: 2 }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[1]!.body).toEqual({ request: { node_ids: ["p1"], depth: 2, edge_types: null } });
    expect(screen.getAllByRole("region", { name: "Batch job: the whole expansion" })).toHaveLength(1);
  }, 15_000);

  test("a view asked for after Open the view wins, as any later view does (openLens)", async () => {
    let releaseBatchView!: () => void;
    answerFirst = (url) =>
      url.endsWith("/inv-1/views/v-batch")
        ? new Promise<Response>((resolve) => {
            releaseBatchView = () => resolve(new Response(JSON.stringify({ view: BATCH_VIEW, nodes: [kestrel], edges: [], layout: {}, missing: 0 })));
          })
        : null;
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    fireEvent.click(await screen.findByRole("button", { name: "Open the view" }, { timeout: 5000 }));
    await waitFor(() => expect(sent.some((s) => s.url.endsWith("/inv-1/views/v-batch"))).toBe(true));
    const viewsMenu = canvasProps.current!.viewsMenu as ReactElement<{ onOpen: (view: { id: string }) => void }>;
    act(() => viewsMenu.props.onOpen({ id: "v-shared" }));
    const lens = await screen.findByRole("region", { name: "Open view" });
    expect(within(lens).getByText("Payments in March")).toBeTruthy();
    await act(async () => releaseBatchView());
    await new Promise((r) => setTimeout(r, 40));
    expect(within(screen.getByRole("region", { name: "Open view" })).getByText("Payments in March")).toBeTruthy();
  }, 15_000);

  test("a second choice while the first runs opens its own panel, which follows the job the Conduit names", async () => {
    let starts = 0;
    answerFirst = (url, method) =>
      method === "POST" && url.endsWith("/inv-1/batch-expansions") && ++starts > 1
        ? new Response(JSON.stringify({ error: "batch_expansion_running", detail: "A batch expansion of yours is already running in this case, so another was not started. Follow that one, or wait for it to finish.", id: "j1" }), { status: 409 })
        : null;
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    const posts = () => sent.filter((s) => s.url.endsWith("/inv-1/batch-expansions"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    await waitFor(() => expect(posts()).toHaveLength(1));
    act(() => canvasProps.current!.onRunExpansionAsBatch!({ ...ASKED, depth: 2 }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[1]!.body).toEqual({ request: { node_ids: ["p1"], depth: 2, edge_types: null } });
    expect(screen.getAllByRole("region", { name: "Batch job: the whole expansion" })).toHaveLength(1);
    // Followed, so without the second request's figures, and its reading is the running job's.
    await screen.findByText("A batch expansion of yours is already running in this case, so another was not started. Follow that one, or wait for it to finish.");
    expect(screen.queryByText(/The canvas refused/)).toBeNull();
    expect(await screen.findByRole("button", { name: "Open the view" }, { timeout: 5000 })).toBeTruthy();
  }, 15_000);

  test("someone else signing in in place takes the panel away, with its figures", async () => {
    vi.mocked(userManager.renewSilently).mockResolvedValue({
      access_token: "b-token",
      expires_at: Math.floor(Date.now() / 1000) + 300,
      profile: { sub: "analyst-2", username: "osprey-demo-analyst-2", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] },
    } as never); // prettier-ignore
    let refuse = false;
    answerFirst = (url) => (refuse && url.endsWith("/inv-1/batch-expansions/j1") ? ((refuse = false), new Response("{}", { status: 401 })) : null);
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    // Held at queued, so the panel is still following when the sign-in changes.
    const held = answerFirst;
    answerFirst = (url, method) =>
      held(url, method) ??
      (url.endsWith("/inv-1/batch-expansions/j1") ? new Response(JSON.stringify({ id: "j1", state: "queued", words: "Waiting for the batch expansion to start.", view: null, nodes: null, links: null, refusal: null })) : null);
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    expect(await screen.findByText(/The canvas refused 6,210 nodes/)).toBeTruthy();
    fireEvent.pointerDown(window); // the person's own action, so the refused reading is renewed (ADR-050 Amendment 2)
    refuse = true;
    await waitFor(() => expect(vi.mocked(userManager.renewSilently)).toHaveBeenCalled(), { timeout: 5000 });
    await waitFor(() => expect(panel()).toBeNull(), { timeout: 5000 });
    expect(screen.queryByText(/The canvas refused 6,210 nodes/)).toBeNull();
  }, 15_000);

  test("offers no second try of a failed job once a view is open", async () => {
    answerFirst = (url) =>
      url.endsWith("/inv-1/batch-expansions/j1")
        ? new Response(JSON.stringify({ id: "j1", state: "failed", words: "The batch expansion could not finish, and nothing was saved. Try again, or narrow the expansion.", view: null, nodes: null, links: null, refusal: null }))
        : null;
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    expect(await screen.findByRole("button", { name: "Try the batch job again" }, { timeout: 5000 })).toBeTruthy();
    const viewsMenu = canvasProps.current!.viewsMenu as ReactElement<{ onOpen: (view: { id: string }) => void }>;
    act(() => viewsMenu.props.onOpen({ id: "v-shared" }));
    await screen.findByRole("region", { name: "Open view" });
    expect(panel()).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Try the batch job again" })).toBeNull();
  }, 15_000);

  test("the panel is drawn at the canvas's foot alone: not over Reports or the Studio while its job runs, and back on the Graph", async () => {
    answerFirst = (url) =>
      url.endsWith("/inv-1/batch-expansions/j1")
        ? new Response(JSON.stringify({ id: "j1", state: "running", words: "Expanding from 1 node.", view: null, nodes: null, links: null, refusal: null }))
        : null;
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    await screen.findByText("Expanding from 1 node.", undefined, { timeout: 5000 });
    const shown = () => document.querySelector<HTMLElement>(".batch-expansion");
    const views = () => screen.getByRole("group", { name: "View" });
    const places = () => screen.getByRole("navigation", { name: "Places" });
    // Over Reports (the view switch), the panel is not drawn, nor read by assistive technology.
    fireEvent.click(within(views()).getByRole("button", { name: "Reports" }));
    await waitFor(() => expect(panel()).toBeNull());
    expect(shown() === null || shown()!.closest("[hidden]") !== null).toBe(true);
    // Nor over the Ingest Studio (a place of its own).
    fireEvent.click(within(places()).getByRole("button", { name: "Ingest Studio" }));
    await waitFor(() => expect(within(places()).getByRole("button", { name: "Ingest Studio" }).getAttribute("aria-current")).toBe("page"));
    expect(panel()).toBeNull();
    expect(shown() === null || shown()!.closest("[hidden]") !== null).toBe(true);
    // Back on the Graph, the same panel, still following the same job: no second start.
    fireEvent.click(within(places()).getByRole("button", { name: "The Glass" }));
    fireEvent.click(within(await screen.findByRole("group", { name: "View" })).getByRole("button", { name: "Graph" }));
    expect(await screen.findByRole("region", { name: "Batch job: the whole expansion" })).toBeTruthy();
    expect(sent.filter((s) => s.url.endsWith("/inv-1/batch-expansions"))).toHaveLength(1);
    expect(screen.getByText("Expanding from 1 node.")).toBeTruthy();
  }, 15_000);

  test("the panel is hidden over the search results, which draw no view, and back when they close", async () => {
    answerFirst = (url) =>
      url.endsWith("/inv-1/batch-expansions/j1")
        ? new Response(JSON.stringify({ id: "j1", state: "running", words: "Expanding from 1 node.", view: null, nodes: null, links: null, refusal: null }))
        : null;
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    await screen.findByText("Expanding from 1 node.", undefined, { timeout: 5000 });
    const box = screen.getByRole("combobox", { name: "Search entities, identifiers, documents" });
    fireEvent.change(box, { target: { value: "Kestrel" } });
    fireEvent.keyDown(box, { key: "Enter" });
    await screen.findByRole("heading", { name: "Search results for 'Kestrel'" });
    expect(panel()).toBeNull();
    expect(document.querySelector(".batch-expansion")?.closest("[hidden]")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Back to / }));
    expect(await screen.findByRole("region", { name: "Batch job: the whole expansion" })).toBeTruthy();
    expect(sent.filter((s) => s.url.endsWith("/inv-1/batch-expansions"))).toHaveLength(1);
  }, 15_000);

  test("going Home and back on the same page follows the job already started, never starting it again", async () => {
    let reads = 0;
    answerFirst = (url) => {
      if (!url.endsWith("/inv-1/batch-expansions/j1")) return null;
      reads += 1;
      return new Response(JSON.stringify(reads < 2
        ? { id: "j1", state: "running", words: "Expanding from 1 node.", view: null, nodes: null, links: null, refusal: null }
        : { id: "j1", state: "done", words: "Saved 6,210 nodes and 9,004 links as your private view “Kestrel, expanded”.", view: BATCH_VIEW, nodes: 6210, links: 9004, refusal: null }));
    }; // prettier-ignore
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await waitFor(() => expect(canvasProps.current?.onRunExpansionAsBatch).toBeTypeOf("function"));
    act(() => canvasProps.current!.onRunExpansionAsBatch!(ASKED));
    await screen.findByText("Expanding from 1 node.", undefined, { timeout: 5000 });
    // Home is another tree of the App's: the workspace, and the panel with it, are taken away.
    fireEvent.click(screen.getByRole("button", { name: "Osprey, go to Home" }));
    await waitFor(() => expect(document.querySelector(".batch-expansion")).toBeNull());
    await new Promise((r) => setTimeout(r, 2500)); // the job finishes meanwhile, on the server
    // From Home to the Studio and on to the Glass, all on the same page (a case opened from Home's list reloads it,
    // which starts nothing): the workspace, and the panel with it, are drawn again.
    fireEvent.click(await screen.findByRole("button", { name: /^Open Ingest Studio/ }));
    fireEvent.click(within(await screen.findByRole("navigation", { name: "Places" })).getByRole("button", { name: "The Glass" }));
    // Drawn again, it follows the job it started, now done, and offers its view: no second job, no second view.
    expect(await screen.findByRole("button", { name: "Open the view" }, { timeout: 5000 })).toBeTruthy();
    expect(sent.filter((s) => s.url.endsWith("/inv-1/batch-expansions"))).toHaveLength(1);
  }, 20_000);
});
