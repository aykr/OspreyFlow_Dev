// @vitest-environment jsdom
//
// `06_DECISIONS.md` ADR-050's tests-owed list, restated as the reworded rule-4 test (objection 7's
// resolution): "an unauthenticated Glass shows the sign-in screen and issues no /v1 call; a
// wrong-audience token is refused and the Glass shows the sign-in screen with the reason." Not the
// Conduit's own already-covered refusal (`tests/services/api/test_auth.py`'s own audience test) —
// this is the Glass-side assertion that has content: what the Glass itself does about it.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { StrictMode } from "react";
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

describe("06_DECISIONS.md ADR-050 — the sign-in gate", () => {
  test("an unauthenticated load shows the sign-in screen and issues no /v1 call", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    await screen.findByRole("button", { name: "Sign in" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test("a wrong-audience token refused by the Conduit shows the sign-in screen with the reason", async () => {
    vi.mocked(userManager.isSignInRedirectCallback).mockReturnValue(true);
    vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
      access_token: "token-with-the-wrong-audience",
      profile: {
        sub: "analyst-1",
        clearance: "OFFICIAL",
        org_unit: "unit-1",
        roles: [],
        receivable_handling_codes: [],
      },
      // Only `access_token`/`profile` are read (`displayPrincipalFromUser`,
      // `bearerToken`) — the rest of `oidc-client-ts`'s real `User` shape is irrelevant here.
    } as never);
    // Every /v1 call the Conduit ever sees this token on is refused — exactly what the realm's
    // own audience mapper pointed at the wrong client, or a Conduit with `verify_aud` on and a
    // token minted for someone else, produces.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 401 }));

    render(<App />);

    await screen.findByText(/could not be used to reach the workspace/i);
    // `getByRole` itself throws if the element is absent — the sign-in screen, not an error page.
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
  });
});

describe("the launcher's hand-off (a person who has just signed in at the launcher)", () => {
  // The mocks above are shared across the file, and the wrong-audience test leaves the callback
  // mock answering "yes, this is a redirect callback": start each of these from a plain load.
  beforeEach(() => {
    vi.mocked(userManager.isSignInRedirectCallback).mockReset().mockReturnValue(false);
    vi.mocked(userManager.completeSignInFromRedirect).mockReset();
    vi.mocked(userManager.signIn).mockReset().mockResolvedValue(undefined);
  });

  // Seen on the owner's deployment: signed in at the launcher, clicked The Glass, and was asked to
  // sign in again by a screen with a button and nothing else. The identity provider already knows
  // the person, so the Glass carries the sign-in on when the launcher says that is what happened.
  test("arriving from the launcher starts the sign-in without a click and issues no /v1 call", async () => {
    window.history.replaceState({}, "", "/?from=launcher");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    await vi.waitFor(() => expect(vi.mocked(userManager.signIn)).toHaveBeenCalledTimes(1));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test("React's development double-run does not start two sign-ins", async () => {
    window.history.replaceState({}, "", "/?from=launcher");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await vi.waitFor(() => expect(vi.mocked(userManager.signIn)).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(vi.mocked(userManager.signIn)).toHaveBeenCalledTimes(1);
  });

  test("once the sign-in has completed, the remembered tab choice is cleared", async () => {
    sessionStorage.setItem(
      "ospreyflow.launcherHandoff",
      JSON.stringify({ view: "ingest", at: Date.now() }),
    );
    vi.mocked(userManager.isSignInRedirectCallback).mockReturnValue(true);
    vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
      access_token: "a-token",
      profile: {
        sub: "analyst-1",
        clearance: "OFFICIAL",
        org_unit: "unit-1",
        roles: [],
        receivable_handling_codes: [],
      },
    } as never);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 401 }));

    render(<App />);

    await vi.waitFor(() =>
      expect(sessionStorage.getItem("ospreyflow.launcherHandoff")).toBeNull(),
    );
  });

  test("a plain load never starts a sign-in by itself", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    await screen.findByRole("button", { name: "Sign in" });
    expect(vi.mocked(userManager.signIn)).not.toHaveBeenCalled();
  });

  test("a refused sign-in is shown, not retried in a loop", async () => {
    window.history.replaceState({}, "", "/?from=launcher&error=access_denied");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    await screen.findByText(/could not be completed: access_denied/i);
    expect(vi.mocked(userManager.signIn)).not.toHaveBeenCalled();
  });

  test("if the sign-in cannot be started, the screen says so and the button still works", async () => {
    window.history.replaceState({}, "", "/?from=launcher");
    vi.mocked(userManager.signIn).mockRejectedValue(new Error("nothing answered"));
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    await screen.findByText(/could not be started/i);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
  });

  test("the Studio tile's sign-in screen says Ingest Studio, not the same words as the Glass's", async () => {
    window.history.replaceState({}, "", "/?from=launcher&view=ingest");
    vi.mocked(userManager.signIn).mockRejectedValue(new Error("nothing answered"));
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    // ADR-115 E2: the welcome page's card says which of the two the person is signing in to.
    await screen.findByRole("heading", { name: "Sign in to the Ingest Studio" });
  });

  test("the Glass tile's own sign-in screen keeps its heading", async () => {
    window.history.replaceState({}, "", "/?from=launcher");
    vi.mocked(userManager.signIn).mockRejectedValue(new Error("nothing answered"));
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    await screen.findByRole("heading", { level: 2, name: "Sign in" });
    expect(screen.getByRole("heading", { level: 1, name: "Intelligence mapping" })).toBeTruthy();
  });
});

describe("the tab the launcher asked for is the tab the Glass opens on", () => {
  // The Studio tile and the Glass tile used to open the identical page. After sign-in the Studio
  // tile's choice (remembered across the identity provider's round trip) must be what is shown.
  const signedInPerson = {
    access_token: "a-token",
    profile: {
      sub: "analyst-1",
      clearance: "OFFICIAL",
      org_unit: "unit-1",
      roles: ["source_author"],
      receivable_handling_codes: [],
    },
  } as never;

  beforeEach(() => {
    vi.mocked(userManager.isSignInRedirectCallback).mockReset().mockReturnValue(true);
    vi.mocked(userManager.completeSignInFromRedirect).mockReset().mockResolvedValue(signedInPerson);
    vi.mocked(ontologySchema.fetchOntologyRegistry).mockResolvedValue(
      new ontologySchema.OntologyRegistry({ entity_types: [], edge_types: [] } as never),
    );
    sessionStorage.setItem("ospreyflow.investigationId", "inv-1");
    // Just enough of the Conduit for the workspace to draw its toolbar and the Ingest tab's first
    // screen: empty lists, an empty ontology, an empty handling scheme and an empty ingest folder.
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const body = url.endsWith("/v1/ontology")
        ? { entity_types: [], edge_types: [] }
        : // ADR-145 decision 2: someone holding the Glass and the Studio, so the cross-link is offered.
          url.endsWith("/v1/me/rights")
          ? { rights: ["investigate", "edit_pipelines"] }
          : url.endsWith("/v1/handling-scheme")
          ? { name: "test", classification: ["OFFICIAL"], handling_codes: {} }
          : url.endsWith("/v1/hotlists")
            ? { hotlists: [] }
            : url.endsWith("/v1/monitors")
              ? { monitors: [] }
              : url.endsWith("/v1/alerts")
                ? { alerts: [] }
                : // The ingest folder is the case's (ADR-099 Amendment 3); this matched only the old
                  // `/v1/ingest/source-files`, so Connect got `[]` and crashed when it drew in time.
                  url.endsWith("/ingest/source-files")
            ? { root: "/ingest", files: [] }
            : [];
      return Promise.resolve(new Response(JSON.stringify(body)));
    });
  });

  // ADR-097 step 1 replaces ADR-065's two-part switch with the left rail: the Ingest Studio is one of
  // the places on it, and inside the Studio the rail leads back to the investigation. Each case below
  // keeps the point of the one it replaces.
  const rail = () => screen.getByRole("navigation", { name: "Workspace" });
  // ADR-146 decision 2: Monitoring left the Glass; Rules and Monitoring is a place of the switcher.
  const rulesPlace = async () =>
    within(await screen.findByRole("navigation", { name: "Places" })).findByRole("button", { name: /^Rules and Monitoring/ });
  // ADR-139: Connection strength, which stayed in the Glass, under the rail's More.
  const openStrength = async () => {
    fireEvent.click(within(await screen.findByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "More" }));
    fireEvent.click(await screen.findByRole("button", { name: "Connection strength" }));
  };

  test("after the Ingest Studio tile, the Ingest Studio is the one showing", async () => {
    sessionStorage.setItem(
      "ospreyflow.launcherHandoff",
      JSON.stringify({ view: "ingest", at: Date.now() }),
    );

    render(<App />);

    // ADR-145 decision 2: the banner's cross-link back to the case, in place of the Studio's rail.
    expect(await screen.findByRole("button", { name: /^← Back to .* in the Glass$/ })).toBeTruthy();
    expect(document.querySelector("header.app-header")!.getAttribute("data-app")).toBe("ingest");
  });

  // Seen live, 10 October 2026: Open Ingest Studio -> sign in -> no case open yet -> the case
  // gate -> choosing a case reloaded the page without the tile's choice, landing on the Glass.
  test("choosing a case at the gate keeps the Studio tile's choice", async () => {
    sessionStorage.setItem(
      "ospreyflow.launcherHandoff",
      JSON.stringify({ view: "ingest", at: Date.now() }),
    );
    sessionStorage.removeItem("ospreyflow.investigationId");
    vi.mocked(globalThis.fetch).mockImplementation((input) => {
      const url = String(input);
      const body = url.endsWith("/v1/investigations")
        ? [{ id: "inv-9", name: "TestCase", level: "editor", created_at: "2026-10-10T09:00:00Z", created_by: "a1" }]
        : // ADR-145 N6: the Studio tile's choice is kept only for someone the Studio is open to.
          url.endsWith("/v1/me/rights")
          ? { rights: ["investigate", "edit_pipelines"] }
          : url.endsWith("/v1/ontology")
          ? { entity_types: [], edge_types: [] }
          : [];
      return Promise.resolve(new Response(JSON.stringify(body)));
    });
    const went: string[] = [];
    const realLocation = window.location;
    Reflect.deleteProperty(window, "location");
    (window as { location: unknown }).location = {
      ...realLocation,
      assign: (url: string | URL) => went.push(String(url)),
    };

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "TestCase" }));
    expect(went).toHaveLength(1);
    expect(went[0]).toContain("view=ingest");
    (window as { location: unknown }).location = realLocation;
  });

  // The switch tests only look at the bar, so no request is answered: an answer of the wrong shape
  // for a panel that is not under test would crash that panel after the test had finished.
  const holdAllRequests = () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise<Response>(() => undefined));
  };
  // Every request held but the rights (ADR-145: no place is offered until they are known).
  const holdAllButRights = () => {
    vi.mocked(globalThis.fetch).mockImplementation((input) =>
      String(input).endsWith("/v1/me/rights")
        ? Promise.resolve(new Response(JSON.stringify({ rights: ["investigate", "read_alert_queue", "edit_pipelines"] })))
        : new Promise<Response>(() => undefined),
    );
  };

  test("the rail is at the far left and the places are in the bar, not the rail; the bar begins with the mark", async () => {
    holdAllButRights();
    render(<App />);

    await screen.findByRole("navigation", { name: "Workspace" });
    // ADR-145 decision 1: the Ingest Studio, Admin and Proposed types left the rail for the switcher.
    for (const gone of ["Ingest Studio", "Admin", "Proposed types"]) expect(within(rail()).queryByRole("button", { name: gone })).toBeNull();
    const places = within(screen.getByRole("navigation", { name: "Places" }));
    expect(places.getByRole("button", { name: "The Glass" }).getAttribute("aria-current")).toBe("page");
    expect(places.getByRole("button", { name: "Ingest Studio" })).toBeTruthy();
    const header = document.querySelector("header.app-header")!;
    // ADR-114 Amendment 5 point 9: the mark is the way back to Start.
    expect(header.firstElementChild?.getAttribute("aria-label")).toBe("Osprey, go to Home");
    expect(header.firstElementChild?.firstElementChild?.className).toBe("brand-mark");
    expect(header.textContent).toContain("Osprey");
    expect(header.getAttribute("data-app")).toBe("glass");
  });

  test("neither the rail nor the banner holds Monitoring: Rules and Monitoring is a place of the switcher", async () => {
    withRights(["investigate", "triage_alerts", "read_alert_queue"]);
    render(<App />);
    const rail = await screen.findByRole("navigation", { name: "Workspace" });
    expect(within(rail).queryByRole("button", { name: "Watches" })).toBeNull();
    expect(within(rail).queryByRole("button", { name: /Monitoring/ })).toBeNull();
    expect(within(await screen.findByRole("navigation", { name: "In the Glass" })).queryByRole("button", { name: /Monitoring/ })).toBeNull();
    fireEvent.click(await rulesPlace());
    expect(await screen.findByRole("region", { name: "You are in Rules and Monitoring" })).toBeTruthy();
    expect((await rulesPlace()).getAttribute("aria-current")).toBe("page");
    expect(screen.queryByRole("navigation", { name: "Workspace" })).toBeNull();
    expect(document.querySelector("header.app-header")!.getAttribute("data-app")).toBe("rules");
  });

  test("inside the Ingest Studio the bar keeps only what belongs to it", async () => {
    holdAllButRights();
    sessionStorage.setItem("ospreyflow.launcherHandoff", JSON.stringify({ view: "ingest", at: Date.now() }));
    render(<App />);

    await screen.findByRole("button", { name: /^← Back to .* in the Glass$/ });
    expect(document.querySelector("header.app-header")!.getAttribute("data-app")).toBe("ingest");
    for (const gone of ["Graph", "Map", "Watches", "Export", "History"]) {
      expect(screen.queryByRole("button", { name: gone })).toBeNull();
    }
    expect(screen.queryByRole("combobox", { name: /search entities/i })).toBeNull();
    // ADR-145 decision 1: the Studio has no rail.
    expect(screen.queryByRole("navigation", { name: "Workspace" })).toBeNull();
    // The case menu stays, in the banner (ADR-145 decision 2; the Studio's own "goes into" row carries a second one).
    expect(within(screen.getByRole("region", { name: "You are in the Ingest Studio" })).getByRole("button", { name: /^Case:/ })).toBeTruthy();
  });

  // ADR-145 N6: a hand-off (`?view=ingest|admin`) is a wish, checked against the rights.
  // Every request held but the rights, so only the rights decide what is drawn.
  const withRights = (rights: string[]) => {
    vi.mocked(globalThis.fetch).mockImplementation((input) =>
      String(input).endsWith("/v1/me/rights")
        ? Promise.resolve(new Response(JSON.stringify({ rights })))
        : new Promise<Response>(() => undefined),
    );
  };

  test("a hand-off to the Studio opens the Glass for someone the Studio is not open to", async () => {
    withRights(["investigate"]);
    sessionStorage.setItem("ospreyflow.launcherHandoff", JSON.stringify({ view: "ingest", at: Date.now() }));
    render(<App />);
    expect(await screen.findByRole("region", { name: "You are in the Glass" })).toBeTruthy();
    expect(document.querySelector("header.app-header")?.getAttribute("data-app")).toBe("glass");
    expect(screen.queryByRole("region", { name: "You are in the Ingest Studio" })).toBeNull();
  });

  test("a hand-off to Admin with a case open opens the Admin place, not Admin under the Glass", async () => {
    withRights(["investigate", "manage_people"]);
    sessionStorage.setItem("ospreyflow.launcherHandoff", JSON.stringify({ view: "admin", at: Date.now() }));
    render(<App />);
    expect(await screen.findByRole("region", { name: "You are in Admin" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "You are in the Glass" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Workspace" })).toBeNull();
  });

  test("a hand-off to Admin for someone Admin is not open to lands on Home", async () => {
    withRights(["investigate"]);
    sessionStorage.setItem("ospreyflow.launcherHandoff", JSON.stringify({ view: "admin", at: Date.now() }));
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "You are in Admin" })).toBeNull();
  });

  // ADR-145 decision 2: choosing another case in the Studio reloads the page (`openCase`); after it,
  // Back returns to the Glass's view that was open before, on the case now open.
  test("after a reload in the Studio, Back returns to the Glass's last view on the open case", async () => {
    withRights(["investigate", "read_alert_queue", "edit_pipelines"]);
    // In the Glass, on Connection strength; then the page is reloaded into the Studio, as `openCase` does.
    const first = render(<App />);
    await openStrength();
    first.unmount();
    sessionStorage.setItem("ospreyflow.launcherHandoff", JSON.stringify({ view: "ingest", at: Date.now() }));
    const went: string[] = [];
    const realLocation = window.location;
    Reflect.deleteProperty(window, "location");
    (window as { location: unknown }).location = { ...realLocation, assign: (url: string | URL) => went.push(String(url)) };
    try {
      render(<App />);
      fireEvent.click(await screen.findByRole("button", { name: /^← Back to .* in the Glass$/ }));
      expect(await screen.findByRole("region", { name: "Connection strength" })).toBeTruthy();
      // The case is the open one: Back neither changes it nor reloads.
      expect(sessionStorage.getItem("ospreyflow.investigationId")).toBe("inv-1");
      expect(went).toEqual([]);
    } finally {
      (window as { location: unknown }).location = realLocation;
    }
  });

  test("the switcher and the cross-link move between the places, and coming back returns to the view that was open", async () => {
    withRights(["investigate", "read_alert_queue", "triage_alerts", "edit_pipelines"]);
    render(<App />);

    await openStrength();
    const places = () => within(screen.getByRole("navigation", { name: "Places" }));
    fireEvent.click(await rulesPlace());
    expect(await screen.findByRole("region", { name: "You are in Rules and Monitoring" })).toBeTruthy();
    fireEvent.click(places().getByRole("button", { name: "Ingest Studio" }));
    expect(screen.queryByRole("navigation", { name: "Workspace" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^← Back to .* in the Glass$/ }));
    // The Glass's view that was open, not Rules and Monitoring, which is no view of the Glass.
    expect(await screen.findByRole("region", { name: "Connection strength" })).toBeTruthy();
    expect(places().getByRole("button", { name: "The Glass" }).getAttribute("aria-current")).toBe("page");
    expect(document.querySelector("header.app-header")!.getAttribute("data-app")).toBe("glass");
  });

  // ADR-124 decision 5: what the open case withholds is that case's own. Since ADR-146 decision 6 no
  // alert opens a case in place (the jump's case of its own went): an alert worked in another case is
  // opened by a reload into that case, on the alert's address, so nothing of case A carries over.
  test("an alert of another case is opened by a reload into that case, on the alert's address", async () => {
    const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
    vi.mocked(globalThis.fetch).mockImplementation((input) => {
      const url = String(input).split("?")[0]!;
      if (url.endsWith("/v1/me/rights")) return json({ rights: ["investigate", "keep_watches", "triage_alerts", "read_alert_queue"] });
      if (url.endsWith("/v1/investigations")) return json([{ id: "inv-1", name: "A", level: "editor", created_at: "", created_by: "" }]);
      if (url.endsWith("/inv-1/alerts")) {
        return json({
          alerts: [{ id: "a1", rule_id: "hotlist:h1", owner_id: "analyst-1", mode: "full", referent_node_ids: ["n1"],
                     evidence_available: true, investigation_id: "inv-2", created_at: "2026-10-10T09:00:00Z",
                     fired_on: [{ type: "Person", label: "A", files: [], more_files: 0, sources_withheld: false }] }],
        }); // prettier-ignore
      }
      if (url.endsWith("/inv-1/alert-queue")) return json([]);
      if (url.endsWith("/v1/alerts/a1")) return json({ investigation_id: "inv-2", explanation: { alert: { id: "a1" } } });
      return new Promise<Response>(() => undefined);
    });
    const went: string[] = [];
    const realLocation = window.location;
    try {
      render(<App />);
      fireEvent.click(await rulesPlace());
      fireEvent.click(await screen.findByRole("button", { name: "Open the alert" }));
      expect(window.location.pathname).toBe("/alerts/a1");
      Reflect.deleteProperty(window, "location");
      (window as { location: unknown }).location = { ...realLocation, pathname: "/alerts/a1", assign: (url: string | URL) => went.push(String(url)) };
      await vi.waitFor(() => expect(went).toEqual(["/alerts/a1?investigation=inv-2&from=case"]));
      expect(sessionStorage.getItem("ospreyflow.investigationId")).toBe("inv-2");
    } finally {
      (window as { location: unknown }).location = realLocation;
      window.history.replaceState(null, "", "/");
    }
  });

  // ADR-146 decision 2 and ADR-145 N6: an address does not draw the place for someone it is not
  // offered to (a Data Engineer reads the queue, for Home, but works no alert).
  test("an alert's address opens the Glass, not Rules and Monitoring, for someone it is not offered to", async () => {
    window.history.replaceState(null, "", "/alerts/a1");
    try {
      withRights(["investigate", "read_alert_queue", "deploy_rules", "edit_pipelines"]);
      render(<App />);
      expect(await screen.findByRole("region", { name: "You are in the Glass" })).toBeTruthy();
      expect(screen.queryByRole("region", { name: "You are in Rules and Monitoring" })).toBeNull();
      expect(screen.queryByRole("region", { name: "Rules and Monitoring" })).toBeNull();
      await vi.waitFor(() => expect(window.location.pathname).toBe("/"));
    } finally {
      window.history.replaceState(null, "", "/");
    }
  });

  // ADR-145 Amendment 4 decision 10: the Reports Viewer's journey, noted over the case switch's reload,
  // lands on the case's Figures under "From alert: ‹its title› · ← Back to your alerts", or on the Alert
  // monitoring board filtered to the alert; Back goes Home. Never the alert's address.
  let asked: string[] = [];
  const asViewer = () => {
    asked = [];
    const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body)));
    vi.mocked(globalThis.fetch).mockImplementation((input) => {
      const whole = String(input);
      asked.push(whole.replace(/^.*\/v1\/investigations\/inv-1\//, ""));
      const url = whole.split("?")[0]!;
      if (url.endsWith("/v1/me/rights")) return json({ rights: ["read_alert_queue", "read_reports", "read_report_feed"] });
      if (url.endsWith("/inv-1/alert-queue")) return json([]);
      if (url.endsWith("/v1/reports/dashboards")) return json([]);
      if (url.endsWith("/inv-1/reports")) {
        return json({ period_weeks: 4, as_of: "2026-11-08", generated_at: "2026-11-08T08:00:00Z", alerts_total: 0,
                      monitoring: { raised_by_rule: [{ week_start: "2026-11-02", label: "hotlists", typology: "", count: 2 }] } });  // prettier-ignore
      }
      return new Promise<Response>(() => undefined);
    });
  };
  const note = (to: "figures" | "board") =>
    sessionStorage.setItem("ospreyflow.alertJourney", JSON.stringify({
      to, caseId: "inv-1", alertId: "a14", title: "Hotlist alert in Kestrel", rule: { label: "hotlists", typology: "" }, weeks: 4 }));  // prettier-ignore

  test("the Reports Viewer's journey opens the case's Figures from an alert, and Back goes Home", async () => {
    asViewer();
    note("figures");
    render(<App />);
    const banner = await screen.findByRole("note", { name: "Opened from an alert" });
    expect(banner.textContent).toContain("From alert: Hotlist alert in Kestrel");
    await vi.waitFor(() => expect(asked).toContain("reports?weeks=4"));
    expect(screen.getByRole("heading", { name: "Figures" })).toBeTruthy();
    expect(window.location.pathname).toBe("/");
    fireEvent.click(within(banner).getByRole("button", { name: "← Back to your alerts" }));
    expect(await screen.findByRole("region", { name: "Needs your attention" })).toBeTruthy();
    expect(sessionStorage.getItem("ospreyflow.alertJourney")).toBeNull();
  });

  test("the journey's banner ends when the reader leaves the screen it opened", async () => {
    asViewer();
    note("figures");
    render(<App />);
    await screen.findByRole("note", { name: "Opened from an alert" });
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: "More" }));
    fireEvent.click(await screen.findByRole("button", { name: "Dashboards" }));
    await screen.findByRole("region", { name: "Alert monitoring" });
    expect(screen.queryByRole("note", { name: "Opened from an alert" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Figures" }));
    await screen.findByRole("heading", { name: "Figures" });
    expect(screen.queryByRole("note", { name: "Opened from an alert" })).toBeNull();
  });

  test("the Reports Viewer's journey opens the Alert monitoring board filtered to the alert's rule", async () => {
    asViewer();
    note("board");
    render(<App />);
    const board = await screen.findByRole("region", { name: "Alert monitoring" });
    await within(board).findByRole("note", { name: "Opened from an alert" });
    expect((within(board).getByRole("combobox", { name: "Rule" }) as HTMLSelectElement).value).toBe("hotlists:");
    expect((within(board).getByRole("combobox", { name: "Period" }) as HTMLSelectElement).value).toBe("4");
  });

  // ADR-146 decision 2: a place of its own, not a view over the working set: no Inspector, timeline or
  // status line under it, as under the Studio.
  test("Rules and Monitoring draws none of the Glass's working-set tools", async () => {
    withRights(["investigate", "triage_alerts", "read_alert_queue"]);
    render(<App />);
    fireEvent.click(await rulesPlace());
    expect(await screen.findByRole("region", { name: "You are in Rules and Monitoring" })).toBeTruthy();
    expect(document.querySelector(".side-panel-header")).toBeNull();
    expect(document.querySelector(".status-bar")).toBeNull();
  });

  // ADR-146 decision 6 (R5) and its test: *Open the evidence*, then *← Back to the alert*, returns to
  // the same alert, still open. The evidence is a private view of the alert's own case (ADR-144
  // decision 4), saved with the nodes the reader was shown and opened as the Glass's read-only lens.
  test("Open the evidence, then Back to the alert, returns to the same alert, still open", async () => {
    const person = {
      id: "n1", type: "Account", properties: { name: "GB-MULE-0042" },
      provenance: { state: "asserted", sources: [], first_seen: "2026-10-01T00:00:00Z" },
      handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      audit: { created_at: "2026-10-01T00:00:00Z", created_by: "seed", revision: 1 },
    }; // prettier-ignore
    const alert = {
      id: "a1", rule_id: "typology:r1", owner_id: "o", mode: "full", investigation_id: "inv-1", status: "open",
      assignee: null, typology: "structuring", referent_node_ids: ["n1"], created_at: "2026-11-01T09:00:00Z",
    }; // prettier-ignore
    const row = { alert, summary: "4 movements", kind: "typology", severity: "medium", audience: "case", team: null };
    const view = { id: "v-ev", case_id: "inv-1", name: "From alert: Structuring", created_by: "analyst-1", created_at: "2026-11-08T00:00:00Z", shared: false, chosen: 1 };
    const saved: unknown[] = [];
    const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
    vi.mocked(globalThis.fetch).mockImplementation((input, init) => {
      const url = String(input).split("?")[0]!;
      if (url.endsWith("/v1/me/rights")) return json({ rights: ["investigate", "triage_alerts", "read_alert_queue"] });
      if (url.endsWith("/v1/investigations")) return json([{ id: "inv-1", name: "Kestrel", level: "editor", created_at: "", created_by: "" }]);
      if (url.endsWith("/inv-1/alert-queue")) return json([row]);
      if (url.endsWith("/inv-1/alert-queue/a1")) return json({ ...row, nodes: [person], edges: [], transactions: [] });
      if (url.endsWith("/v1/alerts/a1")) return json({ investigation_id: "inv-1", explanation: { ...row, nodes: [person], edges: [], transactions: [] } });
      if (url.endsWith("/inv-1/views") && init?.method === "POST") {
        saved.push(JSON.parse(String(init.body)));
        return json(view, 201);
      }
      if (url.endsWith("/inv-1/views/v-ev")) return json({ view, nodes: [person], edges: [], layout: {}, missing: 0 });
      if (url.endsWith("/inv-1/views")) return json([view]);
      return new Promise<Response>(() => undefined);
    });
    try {
      render(<App />);
      fireEvent.click(await rulesPlace());
      fireEvent.click(await screen.findByRole("button", { name: /Open alert:.*Structuring/ }));
      await vi.waitFor(() => expect(window.location.pathname).toBe("/alerts/a1"));
      fireEvent.click(await screen.findByRole("button", { name: "Open the evidence" }));
      const banner = await screen.findByRole("region", { name: "Open view" });
      expect(saved).toEqual([{ name: "From alert: Structuring", node_ids: ["n1"] }]);
      expect(within(banner).getByText("From alert: Structuring")).toBeTruthy();
      expect(within(banner).getByText("Opened from an alert")).toBeTruthy();
      // The way back has focus when the view opens, so a keyboard user is on it.
      await vi.waitFor(() => expect(document.activeElement?.textContent).toBe("← Back to the alert"));
      expect(within(banner).getByText("Private")).toBeTruthy();
      expect(screen.getByRole("region", { name: "You are in the Glass" })).toBeTruthy();
      fireEvent.click(within(banner).getByRole("button", { name: "← Back to the alert" }));
      expect(await screen.findByRole("region", { name: "You are in Rules and Monitoring" })).toBeTruthy();
      expect(window.location.pathname).toBe("/alerts/a1");
      await vi.waitFor(() =>
        expect(screen.getByRole("button", { name: /Open alert:.*Structuring/ }).getAttribute("aria-pressed")).toBe("true"),
      );
      expect(await screen.findByRole("button", { name: "Open the evidence" })).toBeTruthy();
      expect(screen.queryByRole("region", { name: "Open view" })).toBeNull();
    } finally {
      window.history.replaceState(null, "", "/");
    }
  });

  // The review's round 2: a view saved but not opened is said on the alert, which stays open at its
  // address; nothing is shown as opened.
  test("Open the evidence says so on the alert when the view cannot be opened", async () => {
    const node = {
      id: "n1", type: "Account", properties: { name: "GB-MULE-0042" },
      provenance: { state: "asserted", sources: [], first_seen: "2026-10-01T00:00:00Z" },
      handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      audit: { created_at: "2026-10-01T00:00:00Z", created_by: "seed", revision: 1 },
    }; // prettier-ignore
    const alert = {
      id: "a1", rule_id: "typology:r1", owner_id: "o", mode: "full", investigation_id: "inv-1", status: "open",
      assignee: null, typology: "structuring", referent_node_ids: ["n1"], created_at: "2026-11-01T09:00:00Z",
    }; // prettier-ignore
    const row = { alert, summary: "4 movements", kind: "typology", severity: "medium", audience: "case", team: null };
    const view = { id: "v-ev", case_id: "inv-1", name: "From alert: Structuring", created_by: "analyst-1", created_at: "2026-11-08T00:00:00Z", shared: false, chosen: 1 };
    const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
    vi.mocked(globalThis.fetch).mockImplementation((input, init) => {
      const url = String(input).split("?")[0]!;
      if (url.endsWith("/v1/me/rights")) return json({ rights: ["investigate", "triage_alerts", "read_alert_queue"] });
      if (url.endsWith("/v1/investigations")) return json([{ id: "inv-1", name: "Kestrel", level: "editor", created_at: "", created_by: "" }]);
      if (url.endsWith("/inv-1/alert-queue")) return json([row]);
      if (url.endsWith("/inv-1/alert-queue/a1")) return json({ ...row, nodes: [node], edges: [], transactions: [] });
      if (url.endsWith("/v1/alerts/a1")) return json({ investigation_id: "inv-1", explanation: { ...row, nodes: [node], edges: [], transactions: [] } });
      if (url.endsWith("/inv-1/views") && init?.method === "POST") return json(view, 201);
      if (url.endsWith("/inv-1/views/v-ev")) return json({ error: "view_not_found" }, 404);
      return new Promise<Response>(() => undefined);
    });
    try {
      render(<App />);
      fireEvent.click(await rulesPlace());
      fireEvent.click(await screen.findByRole("button", { name: /Open alert:.*Structuring/ }));
      fireEvent.click(await screen.findByRole("button", { name: "Open the evidence" }));
      expect(
        await screen.findByText(/The evidence was saved as the private view “From alert: Structuring”, but it could not be opened/),
      ).toBeTruthy();
      expect(window.location.pathname).toBe("/alerts/a1");
      expect(screen.getByRole("region", { name: "You are in Rules and Monitoring" })).toBeTruthy();
      expect(screen.queryByRole("region", { name: "Open view" })).toBeNull();
      // Round 3: said on the alert only; the Glass, visited next, carries no stale "could not be opened".
      fireEvent.click(within(await screen.findByRole("navigation", { name: "Places" })).getByRole("button", { name: /^The Glass/ }));
      await vi.waitFor(() => expect(window.location.pathname).not.toBe("/alerts/a1"));
      expect(await screen.findByRole("button", { name: "Graph" })).toBeTruthy();
      expect(screen.queryByText(/That view could not be opened/)).toBeNull();
    } finally {
      window.history.replaceState(null, "", "/");
    }
  });

  test("after the Glass tile, the graph is the one showing and the Studio is not", async () => {
    holdAllRequests();
    render(<App />);

    const graph = await screen.findByRole("button", { name: "Graph" });
    expect(graph.getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelector("header.app-header")!.getAttribute("data-app")).toBe("glass");
  });
});

describe("a stale sign-in is noticed whichever screen's call finds it (3 October 2026)", () => {
  // Seen on the owner's machine: after `make refresh` restarted the identity provider the Ingest
  // Studio and the case menu showed "401" as raw errors while the Glass itself re-signed in, because
  // only the Glass's own two calls were wired to the re-sign-in. Since ADR-050 Amendment 1 (build
  // order step 18b) the reaction is a silent renewal in the background, never a page redirect.
  const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const PROFILE = { sub: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] };
  const inSeconds = (seconds: number) => Math.floor(Date.now() / 1000) + seconds;

  /** Signed in as `good-token`; the Conduit refuses `good-token` on the Ingest Studio's call and
   * accepts `renewed-token`, so what a call carried is what it was answered. */
  async function signedInWithOntologyLoaded(expiresInSeconds = 300) {
    vi.mocked(userManager.isSignInRedirectCallback).mockReturnValue(true);
    vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
      access_token: "good-token",
      expires_at: inSeconds(expiresInSeconds),
      profile: PROFILE,
    } as never);
    const signinRedirect = vi.fn();
    vi.mocked(userManager.getUserManager).mockReturnValue({ signinRedirect } as never);
    vi.mocked(userManager.signIn).mockReset();
    const sent: { url: string; authorisation: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const authorisation = new Headers(init?.headers).get("authorization");
      sent.push({ url, authorisation });
      if (url.endsWith("/v1/ontology")) {
        return new Response(JSON.stringify({ edge_types: [], entity_types: [] }), { status: 200 });
      }
      if (url.includes("/v1/ingest/recipes")) {
        return authorisation === "Bearer renewed-token"
          ? new Response("[]", { status: 200 })
          : new Response(null, { status: 401 });
      }
      return new Promise<Response>(() => undefined);
    });
    render(<App />);
    // The first authenticated call has succeeded once the ontology has been asked for.
    await vi.waitFor(() => expect(sent.some((u) => u.url.endsWith("/v1/ontology"))).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 0));
    return { signinRedirect, sent };
  }

  const renewed = () => ({ access_token: "renewed-token", expires_at: inSeconds(300), profile: PROFILE }) as never;
  const recipes = () => fetch(`${API}/v1/ingest/recipes`, { headers: { Authorization: "Bearer good-token" } });

  test("a 401 on a call no Glass code watches (the Ingest Studio's) starts a silent renewal, not a redirect", async () => {
    vi.mocked(userManager.renewSilently).mockReset().mockResolvedValue(renewed());
    const { signinRedirect } = await signedInWithOntologyLoaded();

    // The person's own click in the Studio made the call (ADR-050 Amendment 2: a call refused while
    // nobody has done anything is not renewed, `windows stay signed in` below).
    fireEvent.pointerDown(window);
    const response = await recipes();

    expect(vi.mocked(userManager.renewSilently)).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(200); // made once more with the renewed token
    expect(signinRedirect).not.toHaveBeenCalled();
  });

  test("a 401 for some other token does not start a renewal", async () => {
    vi.mocked(userManager.renewSilently).mockReset().mockResolvedValue(renewed());
    await signedInWithOntologyLoaded();

    await fetch(`${API}/v1/ingest/recipes`, { headers: { Authorization: "Bearer an-older-token" } });

    expect(vi.mocked(userManager.renewSilently)).not.toHaveBeenCalled();
  });
});

describe("windows stay signed in: the token is renewed silently before it expires (ADR-050 Amendment 1, rehearsal defect D1)", () => {
  const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const PROFILE = { sub: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: [], receivable_handling_codes: [] };
  const inSeconds = (seconds: number) => Math.floor(Date.now() / 1000) + seconds;
  const renewed = () => ({ access_token: "renewed-token", expires_at: inSeconds(300), profile: PROFILE }) as never;

  async function signedIn(expiresInSeconds: number) {
    vi.mocked(userManager.isSignInRedirectCallback).mockReturnValue(true);
    vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
      access_token: "good-token",
      expires_at: inSeconds(expiresInSeconds),
      profile: PROFILE,
    } as never);
    const signinRedirect = vi.fn();
    vi.mocked(userManager.getUserManager).mockReturnValue({ signinRedirect } as never);
    vi.mocked(userManager.signIn).mockReset();
    const sent: { url: string; authorisation: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const authorisation = new Headers(init?.headers).get("authorization");
      sent.push({ url, authorisation });
      if (url.endsWith("/v1/ontology")) {
        return new Response(JSON.stringify({ edge_types: [], entity_types: [] }), { status: 200 });
      }
      if (url.includes("/v1/ingest/recipes")) {
        return authorisation === "Bearer renewed-token"
          ? new Response("[]", { status: 200 })
          : new Response(null, { status: 401 });
      }
      return new Promise<Response>(() => undefined);
    });
    render(<App />);
    await vi.waitFor(() => expect(sent.some((u) => u.url.endsWith("/v1/ontology"))).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 0));
    return { signinRedirect, sent };
  }

  const recipes = () => fetch(`${API}/v1/ingest/recipes`, { headers: { Authorization: "Bearer good-token" } });
  // ADR-050 Amendment 2: the person doing something, which a renewal now waits for.
  const press = () => fireEvent.keyDown(window, { key: "ArrowDown" });

  test("a token near expiry is renewed in the background, with no navigation, and the next call carries it", async () => {
    vi.mocked(userManager.renewSilently).mockReset().mockResolvedValue(renewed());
    const { signinRedirect, sent } = await signedIn(2);
    press();

    // Nothing is called and nothing refused: the renewal comes of the token's own expiry alone.
    await vi.waitFor(() => expect(vi.mocked(userManager.renewSilently)).toHaveBeenCalledTimes(1), { timeout: 4000 });
    await new Promise((resolve) => setTimeout(resolve, 0));

    const response = await recipes();
    expect(response.status).toBe(200);
    expect(sent.at(-1)?.authorisation).toBe("Bearer renewed-token");
    expect(signinRedirect).not.toHaveBeenCalled();
    expect(vi.mocked(userManager.signIn)).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Sign in" })).toBeNull();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("two triggers at once make one renewal, and both calls are answered with its token", async () => {
    let finish!: (value: unknown) => void;
    vi.mocked(userManager.renewSilently)
      .mockReset()
      .mockImplementation(() => new Promise((resolve) => (finish = resolve)) as never);
    await signedIn(300);

    press();
    const both = Promise.all([recipes(), recipes()]);
    await vi.waitFor(() => expect(vi.mocked(userManager.renewSilently)).toHaveBeenCalled());
    finish(renewed());
    const [a, b] = await both;

    expect([a.status, b.status]).toEqual([200, 200]);
    expect(vi.mocked(userManager.renewSilently)).toHaveBeenCalledTimes(1);
  });

  test("a failed renewal leaves the page in place and asks to sign in again there", async () => {
    vi.mocked(userManager.renewSilently).mockReset().mockResolvedValue(null);
    vi.mocked(userManager.signInAgainInPlace).mockReset().mockResolvedValue(renewed());
    const { signinRedirect, sent } = await signedIn(300);

    press();
    expect((await recipes()).status).toBe(401);

    const prompt = await screen.findByRole("alertdialog", { name: "Your session has ended" });
    expect(signinRedirect).not.toHaveBeenCalled();
    expect(vi.mocked(userManager.signIn)).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Sign in" })).toBeNull(); // not the sign-in screen

    fireEvent.click(within(prompt).getByRole("button", { name: "Sign in again" }));
    await vi.waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(vi.mocked(userManager.signInAgainInPlace)).toHaveBeenCalledTimes(1);

    expect((await recipes()).status).toBe(200);
    expect(sent.at(-1)?.authorisation).toBe("Bearer renewed-token");
  });

  test("an identity provider that cannot be reached is not said as an ended session", async () => {
    vi.mocked(userManager.renewSilently).mockReset().mockRejectedValue(new Error("IFrame timed out without a response"));
    await signedIn(300);

    press();
    await recipes();

    const prompt = await screen.findByRole("alertdialog", { name: "The sign-in service could not be reached" });
    expect(within(prompt).getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  // ADR-050 Amendment 2 (build order step 28 (b)): an unattended window is not kept alive.
  test("an unattended window lets its token lapse: no renewal, and nothing asked", async () => {
    vi.mocked(userManager.renewSilently).mockReset().mockResolvedValue(renewed());
    await signedIn(2);
    await new Promise((resolve) => setTimeout(resolve, 2500)); // past the renewal's time and the expiry
    expect(vi.mocked(userManager.renewSilently)).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("a call refused while nobody is there is not renewed; the person's first key press renews, and their call is answered", async () => {
    vi.mocked(userManager.renewSilently).mockReset().mockResolvedValue(renewed());
    const { sent } = await signedIn(300);

    expect((await recipes()).status).toBe(401); // a screen's own poll, say: no person behind it
    expect(vi.mocked(userManager.renewSilently)).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();

    press();
    await vi.waitFor(() => expect(vi.mocked(userManager.renewSilently)).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect((await recipes()).status).toBe(200);
    expect(sent.at(-1)?.authorisation).toBe("Bearer renewed-token");
  });
});
