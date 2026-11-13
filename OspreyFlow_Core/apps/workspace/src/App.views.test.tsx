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

vi.mock("./canvas/GlassCanvas", () => ({
  GlassCanvas: ({ viewsMenu }: { viewsMenu?: import("react").ReactNode }) => (
    <>
      <div role="toolbar" aria-label="Canvas tools">{viewsMenu}</div>
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
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});


describe("Views ▾ by the graph (ADR-144 Amendment 3)", () => {
  test("a view chosen from Views opens as the read-only lens, as the drawer opens it, and Back puts the case back", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    const views = within(screen.getByRole("toolbar", { name: "Canvas tools" })).getByRole("button", { name: "Views" });
    fireEvent.click(views);
    fireEvent.click(await screen.findByRole("button", { name: /^Payments in March/ }));
    const lens = await screen.findByRole("region", { name: "Open view" });
    expect(within(lens).getByText("Payments in March")).toBeTruthy();
    expect(asked.filter((url) => url.endsWith("/inv-1/views/v-shared"))).toHaveLength(1);
    fireEvent.click(within(lens).getByRole("button", { name: /Back to the case/ }));
    await vi.waitFor(() => expect(screen.queryByRole("region", { name: "Open view" })).toBeNull());
  });

  // The owner's navigation decision (ADR-145 Amendment 15): the Cases panel is opened at its views list from the case
  // line's *Views in this case* (the rail's Cases left).
  test("the Cases drawer keeps its list of the case's views", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(within(screen.getByRole("region", { name: "You are in the Glass" })).getByRole("button", { name: "Views in this case" }));
    const list = await screen.findByRole("list", { name: "Views in this case" });
    expect(within(list).getByText("Payments in March")).toBeTruthy();
  });
});
