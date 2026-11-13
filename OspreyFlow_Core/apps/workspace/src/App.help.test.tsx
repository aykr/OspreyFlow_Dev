// @vitest-environment jsdom
//
// ADR-145 Amendment 12 (the owner's ruling of 13 November 2026): the rail's Help, and the `?` key, open
// the keys panel over whichever view is on screen, and a second press closes it; Esc closes it too.
// It was drawn only beside the graph, so in every other view Help did nothing visible.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";

// `sigma`/`maplibre-gl` touch real WebGL — at *import* time, not only on mount — which jsdom does
// not provide (every existing test that touches `GlassCanvas`/`MapView` runs against a real
// browser: Playwright, `keyboard/*.tsx` and `map-verify/*`, never Vitest/jsdom). This test never
// renders past the sign-in gate, so both are stubbed outright rather than shimmed piecemeal —
// nothing here exercises canvas or map rendering, only the auth gate that sits in front of them.
vi.mock("./canvas/GlassCanvas", () => ({ GlassCanvas: () => null }));
vi.mock("./map/MapView", () => ({ MapView: () => null }));
// The timeline draws with ECharts, which needs a real canvas that jsdom has none of.
vi.mock("./timeline/Timeline", () => ({ Timeline: () => null }));

let App!: typeof AppComponent;
beforeAll(async () => {
  // Something else in `App.tsx`'s own import graph (not `GlassCanvas`/`MapView`, both stubbed
  // above) still reaches `sigma`'s own module-load-time `WebGL2RenderingContext` check — this
  // shim satisfies it without needing a real WebGL context, since nothing in this test suite ever
  // draws to a canvas. A plain top-level `import { App } from "./App"` would not work here: ES
  // module imports are hoisted and evaluated before any of this file's own statements run,
  // including this shim, so `App` is loaded dynamically, after it, instead.
  const g = globalThis as {
    WebGL2RenderingContext?: unknown;
    WebGLRenderingContext?: unknown;
  };
  g.WebGL2RenderingContext ??= class {};
  g.WebGLRenderingContext ??= class {};
  ({ App } = await import("./App"));
});

vi.mock("./auth/userManager", async () => {
  const actual =
    await vi.importActual<typeof import("./auth/userManager")>("./auth/userManager");
  return {
    ...actual,
    isSignInRedirectCallback: vi.fn(() => false),
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
  return {
    ...actual,
    fetchOntologyRegistry: vi.fn(
      () =>
        new Promise(() => {
          /* left pending — this test never reaches the point where its resolution matters */
        }),
    ),
  };
});

vi.mock("./map/providers", async () => {
  const actual = await vi.importActual<typeof import("./map/providers")>("./map/providers");
  return { ...actual, fetchMapConfig: vi.fn(() => new Promise(() => undefined)) };
});

import * as userManager from "./auth/userManager";
import * as ontologySchema from "./ontology/schema";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
  sessionStorage.clear();
});


describe("the rail's Help over every view the rail reaches", () => {
  const signedInPerson = {
    access_token: "a-token",
    profile: { sub: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] },
  } as never;

  beforeEach(() => {
    vi.mocked(userManager.isSignInRedirectCallback).mockReset().mockReturnValue(true);
    vi.mocked(userManager.completeSignInFromRedirect).mockReset().mockResolvedValue(signedInPerson);
    vi.mocked(ontologySchema.fetchOntologyRegistry).mockResolvedValue(
      new ontologySchema.OntologyRegistry({ entity_types: [], edge_types: [] } as never),
    );
    sessionStorage.setItem("ospreyflow.investigationId", "inv-1");
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const body = url.endsWith("/v1/ontology")
        ? { entity_types: [], edge_types: [] }
        : url.endsWith("/v1/me/rights")
          ? { rights: ["investigate", "trace_ownership", "ask_model", "read_reports"] }
          : url.endsWith("/v1/handling-scheme")
            ? { name: "test", classification: ["OFFICIAL"], handling_codes: {} }
            : url.endsWith("/v1/hotlists")
              ? { hotlists: [] }
              : url.endsWith("/v1/monitors")
                ? { monitors: [] }
                : url.endsWith("/v1/alerts")
                  ? { alerts: [] }
                  : [];
      return Promise.resolve(new Response(JSON.stringify(body)));
    });
  });

  const rail = () => screen.getByRole("navigation", { name: "Workspace" });
  const panel = () => screen.queryByRole("dialog", { name: "Welcome back" });

  /** A place reached from the rail: on it, or in its menu (named More before Amendment 12). */
  async function openFromRail(name: string): Promise<void> {
    const direct = within(rail()).queryByRole("button", { name });
    if (direct) {
      fireEvent.click(direct);
      return;
    }
    fireEvent.click(within(rail()).getByRole("button", { name: /^(More|Explore Details)/ }));
    fireEvent.click(await screen.findByRole("button", { name }));
  }

  async function signedInWithThePanelClosed(): Promise<void> {
    render(<App />);
    await screen.findByRole("navigation", { name: "Workspace" });
    const open = panel();
    if (open) fireEvent.click(within(open).getByRole("button", { name: "Close the welcome panel" }));
    expect(panel()).toBeNull();
  }

  const VIEWS: [string, string | null][] = [
    ["the graph", null],
    ["Dashboards", "Dashboards"],
    ["Ownership", "Ownership"],
    ["Connection strength", "Connection strength"],
  ];

  test.each(VIEWS)("in %s, Help opens the panel and a second press closes it", async (_view, place) => {
    await signedInWithThePanelClosed();
    if (place) await openFromRail(place);
    const help = within(rail()).getByRole("button", { name: "Help" });
    fireEvent.click(help);
    expect(panel()).not.toBeNull();
    fireEvent.click(help);
    expect(panel()).toBeNull();
  });

  test.each(VIEWS)("in %s, the ? key opens the panel and again closes it, and Esc closes it", async (_view, place) => {
    await signedInWithThePanelClosed();
    if (place) await openFromRail(place);
    fireEvent.keyDown(window, { key: "?" });
    expect(panel()).not.toBeNull();
    fireEvent.keyDown(window, { key: "?" });
    expect(panel()).toBeNull();
    fireEvent.keyDown(window, { key: "?" });
    fireEvent.keyDown(panel()!, { key: "Escape" });
    expect(panel()).toBeNull();
  });

  test("the panel carries the user guide's link, as Home's Glass card does", async () => {
    await signedInWithThePanelClosed();
    fireEvent.click(within(rail()).getByRole("button", { name: "Help" }));
    const link = within(panel()!).getByRole("link", { name: "Read the user guide (PDF)" });
    expect(link.getAttribute("href")).toMatch(/\/v1\/guides\/user$/);
  });
});
