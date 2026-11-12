// @vitest-environment jsdom
//
// ADR-145 decision 4 and Amendment 2 (variant B, the owner's choice of 7 November 2026): the case
// screen's chrome, counted on the real `App`. A keyboard user passes 24 controls before the canvas
// (25 on the deployed page, whose brand frame adds the skip link first; part 1's harness, drawing
// the mark without its Home button, counted one fewer for every variant), and the right-hand column
// opens with the Inspector only. Red if a control returns before the canvas, or a panel opens by
// default. The canvas, the map and the timeline need WebGL, which jsdom has none of: the canvas is a
// stand-in carrying its real role and name, so the count stops where the real one would.
//
// What this count cannot see: it reads the DOM in document order, not a real Tab walk, so a control
// hidden only by CSS would be counted, and one with a positive `tabindex` (reached out of document
// order) would be counted in the wrong place. Neither is used in the chrome today. A true Tab walk on
// the real `App` needs a browser and the Conduit behind it — the dev stack — which this tier has not.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";

vi.mock("./canvas/GlassCanvas", () => ({
  GlassCanvas: () => <div role="application" aria-label="Network canvas" tabIndex={0} />,
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

const TABBABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function before(canvas: Element): string[] {
  return [...document.querySelectorAll<HTMLElement>(TABBABLE)]
    .filter((el) => el !== canvas && el.compareDocumentPosition(canvas) & Node.DOCUMENT_POSITION_FOLLOWING)
    .filter((el) => !el.closest("[hidden], [aria-hidden='true'], [inert]"))
    .map((el) => (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().replace(/\s+/g, " "));
}

beforeEach(() => {
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
    [/\/inv-1\/datasets$/, [{ id: "ds-1", name: "Prison intel", owning_unit: "unit-1", created_at: "2026-11-01T09:00:00Z", created_by: "a" }]],
  ]; // prettier-ignore
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
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

describe("the case screen's chrome, variant B (ADR-145 Amendment 2)", () => {
  test("24 controls stand before the canvas, in this order", async () => {
    render(<App />);
    const canvas = await screen.findByRole("application", { name: "Network canvas" });
    await screen.findByRole("button", { name: "Open Prison intel in the Ingest Studio ↗" });
    const stops = before(canvas);
    expect(stops).toEqual([
      // ADR-146 decision 2: Rules and Monitoring, with the count that left the banner.
      "Osprey, go to Home", "The Glass", "Ingest Studio", "Rules and Monitoring 3 open", "Admin",
      expect.stringMatching(/Search entities/), "Add many from a list", "Filters",
      "Graph", "Map", "More views▾", "Export ▾", expect.stringMatching(/theme/i), expect.stringMatching(/· OFFICIAL/),
      "Case", "Boards", expect.stringMatching(/^Case: Kestrel/), "Open Prison intel in the Ingest Studio ↗",
      // The rail, then the Graph's own toolbar over the canvas.
      "Cases", "Explore", "More", "Help", "Show names",
      "Match strictness",
    ]); // prettier-ignore
  });

  test("the banner's Boards opens the case's drawing boards and is the current section (ADR-143, L3.3)", async () => {
    render(<App />);
    const sections = await screen.findByRole("navigation", { name: "In the Glass" });
    const boards = await within(sections).findByRole("button", { name: "Boards" });
    expect(boards.getAttribute("aria-disabled")).toBeNull();
    boards.focus();
    fireEvent.click(boards);
    await screen.findByRole("heading", { name: /^Drawing boards in case/ });
    expect(boards.getAttribute("aria-current")).toBe("page");
    expect(within(sections).getByRole("button", { name: "Case" }).getAttribute("aria-current")).toBeNull();
  });

  test("the switcher's Rules and Monitoring carries the open count, open, claimed and proposed for closing but not closed (rule 3: as the reader's queue says), its count in its name", async () => {
    render(<App />);
    const places = await screen.findByRole("navigation", { name: "Places" });
    const rules = await within(places).findByRole("button", { name: "Rules and Monitoring 3 open" });
    expect(rules.querySelector(".place-switcher__count")?.textContent).toBe("3");
    // ADR-146 decision 2: Monitoring left the Glass, its count with it.
    const sections = await screen.findByRole("navigation", { name: "In the Glass" });
    expect(within(sections).queryByRole("button", { name: /Monitoring/ })).toBeNull();
  });

  test("the column opens with the Inspector only, the other panels folded in their order", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    const headers = (name: string) =>
      within(document.body)
        .getAllByRole("button", { name: new RegExp(`^${name}$`) })
        .find((b) => b.closest(".side-panel-header"));
    expect(headers("Inspector")?.getAttribute("aria-expanded")).toBe("true");
    for (const name of ["Metrics", "Query builder"]) expect(headers(name)?.getAttribute("aria-expanded")).toBe("false");
  });
});
