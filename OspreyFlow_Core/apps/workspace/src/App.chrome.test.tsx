// @vitest-environment jsdom
//
// ADR-145 decision 4 and Amendment 2 (variant B, the owner's choice of 7 November 2026): the case
// screen's chrome, counted on the real `App`. A keyboard user passes 24 controls before the canvas (25 before ADR-145 Amendment 19 moved Match strictness into the canvas toolbar)
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
import { useEffect } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";
import { forgetToolbarSettings } from "./canvas/toolbarVisibility";

// The stand-in draws what App hands the canvas toolbar (v0.6.1 glass-rows A: strictness after Layout), inside the
// canvas, where the real `GlassCanvas` draws its toolbar.
// C: the toolbar's id, `hidden` while App says so, and *Hide toolbar* at its end, as `GlassCanvas` draws them (the
// real toolbar's own hiding is held in a browser, `keyboard/glass-toolbar.spec.ts`).
// Each draw's `toolbarHidden` is kept, so the first draw can be held to the analyst's setting (`canvasDraws`).
const canvasDraws: (boolean | undefined)[] = [];
const canvasNarrow = { value: false };
// The canvas's T is the real `GlassCanvas`'s (`keyboard.spec.ts`); the stand-in hands its key to `onToolbarKey`, so App's
// wiring of what T does is held here.
vi.mock("./canvas/GlassCanvas", () => ({
  GlassCanvas: ({ toolbarAfterLayout, toolbarEnd, toolbarHidden, toolbarId, onToolbarKey, onToolbarCompactChange }: { toolbarAfterLayout?: import("react").ReactNode; toolbarEnd?: import("react").ReactNode; toolbarHidden?: boolean; toolbarId?: string; onToolbarKey?: () => void; onToolbarCompactChange?: (compact: boolean) => void }) => {
    canvasDraws.push(toolbarHidden);
    // The real canvas reports whether its toolbar is narrow (its width, read off the canvas); `canvasNarrow` says so here.
    useEffect(() => onToolbarCompactChange?.(canvasNarrow.value), [onToolbarCompactChange]);
    return (
      <div role="application" aria-label="Network canvas" tabIndex={0} onKeyDown={(e) => { if (e.key === "t" && e.target === e.currentTarget) onToolbarKey?.(); }}>
        <div role="toolbar" aria-label="Canvas tools" id={toolbarId} hidden={toolbarHidden}>{toolbarAfterLayout}{toolbarEnd}</div>
      </div>
    );
  },
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
  test("24 controls stand before the canvas, in this order (the owner's navigation, ADR-145 Amendment 15; strictness in the canvas toolbar, Amendment 19)", async () => {
    render(<App />);
    const canvas = await screen.findByRole("application", { name: "Network canvas" });
    await screen.findByRole("button", { name: "Open this case's data in the Ingest Studio ↗" });
    const stops = before(canvas);
    expect(stops).toEqual([
      // ADR-146 decision 2: Rules and Monitoring, with the count that left the banner.
      "Osprey, go to Home", "The Glass", "Ingest Studio", "Rules and Monitoring 3 open", "Admin",
      expect.stringMatching(/Search entities/), "Add many from a list", "Filters",
      // Amendment 15: one view switch, Graph · Map · Drawing board · Reports, then More (Amendment 17), by its name.
      "Graph", "Map", "Drawing board", "Reports", "More ways to show the case", "Export ▾", expect.stringMatching(/theme/i), expect.stringMatching(/· OFFICIAL/),
      // The case line: Case ‹switcher› · Saved views (n) · reads …, then the cross-link (Amendment 17).
      expect.stringMatching(/^Case: Kestrel/), expect.stringMatching(/^Saved views/), "Open this case's data in the Ingest Studio ↗",
      // The rail: the panel openers alone, then Help and the names toggle. The Graph has no row of its own
      // (Amendment 19 decision 5): strictness is in the canvas toolbar, inside the canvas.
      "Explore", "Ask & Chat", "History", "Help", "Show names",
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

// ADR-145 Amendment 14 (the owner's screen fixes of 13 November 2026, v0.5.2 step 3e): the dataset named
// once in the context row (its one place, one marker was replaced by Amendment 15's navigation).
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
    fireEvent.click(screen.getByRole("button", { name: /^More ways to show the case/ }));
    const more = within(await screen.findByRole("group", { name: "More ways to show the case" }).catch(() => screen.getByRole("dialog", { name: "More ways to show the case" })));
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
      // Ask & Chat opens a page, not a dialog (v0.6.0 #4); Explore and History open drawers.
      expect(opener.getAttribute("aria-haspopup")).toBe(name === "Ask & Chat" ? null : "dialog");
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
      // Explore and History are drawers; Ask & Chat is a page over the view (v0.6.0 #4).
      const shown = name === "Ask & Chat" ? "region" : "dialog";
      expect(screen.getAllByRole(shown, { name: new RegExp(title) }).length).toBeGreaterThan(0);
      expect(pressedViews()).toEqual(["Map"]);
      fireEvent.click(opener);
      await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("false"));
      expect(document.activeElement).toBe(opener);
      fireEvent.click(opener);
      await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("true"));
      const close = name === "Ask & Chat" ? /^Back to Map$/ : new RegExp(`^Close ${title}`);
      fireEvent.click(screen.getAllByRole("button", { name: close })[0]!);
      await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("false"));
      expect(document.activeElement).toBe(opener);
      expect(pressedViews()).toEqual(["Map"]);
    });
  }

  // ADR-145 Amendment 19: what is on the canvas, "Whole case", after *Saved views (n)*.
  test("the case line: You are in the Glass · Case ‹switcher› · Saved views (n) · Whole case · reads …", async () => {
    await ready();
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    await within(region).findByText("reads Prison intel");
    const parts = [...region.querySelectorAll(":scope > *, .govuk-notification-banner__content > *")]
      .filter((el) => !el.classList.contains("context-banner__sep") && !el.classList.contains("govuk-notification-banner__content"))
      .map((el) => (el.textContent ?? "").trim().replace(/\s+/g, " "));
    expect(parts.slice(0, 6)).toEqual(["You are in the Glass", "Case", expect.stringMatching(/^Case: Kestrel/), expect.stringMatching(/^Saved views/), "Whole case", "reads Prison intel"]);
  });

  test("Saved views opens its panel at the saved views list", async () => {
    await ready();
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    fireEvent.click(within(region).getByRole("button", { name: /^Saved views/ }));
    // ADR-145 Amendment 17: opened from the case line it is *Saved views*, its list the case's saved views.
    const panel = await screen.findByRole("dialog", { name: "Saved views" });
    const views = await within(panel).findByRole("region", { name: "Saved views in this case" });
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
    const more = screen.getByRole("button", { name: /^More ways to show the case/ });
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

// The lane-reviewer's findings on Part B (ADR-145 Amendment 15): All cases outside the Glass, focus after it, the switch's
// rights, exactly one current view, and Views in this case as a toggle.
describe("Part B after review (ADR-145 Amendment 15)", () => {
  const withRights = (rights: string[]) => {
    const held = vi.mocked(globalThis.fetch).getMockImplementation()!;
    vi.mocked(globalThis.fetch).mockImplementation((input, init) =>
      /\/v1\/me\/rights$/.test(String(input).split("?")[0]!) ? Promise.resolve(new Response(JSON.stringify({ rights }))) : held(input, init),
    );
  };
  const switchOf = () => {
    const group = screen.getByRole("group", { name: "View" });
    return { main: within(group).getAllByRole("button").map((b) => b.textContent) };
  };

  test("in the Ingest Studio the case menu's All cases opens the case picker, as before, not the Glass's Cases panel", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(await within(screen.getByRole("navigation", { name: "Places" })).findByRole("button", { name: /^Ingest Studio$/ }));
    const studio = await screen.findByRole("region", { name: "You are in the Ingest Studio" });
    fireEvent.click(await within(studio).findByRole("button", { name: /^Case: Kestrel/ }));
    const menu = await screen.findByRole("dialog", { name: "Case menu" }).catch(() => screen.getByRole("group", { name: "Case menu" }));
    fireEvent.click(within(menu).getByRole("button", { name: "All cases" }));
    expect(await screen.findByRole("heading", { level: 1 })).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Cases" })).toBeNull();
  });

  test("the Cases panel opened from All cases returns focus to the case menu's button when it closes", async () => {
    render(<App />);
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    const caseButton = await within(region).findByRole("button", { name: /^Case: Kestrel/ });
    caseButton.focus();
    fireEvent.click(caseButton);
    const menu = await screen.findByRole("dialog", { name: "Case menu" }).catch(() => screen.getByRole("group", { name: "Case menu" }));
    const all = within(menu).getByRole("button", { name: "All cases" });
    all.focus();
    fireEvent.click(all);
    const panel = await screen.findByRole("dialog", { name: "Cases" });
    fireEvent.click(within(panel).getByRole("button", { name: "Close Cases" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog", { name: "Cases" })).toBeNull());
    expect(document.activeElement).toBe(within(region).getByRole("button", { name: /^Case: Kestrel/ }));
  });

  test("Saved views is a toggle: expanded while its panel is open, a second press closes it", async () => {
    render(<App />);
    const region = await screen.findByRole("region", { name: "You are in the Glass" });
    const views = await within(region).findByRole("button", { name: /^Saved views/ });
    expect(views.getAttribute("aria-haspopup")).toBe("dialog");
    expect(views.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(views);
    await screen.findByRole("dialog", { name: "Saved views" });
    expect(views.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(views);
    await vi.waitFor(() => expect(screen.queryByRole("dialog", { name: "Saved views" })).toBeNull());
  });

  test("a Reports Viewer's switch is Reports, with Figures under More views: no graph, map or drawing board", async () => {
    withRights(["read_reports"]);
    render(<App />);
    await vi.waitFor(() => expect(screen.getByRole("group", { name: "View" })).toBeTruthy());
    await vi.waitFor(() => expect(switchOf().main).toEqual(["Reports"]));
    // A Reports Viewer lands on Figures, so More views is named after it (Amendment 2).
    fireEvent.click(screen.getByRole("button", { name: /^(More ways to show the case|Figures)/ }));
    const more = within(await screen.findByRole("group", { name: "More ways to show the case" }));
    expect(more.getAllByRole("button").map((b) => b.textContent)).toEqual(["Figures"]);
  });

  test("an investigator without read_reports or trace_ownership has Graph, Map and Drawing board, and Matrix and Connection strength under More views", async () => {
    withRights(["investigate"]);
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    await vi.waitFor(() => expect(switchOf().main).toEqual(["Graph", "Map", "Drawing board"]));
    fireEvent.click(screen.getByRole("button", { name: /^More ways to show the case/ }));
    const more = within(await screen.findByRole("group", { name: "More ways to show the case" }));
    expect(more.getAllByRole("button").map((b) => b.textContent)).toEqual(["Matrix", "Connection strength"]);
  });

  test("a drawing board chosen before the rights arrive gives way when they say the person may not investigate", async () => {
    // While the rights are unknown the Glass offers what it always offered (ADR-112), the drawing board among them.
    let answer: (rights: string[]) => void = () => undefined;
    const held = vi.mocked(globalThis.fetch).getMockImplementation()!;
    vi.mocked(globalThis.fetch).mockImplementation((input, init) =>
      /\/v1\/me\/rights$/.test(String(input).split("?")[0]!)
        ? new Promise<Response>((resolve) => (answer = (rights) => resolve(new Response(JSON.stringify({ rights })))))
        : held(input, init),
    );
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(within(screen.getByRole("group", { name: "View" })).getByRole("button", { name: "Drawing board" }));
    await screen.findByRole("heading", { name: /^Drawing boards in case/ });
    answer(["read_reports"]);
    await vi.waitFor(() => expect(screen.queryByRole("heading", { name: /^Drawing boards in case/ })).toBeNull());
    await vi.waitFor(() => expect(switchOf().main).toEqual(["Reports"]));
    expect(screen.getByRole("button", { name: /^Figures/ }).className).toContain("menu-button--pressed");
  });

  test("Ownership chosen before the rights arrive gives way when they do not offer it, and one view is current", async () => {
    let answer: (rights: string[]) => void = () => undefined;
    const held = vi.mocked(globalThis.fetch).getMockImplementation()!;
    vi.mocked(globalThis.fetch).mockImplementation((input, init) =>
      /\/v1\/me\/rights$/.test(String(input).split("?")[0]!)
        ? new Promise<Response>((resolve) => (answer = (rights) => resolve(new Response(JSON.stringify({ rights })))))
        : held(input, init),
    );
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(screen.getByRole("button", { name: /^More ways to show the case/ }));
    fireEvent.click(await within(await screen.findByRole("group", { name: "More ways to show the case" })).findByRole("button", { name: "Ownership" }));
    await vi.waitFor(() => expect(screen.getByRole("button", { name: /^Ownership/ }).className).toContain("menu-button--pressed"));
    answer(["investigate"]);
    await vi.waitFor(() => expect(switchOf().main).toEqual(["Graph", "Map", "Drawing board"]));
    await vi.waitFor(() =>
      expect(within(screen.getByRole("group", { name: "View" })).queryAllByRole("button", { pressed: true }).map((b) => b.textContent)).toEqual(["Graph"]),
    );
  });

  test("the built-in Administrator, offered Connection strength alone, has it in the switch and current", async () => {
    // rights.py's Administrator: manage_dashboards and manage_strength_influencers, neither investigate nor read_reports.
    withRights(["manage_dashboards", "manage_strength_influencers", "manage_people"]);
    render(<App />);
    await vi.waitFor(() => expect(switchOf().main).toEqual(["Connection strength"]));
    await vi.waitFor(() =>
      expect(within(screen.getByRole("group", { name: "View" })).queryAllByRole("button", { pressed: true }).map((b) => b.textContent)).toEqual([
        "Connection strength",
      ]),
    );
  });

  test("exactly one view is current: one pressed in the switch, or none there and More views naming its own", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    const group = () => screen.getByRole("group", { name: "View" });
    const pressed = () => within(group()).queryAllByRole("button", { pressed: true }).map((b) => b.textContent);
    for (const name of ["Map", "Drawing board", "Reports", "Graph"]) {
      fireEvent.click(within(group()).getByRole("button", { name }));
      await vi.waitFor(() => expect(pressed()).toEqual([name]));
      expect(screen.getByRole("button", { name: /^More ways to show the case/ }).className).not.toContain("menu-button--pressed");
    }
    fireEvent.click(screen.getByRole("button", { name: /^More ways to show the case/ }));
    fireEvent.click(await within(await screen.findByRole("group", { name: "More ways to show the case" })).findByRole("button", { name: "Matrix" }));
    await vi.waitFor(() => expect(pressed()).toEqual([]));
    expect(screen.getByRole("button", { name: /^Matrix/ }).className).toContain("menu-button--pressed");
  });
});

// v0.6.1 glass-rows A (ADR-145 Amendment 19 decision 5; the owner's rulings of 16 November 2026): the Graph's own
// row above the canvas, which held strictness alone, is gone; strictness is a button in the canvas toolbar.
describe("Match strictness in the canvas toolbar (Amendment 19 decision 5)", () => {
  test("the Graph draws no row of its own; strictness is in the canvas toolbar, naming the setting", async () => {
    render(<App />);
    const tools = await screen.findByRole("toolbar", { name: "Canvas tools" });
    // The fixture's threshold is 0.8: Broad.
    const button = await within(tools).findByRole("button", { name: "Match strictness: Broad" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("toolbar", { name: "Graph view" })).toBeNull();
    expect(document.querySelector(".view-toolbar")).toBeNull();
  });

  test("the Map keeps its row, Add site and Draw boundary, with no strictness in it", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(screen.getByRole("button", { name: "Map" }));
    const row = await screen.findByRole("toolbar", { name: "Map view" });
    expect(within(row).getByRole("button", { name: "Add site" })).toBeTruthy();
    expect(within(row).getByRole("button", { name: "Draw boundary" })).toBeTruthy();
    expect(within(row).queryByRole("button", { name: /strictness/i })).toBeNull();
  });
});

// v0.6.1 glass-rows C (ADR-145 Amendment 19 decision 6; the owner's rulings 3 and 4, 16 November 2026): a toolbar
// that can be hidden. *Hide toolbar* at the toolbar's right end hides it and slims the case line, which then ends
// with *Show toolbar*; each names the toolbar it controls and whether it is shown; focus moves between the two;
// T on the focused canvas does the same, focus staying on the canvas (the owner's ruling of 16 November 2026); the setting is the signed-in analyst's, in this browser; the Map has it, the Drawing
// board does not.
describe("a toolbar that can be hidden (Amendment 19 decision 6)", () => {
  const KEY = "ospreyflow.glass.toolbar.osprey-demo-analyst";
  beforeEach(() => {
    // The username the setting is kept under is the token's preferred_username, as the Studio's mode is.
    vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
      access_token: "a-token",
      profile: { sub: "analyst-1", preferred_username: "osprey-demo-analyst", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] },
    } as never); // prettier-ignore
  });
  afterEach(() => forgetToolbarSettings());
  const caseLine = () => screen.getByRole("region", { name: "You are in the Glass" });

  test("Hide toolbar hides the canvas toolbar, slims the case line, and Show toolbar there brings it back, focus moving between them", async () => {
    render(<App />);
    const tools = await screen.findByRole("toolbar", { name: "Canvas tools" });
    const hide = await within(tools).findByRole("button", { name: "Hide toolbar" });
    expect(hide.getAttribute("aria-expanded")).toBe("true");
    expect(hide.getAttribute("aria-controls")).toBe(tools.id);
    expect(tools.id).not.toBe("");
    await within(caseLine()).findByText(/^reads /);
    expect(within(caseLine()).queryByRole("button", { name: "Show toolbar" })).toBeNull();

    fireEvent.click(hide);
    expect(tools.hidden).toBe(true);
    // Out of the accessibility tree, not merely out of sight.
    expect(screen.queryByRole("toolbar", { name: "Canvas tools" })).toBeNull();
    const show = within(caseLine()).getByRole("button", { name: "Show toolbar" });
    expect(show.getAttribute("aria-expanded")).toBe("false");
    expect(show.getAttribute("aria-controls")).toBe(tools.id);
    expect(document.activeElement).toBe(show);
    // The slim line (case's seam): no reads, the case and Saved views kept, Show toolbar last.
    expect(caseLine().textContent).not.toMatch(/reads /);
    expect(within(caseLine()).getByRole("button", { name: /^Saved views/ })).toBeTruthy();
    expect(within(caseLine()).getAllByRole("button").at(-1)).toBe(show);
    expect(localStorage.getItem(KEY)).toBe("hidden");

    fireEvent.click(show);
    expect(tools.hidden).toBe(false);
    expect(document.activeElement).toBe(within(tools).getByRole("button", { name: "Hide toolbar" }));
    expect(within(caseLine()).queryByRole("button", { name: "Show toolbar" })).toBeNull();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  test("the Glass opens as the analyst left it: hidden at the first draw", async () => {
    localStorage.setItem(KEY, "hidden");
    canvasDraws.length = 0;
    render(<App />);
    const show = await within(await screen.findByRole("region", { name: "You are in the Glass" })).findByRole("button", { name: "Show toolbar" });
    expect(show.getAttribute("aria-expanded")).toBe("false");
    await screen.findByRole("application", { name: "Network canvas" });
    expect(screen.queryByRole("toolbar", { name: "Canvas tools" })).toBeNull();
    // Never drawn shown first and hidden after: every draw of the canvas had it hidden.
    expect(canvasDraws.length).toBeGreaterThan(0);
    expect(canvasDraws.every((hidden) => hidden === true)).toBe(true);
  });

  test("under the Ask & Chat page (ADR-145 Amendment 18) there is no Show toolbar and the key does nothing; back on the view, both are as left", async () => {
    localStorage.setItem(KEY, "hidden");
    render(<App />);
    const show = await within(await screen.findByRole("region", { name: "You are in the Glass" })).findByRole("button", { name: "Show toolbar" });
    expect(show).toBeTruthy();
    const opener = within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "Ask & Chat" });
    fireEvent.click(opener);
    await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("true"));
    expect(screen.getByRole("application", { name: "Network canvas" }).closest("[inert]")).not.toBeNull();
    // Showing it would send focus to Hide toolbar inside the inert view, and lose it.
    expect(within(caseLine()).queryByRole("button", { name: "Show toolbar" })).toBeNull();
    fireEvent.keyDown(document.body, { key: "t", code: "KeyT" });
    expect(localStorage.getItem(KEY)).toBe("hidden");
    fireEvent.click(opener);
    await vi.waitFor(() => expect(opener.getAttribute("aria-expanded")).toBe("false"));
    expect(within(caseLine()).getByRole("button", { name: "Show toolbar" })).toBeTruthy();
  });

  test("Show toolbar reads Show where the canvas says its toolbar is narrow (ruling 14), its name kept", async () => {
    canvasNarrow.value = true;
    try {
      localStorage.setItem(KEY, "hidden");
      render(<App />);
      const show = await within(await screen.findByRole("region", { name: "You are in the Glass" })).findByRole("button", { name: "Show toolbar" });
      await vi.waitFor(() => expect(show.textContent).toBe("Show"));
    } finally {
      canvasNarrow.value = false;
    }
  });

  test("another analyst's setting on this browser is not this one's", async () => {
    localStorage.setItem("ospreyflow.glass.toolbar.someone-else", "hidden");
    render(<App />);
    expect(await screen.findByRole("toolbar", { name: "Canvas tools" })).toBeTruthy();
    expect(within(caseLine()).queryByRole("button", { name: "Show toolbar" })).toBeNull();
  });

  test("T on the canvas hides and shows it, focus staying on the canvas; T anywhere else does nothing", async () => {
    render(<App />);
    const tools = await screen.findByRole("toolbar", { name: "Canvas tools" });
    await within(tools).findByRole("button", { name: "Hide toolbar" });
    // Elsewhere: on the page, or typed in search; each checked on its own, so two that each toggled could not cancel out.
    fireEvent.keyDown(document.body, { key: "t", code: "KeyT" });
    expect(tools.hidden).toBe(false);
    fireEvent.keyDown(screen.getByRole("combobox", { name: /Search entities/ }), { key: "t", code: "KeyT" });
    expect(tools.hidden).toBe(false);
    fireEvent.keyDown(document.body, { key: "T", code: "KeyT", altKey: true, shiftKey: true });
    expect(tools.hidden).toBe(false);
    expect(localStorage.getItem(KEY)).toBeNull();
    const canvas = screen.getByRole("application", { name: "Network canvas" });
    canvas.focus();
    fireEvent.keyDown(canvas, { key: "t", code: "KeyT" });
    expect(tools.hidden).toBe(true);
    expect(within(caseLine()).getByRole("button", { name: "Show toolbar" })).toBeTruthy();
    // The key's place is the canvas, which keeps focus: nothing was lost to move it from.
    expect(document.activeElement).toBe(canvas);
    expect(localStorage.getItem(KEY)).toBe("hidden");
    fireEvent.keyDown(canvas, { key: "t", code: "KeyT" });
    expect(tools.hidden).toBe(false);
    expect(document.activeElement).toBe(canvas);
  });

  test("the Map has the same control and the same setting: its row hidden, Show toolbar on the line", async () => {
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(screen.getByRole("button", { name: "Map" }));
    const row = await screen.findByRole("toolbar", { name: "Map view" });
    const hide = within(row).getByRole("button", { name: "Hide toolbar" });
    expect(hide.getAttribute("aria-controls")).toBe(row.id);
    fireEvent.click(hide);
    expect(row.hidden).toBe(true);
    expect(screen.queryByRole("toolbar", { name: "Map view" })).toBeNull();
    const show = within(caseLine()).getByRole("button", { name: "Show toolbar" });
    expect(document.activeElement).toBe(show);
    expect(localStorage.getItem(KEY)).toBe("hidden");
    // One setting: back on the Graph its toolbar is hidden too.
    fireEvent.click(screen.getByRole("button", { name: "Graph" }));
    await screen.findByRole("application", { name: "Network canvas" });
    expect(screen.queryByRole("toolbar", { name: "Canvas tools" })).toBeNull();
    expect(within(caseLine()).getByRole("button", { name: "Show toolbar" })).toBeTruthy();
  });

  test("the Drawing board is not hidden: its line is the full one with no Show toolbar, whatever the setting, and T does nothing there", async () => {
    localStorage.setItem(KEY, "hidden");
    render(<App />);
    await screen.findByRole("application", { name: "Network canvas" });
    fireEvent.click(screen.getByRole("button", { name: "Drawing board" }));
    await within(caseLine()).findByText(/^reads /);
    expect(within(caseLine()).queryByRole("button", { name: "Show toolbar" })).toBeNull();
    fireEvent.keyDown(document.body, { key: "t", code: "KeyT" });
    expect(localStorage.getItem(KEY)).toBe("hidden");
  });
});
