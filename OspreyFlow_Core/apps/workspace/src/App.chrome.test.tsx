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

import * as oidcConfig from "./auth/oidcConfig";
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
  test("25 controls stand before the canvas, in this order (the owner's navigation, ADR-145 Amendment 15)", async () => {
    render(<App />);
    const canvas = await screen.findByRole("application", { name: "Network canvas" });
    await screen.findByRole("button", { name: "Open this case's data in the Ingest Studio ↗" });
    const stops = before(canvas);
    expect(stops).toEqual([
      // ADR-146 decision 2: Rules and Monitoring, with the count that left the banner.
      "Osprey, go to Home", "The Glass", "Ingest Studio", "Rules and Monitoring 3 open", "Admin",
      expect.stringMatching(/Search entities/), "Add many from a list", "Filters",
      // Amendment 15: one view switch, Graph · Map · Drawing board · Reports, then More views.
      "Graph", "Map", "Drawing board", "Reports", "More views▾", "Export ▾", expect.stringMatching(/theme/i), expect.stringMatching(/· OFFICIAL/),
      // The case line: Case ‹switcher› · Views in this case · reads …, then the cross-link.
      expect.stringMatching(/^Case: Kestrel/), "Views in this case", "Open this case's data in the Ingest Studio ↗",
      // The rail: the panel openers alone, then Help and the names toggle; then the Graph's own toolbar.
      "Explore", "Ask & Chat", "History", "Help", "Show names",
      "Match strictness",
    ]); // prettier-ignore
  });

  test("the switcher's Rules and Monitoring carries the open count, open, claimed and proposed for closing but not closed (rule 3: as the reader's queue says), its count in its name", async () => {
    render(<App />);
    const places = await screen.findByRole("navigation", { name: "Places" });
    const rules = await within(places).findByRole("button", { name: "Rules and Monitoring 3 open" });
    expect(rules.querySelector(".place-switcher__count")?.textContent).toBe("3");
    // ADR-146 decision 2: Monitoring left the Glass, its count with it; the Glass's row has no sections at all now
    // (ADR-145 Amendment 15).
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    expect(within(region).queryByRole("button", { name: /Monitoring/ })).toBeNull();
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

// ADR-145 Amendment 14 (the owner's screen fixes of 13 November 2026, v0.5.2 step 3e): one place, one
// marker, and the dataset named once in the context row.
describe("the dataset named once (ADR-145 Amendment 14 decision 4)", () => {

  test("the context row names the case's one dataset once: no scope badge beside the case, a cross-link without it", async () => {
    const held = vi.mocked(globalThis.fetch).getMockImplementation()!;
    vi.mocked(globalThis.fetch).mockImplementation((input, init) =>
      /\/v1\/investigations$/.test(String(input).split("?")[0]!)
        ? Promise.resolve(new Response(JSON.stringify([{ id: "inv-1", name: "Kestrel", level: "author", created_at: "2026-11-01T09:00:00Z", created_by: "a", datasets: ["Prison intel"] }])))
        : held(input, init),
    ); // prettier-ignore
    render(<App />);
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    await within(region).findByText("reads Prison intel");
    await within(region).findByRole("button", { name: "Open this case's data in the Ingest Studio ↗" });
    // The switcher has read the listing (its name is the case's), so a badge would be drawn by now.
    await within(region).findByRole("button", { name: /^Case: Kestrel/ });
    expect((region.textContent ?? "").match(/prison intel/gi)).toHaveLength(1);
  });

  // ADR-115 Amendment 1 point 5's two cases kept: a case reading no dataset is still marked (in the banner's
  // words, "reads no dataset"), and the badge still names the scope when the case's datasets cannot be read.
  for (const [what, listed, datasets] of [
    ["a case that reads no dataset says so once, in the banner (reads no dataset), not as NO DATA beside it", [] as string[], "empty"],
    ["the badge names the scope when the case's datasets cannot be read", ["Prison intel"], "refused"],
  ] as const) {
    test(what, async () => {
      const held = vi.mocked(globalThis.fetch).getMockImplementation()!;
      vi.mocked(globalThis.fetch).mockImplementation((input, init) => {
        const path = String(input).split("?")[0]!;
        if (/\/v1\/investigations$/.test(path))
          return Promise.resolve(new Response(JSON.stringify([{ id: "inv-1", name: "Kestrel", level: "author", created_at: "2026-11-01T09:00:00Z", created_by: "a", datasets: listed }])));
        if (/\/inv-1\/datasets$/.test(path))
          return Promise.resolve(datasets === "empty" ? new Response("[]") : new Response("{}", { status: 403 }));
        return held(input, init);
      }); // prettier-ignore
      render(<App />);
      const region = await screen.findByRole("region", { name: "You are in the Glass" });
      await within(region).findByRole("button", { name: /^Case: Kestrel/ });
      if (datasets === "empty") {
        expect(await within(region).findByText("reads no dataset")).toBeTruthy();
        expect(within(region).queryByText("NO DATA")).toBeNull();
      } else {
        expect(await within(region).findByText("PRISON INTEL")).toBeTruthy();
        expect(within(region).queryByText(/^reads /)).toBeNull();
      }
    });
  }
});

describe("the scope badge where the banner names no dataset (ADR-145 Amendment 14 decision 4)", () => {

  for (const [place, region] of [[/^Rules and Monitoring/, "You are in Rules and Monitoring"], [/^Ingest Studio$/, "You are in the Ingest Studio"]] as const) {
    test(`the scope badge stays where the banner names no dataset: ${region}`, async () => {
      const held = vi.mocked(globalThis.fetch).getMockImplementation()!;
      vi.mocked(globalThis.fetch).mockImplementation((input, init) =>
        /\/v1\/investigations$/.test(String(input).split("?")[0]!)
          ? Promise.resolve(new Response(JSON.stringify([{ id: "inv-1", name: "Kestrel", level: "author", created_at: "2026-11-01T09:00:00Z", created_by: "a", datasets: ["Prison intel"] }])))
          : held(input, init),
      ); // prettier-ignore
      render(<App />);
      await screen.findByRole("application", { name: "Network canvas" });
      fireEvent.click(await within(screen.getByRole("navigation", { name: "Places" })).findByRole("button", { name: place }));
      const there = await screen.findByRole("region", { name: region });
      expect(await within(there).findByText("PRISON INTEL")).toBeTruthy();
    });
  }
});

// The owner's navigation decision of 13 November 2026 (process/lanes/NAVIGATION_2026-11-13.md, Part B; ADR-145
// Amendment 15): one view switch in the top bar, a strip without modes, a rail of panel openers alone, and the
// case line with its views and all cases.
describe("the owner's navigation (ADR-145 Amendment 15)", () => {
  const rail = () => screen.getByRole("navigation", { name: "Workspace" });
  const viewGroup = () => screen.getByRole("group", { name: "View" });
  const pressedViews = () => within(viewGroup()).queryAllByRole("button", { pressed: true }).map((b) => b.textContent);
  const ready = async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
  };

  test("the top bar's one view switch is Graph · Map · Drawing board · Reports · More views, exactly one current", async () => {
    await ready();
    expect(within(viewGroup()).getAllByRole("button").map((b) => b.textContent)).toEqual(["Graph", "Map", "Drawing board", "Reports"]);
    expect(pressedViews()).toEqual(["Graph"]);
    fireEvent.click(within(viewGroup()).getByRole("button", { name: "Reports" }));
    await vi.waitFor(() => expect(pressedViews()).toEqual(["Reports"]));
    fireEvent.click(screen.getByRole("button", { name: /^More views/ }));
    const more = within(await screen.findByRole("group", { name: "More views" }).catch(() => screen.getByRole("dialog", { name: "More views" })));
    expect(more.getAllByRole("button").map((b) => b.textContent)).toEqual(["Matrix", "Figures", "Ownership", "Connection strength"]);
    fireEvent.click(more.getByRole("button", { name: "Ownership" }));
    await vi.waitFor(() => expect(pressedViews()).toEqual([]));
    expect(screen.getByRole("button", { name: /^Ownership/ }).className).toContain("menu-button--pressed");
  });

  test("Drawing board is a view: its own screen says it is a sketch that does not change the case's data", async () => {
    await ready();
    fireEvent.click(within(viewGroup()).getByRole("button", { name: "Drawing board" }));
    await screen.findByRole("heading", { name: /^Drawing boards in case/ });
    expect(pressedViews()).toEqual(["Drawing board"]);
    expect(screen.getByText(/your sketch; it does not change the case's data/)).toBeTruthy();
  });

  test("the strip names no mode and says no mode's note", async () => {
    await ready();
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    expect(within(region).queryByRole("navigation")).toBeNull();
    expect(within(region).queryByText(/Graph: the case's data/)).toBeNull();
    expect(region.getAttribute("aria-describedby")).toBeNull();
  });

  test("the rail holds the panel openers alone: Explore, Ask & Chat, History, then Help and the names toggle", async () => {
    await ready();
    expect(within(rail()).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["Explore", "Ask & Chat", "History", "Help", "Show names"]);
    for (const name of ["Explore", "Ask & Chat", "History"]) {
      const opener = within(rail()).getByRole("button", { name });
      expect(opener.getAttribute("aria-pressed")).toBeNull();
      expect(opener.getAttribute("aria-expanded")).toBe("false");
    }
  });

  for (const [name, title] of [["Explore", "Explore"], ["Ask & Chat", "Ask & Chat"], ["History", "History"]] as const) {
    test(`${name} opens its panel without changing the view, a second press closes it, and closing returns focus to it`, async () => {
      await ready();
      fireEvent.click(within(viewGroup()).getByRole("button", { name: "Map" }));
      await vi.waitFor(() => expect(pressedViews()).toEqual(["Map"]));
      const opener = within(rail()).getByRole("button", { name });
      opener.focus();
      fireEvent.click(opener);
      await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("true"));
      expect(screen.getAllByRole("dialog", { name: new RegExp(title) }).length).toBeGreaterThan(0);
      expect(pressedViews()).toEqual(["Map"]);
      fireEvent.click(opener);
      await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("false"));
      expect(document.activeElement).toBe(opener);
      fireEvent.click(opener);
      await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("true"));
      fireEvent.click(screen.getAllByRole("button", { name: new RegExp(`^Close ${title}`) })[0]!);
      await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("false"));
      expect(document.activeElement).toBe(opener);
      expect(pressedViews()).toEqual(["Map"]);
    });
  }

  test("the case line: You are in the Glass · Case ‹switcher› · Views in this case · reads …", async () => {
    await ready();
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    await within(region).findByText("reads Prison intel");
    const parts = [...region.querySelectorAll(":scope > *, .govuk-notification-banner__content > *")]
      .filter((el) => !el.classList.contains("context-banner__sep") && !el.classList.contains("govuk-notification-banner__content"))
      .map((el) => (el.textContent ?? "").trim().replace(/\s+/g, " "));
    expect(parts.slice(0, 5)).toEqual(["You are in the Glass", "Case", expect.stringMatching(/^Case: Kestrel/), "Views in this case", "reads Prison intel"]);
  });

  test("Views in this case opens the Cases panel at its views list", async () => {
    await ready();
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    fireEvent.click(within(region).getByRole("button", { name: "Views in this case" }));
    const panel = await screen.findByRole("dialog", { name: "Cases" });
    const views = await within(panel).findByRole("region", { name: "Views in this case" });
    await vi.waitFor(() => expect(document.activeElement).toBe(views));
  });

  test("the case switcher's last entry is All cases, which opens the Cases panel", async () => {
    await ready();
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    fireEvent.click(await within(region).findByRole("button", { name: /^Case: Kestrel/ }));
    const menu = await screen.findByRole("dialog", { name: "Case menu" }).catch(() => screen.getByRole("group", { name: "Case menu" }));
    const entries = within(menu).getAllByRole("button");
    expect(entries.at(-1)?.textContent).toBe("All cases");
    fireEvent.click(entries.at(-1)!);
    expect(await screen.findByRole("dialog", { name: "Cases" })).toBeTruthy();
  });
});

// The owner's ruling of 13 November 2026 (Q2; ADR-145 Amendment 15): "Build a report" beside Reports, opening Superset
// in a new tab, for a holder of manage_dashboards on a deployment with Superset, and for no one else.
describe("Build a report beside Reports (ADR-145 Amendment 15)", () => {
  const SUPERSET = "https://bi.example.test";
  const withRights = (rights: string[]) => {
    const held = vi.mocked(globalThis.fetch).getMockImplementation()!;
    vi.mocked(globalThis.fetch).mockImplementation((input, init) =>
      /\/v1\/me\/rights$/.test(String(input).split("?")[0]!) ? Promise.resolve(new Response(JSON.stringify({ rights }))) : held(input, init),
    );
  };
  const link = () => screen.queryByRole("link", { name: /^Build a report/ });

  test("is offered to a builder where Superset is deployed, beside Reports, opening Superset in a new tab", async () => {
    vi.mocked(oidcConfig.deploymentReportsUrl).mockReturnValue(SUPERSET);
    withRights([...RIGHTS, "manage_dashboards"]);
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    const found = await screen.findByRole("link", { name: "Build a report (opens in new tab)" });
    expect(found.getAttribute("href")).toBe(SUPERSET);
    expect(found.getAttribute("target")).toBe("_blank");
    expect(found.getAttribute("rel")).toBe("noopener noreferrer");
    const reports = within(screen.getByRole("group", { name: "View" })).getByRole("button", { name: "Reports" });
    expect(reports.compareDocumentPosition(found) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const more = screen.getByRole("button", { name: /^More views/ });
    expect(found.compareDocumentPosition(more) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test("is not offered to a Reports Viewer, who holds no manage_dashboards, where Superset is deployed", async () => {
    vi.mocked(oidcConfig.deploymentReportsUrl).mockReturnValue(SUPERSET);
    withRights(RIGHTS);
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await within(screen.getByRole("group", { name: "View" })).findByRole("button", { name: "Reports" });
    expect(link()).toBeNull();
  });

  test("is not offered, even to a builder, where there is no Superset", async () => {
    vi.mocked(oidcConfig.deploymentReportsUrl).mockReturnValue(null);
    withRights([...RIGHTS, "manage_dashboards"]);
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await within(screen.getByRole("group", { name: "View" })).findByRole("button", { name: "Reports" });
    expect(link()).toBeNull();
  });
});
