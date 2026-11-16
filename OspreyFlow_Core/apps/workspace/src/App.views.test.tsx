// @vitest-environment jsdom
//
// ADR-144 Amendment 3 (the owner, 13 November 2026): *Views ▾* by the graph, on the real `App`. Choosing a
// view there is the Cases drawer's own `openLens`: the view is opened from the Conduit and shown as the
// read-only lens, *Back to the case* puts the case back, and the drawer keeps its list. The canvas needs
// WebGL, which jsdom has none of, so it is a stand-in that draws what `App` hands it for the toolbar's
// View group (`viewsMenu`), as `GlassCanvas` does.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";
import { forgetToolbarSettings } from "./canvas/toolbarVisibility";

// v0.6.1 glass-rows C: the toolbar's id, `hidden` and *Hide toolbar* at its end, as `GlassCanvas` draws them.
vi.mock("./canvas/GlassCanvas", () => ({
  GlassCanvas: ({ viewsMenu, toolbarEnd, toolbarHidden, toolbarId }: { viewsMenu?: import("react").ReactNode; toolbarEnd?: import("react").ReactNode; toolbarHidden?: boolean; toolbarId?: string }) => (
    <>
      <div role="toolbar" aria-label="Canvas tools" id={toolbarId} hidden={toolbarHidden}>{viewsMenu}{toolbarEnd}</div>
      <div role="application" aria-label="Network canvas" tabIndex={0} />
    </>
  ),
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

/** A person the four places open for, who holds the Glass and the Studio (so the banner carries its
 * cross-link) and every rail destination: the most a case screen draws. */
const RIGHTS = ["investigate", "read_alert_queue", "triage_alerts", "keep_watches", "trace_ownership", "ask_model", "read_reports",
                "run_analysis", "edit_pipelines", "operate_schedules"]; // prettier-ignore

const VIEW = { id: "v-shared", case_id: "inv-1", name: "Payments in March", created_by: "analyst-2", created_at: "2026-11-08T10:00:00Z", shared: true, chosen: 1 };
const PERSON = {
  id: "n1", type: "Account", properties: { name: "GB-MULE-0042" },
  provenance: { state: "asserted", sources: [], first_seen: "2026-10-01T00:00:00Z" },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
  audit: { created_at: "2026-10-01T00:00:00Z", created_by: "seed", revision: 1 },
}; // prettier-ignore
let asked: string[] = [];

beforeEach(() => {
  asked = [];
  vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
    access_token: "a-token",
    profile: { sub: "analyst-1", username: "osprey-demo-analyst", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] },
  } as never); // prettier-ignore
  vi.mocked(ontologySchema.fetchOntologyRegistry).mockResolvedValue(
    new ontologySchema.OntologyRegistry({ entity_types: [], edge_types: [] } as never),
  );
  sessionStorage.setItem("ospreyflow.investigationId", "inv-1");
  // A returning analyst: the first visit's welcome panel (ADR-115 E6) is closed.
  localStorage.setItem("ospreyflow.welcome-closed.analyst-1", "1");
  // The reads the chrome draws from are answered; every other is held, so nothing half-answered can
  // throw while the count is taken.
  const answers: [RegExp, unknown][] = [
    [/\/v1\/me\/rights$/, { rights: RIGHTS }],
    // ADR-148 Amendment 8: the account menu shows the Conduit's resolved principal, never the token's.
    [/\/v1\/me$/, { id: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] }],
    [/\/v1\/ontology$/, { entity_types: [], edge_types: [] }],
    [/\/v1\/handling-scheme$/, { name: "test", classification: ["OFFICIAL"], handling_codes: {} }],
    [/\/v1\/investigations$/, [{ id: "inv-1", name: "Kestrel", level: "author", created_at: "2026-11-01T09:00:00Z", created_by: "a" }]],
    [/\/inv-1\/resolution\/threshold$/, { threshold: 0.8 }],
    // The case's queue as the reader may see it: one open, one claimed, one proposed for closing
    // (ADR-146 decision 6, G9: still open), one closed.
    [/\/inv-1\/alert-queue$/, [{ alert: { status: "open" } }, { alert: { status: "claimed" } }, { alert: { status: "closing" } }, { alert: { status: "closed" } }]],
    [/\/inv-1\/views$/, [VIEW]],
    [/\/inv-1\/views\/v-shared$/, { view: VIEW, nodes: [PERSON], edges: [], layout: {}, missing: 0 }],
    [/\/inv-1\/datasets$/, [{ id: "ds-1", name: "Prison intel", owning_unit: "unit-1", created_at: "2026-11-01T09:00:00Z", created_by: "a" }]],
  ]; // prettier-ignore
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    asked.push(String(input).split("?")[0]!);
    const found = answers.find(([pattern]) => pattern.test(String(input).split("?")[0]!));
    return found ? Promise.resolve(new Response(JSON.stringify(found[1]))) : new Promise<Response>(() => undefined);
  });
});

afterEach(() => {
  cleanup();
  forgetToolbarSettings();
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});


describe("saved views and the way back to the whole case (ADR-145 Amendment 19, Amendment 17, ADR-144 Amendment 6)", () => {
  test("a saved view opened from the case line is said on the case line, focus on its name, with no strip over the canvas; Back to the whole case puts the case back and focus on Saved views", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    // The toolbar's Views menu is withdrawn (ADR-144 Amendment 6): the case line's button is the one way.
    expect(within(screen.getByRole("toolbar", { name: "Canvas tools" })).queryByRole("button", { name: /^Views/ })).toBeNull();
    const caseLine = screen.getByRole("region", { name: "You are in the Glass" });
    // Amendment 19: with none open, the case line ends "Whole case"; no strip says it over the canvas.
    expect(within(caseLine).getByText("Whole case")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "The whole case" })).toBeNull();
    expect(screen.queryByText("You are looking at the whole case.")).toBeNull();
    const savedViews = await within(caseLine).findByRole("button", { name: "Saved views (1)" });
    fireEvent.click(savedViews);
    fireEvent.click(await screen.findByRole("button", { name: "Open Payments in March" }));
    const named = await within(caseLine).findByText(/^Saved view:/);
    expect(named.textContent).toBe("Saved view: Payments in March");
    await vi.waitFor(() => expect(document.activeElement).toBe(named));
    expect(within(caseLine).queryByText("Whole case")).toBeNull();
    // Nothing between the case line and the canvas: no strip, no saved view region.
    expect(screen.queryByRole("region", { name: "Saved view" })).toBeNull();
    // Details holds that nothing in it changes the case.
    fireEvent.click(within(caseLine).getByRole("button", { name: "Details" }));
    expect(screen.getByRole("region", { name: "Saved view details" }).textContent).toContain("Nothing in a saved view changes the case.");
    expect(asked.filter((url) => url.endsWith("/inv-1/views/v-shared"))).toHaveLength(1);
    fireEvent.click(within(caseLine).getByRole("button", { name: "Back to the whole case" }));
    await vi.waitFor(() => expect(within(caseLine).queryByText(/^Saved view:/)).toBeNull());
    expect(within(caseLine).getByText("Whole case")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Saved view details" })).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(within(caseLine).getByRole("button", { name: "Saved views (1)" })));
  });

  // v0.6.1 glass-rows C, the owner's brief: "Back to the whole case is on screen in every state", the toolbar hidden too.
  test("with the toolbar hidden, a saved view opened from the slim line says so there, and Back to the whole case on it puts the case back, the toolbar still hidden", async () => {
    render(<App />);
    const tools = await screen.findByRole("toolbar", { name: "Canvas tools" });
    fireEvent.click(within(tools).getByRole("button", { name: "Hide toolbar" }));
    expect(tools.hidden).toBe(true);
    const caseLine = screen.getByRole("region", { name: "You are in the Glass" });
    expect(within(caseLine).getByRole("button", { name: "Show toolbar" })).toBeTruthy();
    expect(within(caseLine).getByText("Whole case")).toBeTruthy();
    fireEvent.click(await within(caseLine).findByRole("button", { name: "Saved views (1)" }));
    fireEvent.click(await screen.findByRole("button", { name: "Open Payments in March" }));
    const named = await within(caseLine).findByText(/^Saved view:/);
    expect(named.textContent).toBe("Saved view: Payments in March");
    // The saved view's canvas is drawn afresh; its toolbar is hidden as the analyst left it.
    expect(document.getElementById("glass-view-toolbar")?.hidden).toBe(true);
    expect(within(caseLine).getByRole("button", { name: "Show toolbar" })).toBeTruthy();
    const back = within(caseLine).getByRole("button", { name: "Back to the whole case" });
    fireEvent.click(back);
    await vi.waitFor(() => expect(within(caseLine).queryByText(/^Saved view:/)).toBeNull());
    expect(within(caseLine).getByText("Whole case")).toBeTruthy();
    expect(document.getElementById("glass-view-toolbar")?.hidden).toBe(true);
    expect(within(caseLine).getByRole("button", { name: "Show toolbar" })).toBeTruthy();
    await vi.waitFor(() => expect(document.activeElement).toBe(within(caseLine).getByRole("button", { name: "Saved views (1)" })));
  });

  // The owner's navigation decision (ADR-145 Amendment 15): the Cases panel is opened at its views list from the case
  // line's *Views in this case* (the rail's Cases left).
  test("the Cases drawer keeps its list of the case's views", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(within(screen.getByRole("region", { name: "You are in the Glass" })).getByRole("button", { name: /^Saved views/ }));
    const list = await screen.findByRole("list", { name: "Saved views" });
    expect(within(list).getByText("Payments in March")).toBeTruthy();
  });

  // ADR-145 Amendment 17 (the owner's exception, 14 November 2026): from the case line the drawer is *Saved views*,
  // the views list alone; its first row, *The whole case*, does what the case line's way back does (Amendment 19).
  test("the Saved views drawer holds the saved views alone, and The whole case closes the open view", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    const caseLine = () => within(screen.getByRole("region", { name: "You are in the Glass" }));
    fireEvent.click(caseLine().getByRole("button", { name: /^Saved views/ }));
    const drawer = await screen.findByRole("dialog", { name: "Saved views" });
    await within(drawer).findByRole("list", { name: "Saved views" });
    expect(within(drawer).queryByRole("button", { name: "Browse all cases" })).toBeNull();
    fireEvent.click(await within(drawer).findByRole("button", { name: "Open Payments in March" }));
    await caseLine().findByText(/^Saved view:/);
    fireEvent.click(caseLine().getByRole("button", { name: /^Saved views/ }));
    const again = await screen.findByRole("dialog", { name: "Saved views" });
    fireEvent.click(await within(again).findByRole("button", { name: "Open the whole case" }));
    await vi.waitFor(() => expect(caseLine().queryByText(/^Saved view:/)).toBeNull());
    expect(caseLine().getByText("Whole case")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Saved views" })).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(caseLine().getByRole("button", { name: /^Saved views/ })));
  });
});
