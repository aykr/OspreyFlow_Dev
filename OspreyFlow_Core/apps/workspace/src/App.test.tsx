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

    await screen.findByRole("heading", { name: "Ingest Studio" });
  });

  test("the Glass tile's own sign-in screen keeps its heading", async () => {
    window.history.replaceState({}, "", "/?from=launcher");
    vi.mocked(userManager.signIn).mockRejectedValue(new Error("nothing answered"));
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));

    render(<App />);

    await screen.findByRole("heading", { name: "OspreyFlow" });
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
        : url.endsWith("/v1/handling-scheme")
          ? { name: "test", classification: ["OFFICIAL"], handling_codes: {} }
          : url.endsWith("/v1/hotlists")
            ? { hotlists: [] }
            : url.endsWith("/v1/monitors")
              ? { monitors: [] }
              : url.endsWith("/v1/alerts")
                ? { alerts: [] }
                : url.endsWith("/v1/ingest/source-files")
            ? { root: "/ingest", files: [] }
            : [];
      return Promise.resolve(new Response(JSON.stringify(body)));
    });
  });

  test("after the Ingest Studio tile, the Ingest tab is the one showing", async () => {
    sessionStorage.setItem(
      "ospreyflow.launcherHandoff",
      JSON.stringify({ view: "ingest", at: Date.now() }),
    );

    render(<App />);

    const ingest = await screen.findByRole("button", { name: "Ingest Studio" });
    expect(ingest.getAttribute("aria-pressed")).toBe("true");
  });

  // The switch tests only look at the bar, so no request is answered: an answer of the wrong shape
  // for a panel that is not under test would crash that panel after the test had finished.
  const holdAllRequests = () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise<Response>(() => undefined));
  };

  test("the two apps are named in one switch at the far left, the open one pressed", async () => {
    holdAllRequests();
    render(<App />);

    const group = await screen.findByRole("group", { name: "Application" });
    const glass = within(group).getByRole("button", { name: "Glass" });
    const ingest = within(group).getByRole("button", { name: "Ingest Studio" });
    expect(glass.getAttribute("aria-pressed")).toBe("true");
    expect(ingest.getAttribute("aria-pressed")).toBe("false");
    const header = document.querySelector("header.app-header")!;
    expect(header.firstElementChild).toBe(group);
    expect(header.getAttribute("data-app")).toBe("glass");
  });

  test("inside the Ingest Studio the bar keeps only what belongs to it", async () => {
    holdAllRequests();
    sessionStorage.setItem("ospreyflow.launcherHandoff", JSON.stringify({ view: "ingest", at: Date.now() }));
    render(<App />);

    const group = await screen.findByRole("group", { name: "Application" });
    expect(within(group).getByRole("button", { name: "Ingest Studio" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelector("header.app-header")!.getAttribute("data-app")).toBe("ingest");
    for (const gone of ["Graph", "Map", "Watches", "Export ⚙", "History"]) {
      expect(screen.queryByRole("button", { name: gone })).toBeNull();
    }
    expect(screen.queryByRole("combobox", { name: /search entities/i })).toBeNull();
    // The case menu stays (the Studio's own "goes into" row carries a second one).
    expect(within(document.querySelector("header.app-header") as HTMLElement).getByRole("button", { name: /^Case:/ })).toBeTruthy();
  });

  test("the switch moves between the apps, and Glass returns to the view that was open", async () => {
    holdAllRequests();
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Watches" }));
    fireEvent.click(screen.getByRole("button", { name: "Ingest Studio" }));
    expect(screen.queryByRole("button", { name: "Watches" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Glass" }));
    expect(screen.getByRole("button", { name: "Watches" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelector("header.app-header")!.getAttribute("data-app")).toBe("glass");
  });

  test("after the Glass tile, the graph is the one showing and Ingest is not", async () => {
    holdAllRequests();
    render(<App />);

    const ingest = await screen.findByRole("button", { name: "Ingest Studio" });
    expect(ingest.getAttribute("aria-pressed")).toBe("false");
  });
});

describe("a stale sign-in is noticed whichever screen's call finds it (3 October 2026)", () => {
  // Seen on the owner's machine: after `make refresh` restarted the identity provider the Ingest
  // Studio and the case menu showed "401" as raw errors while the Glass itself re-signed in, because
  // only the Glass's own two calls were wired to the re-sign-in.
  const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

  async function signedInWithOntologyLoaded() {
    vi.mocked(userManager.isSignInRedirectCallback).mockReturnValue(true);
    vi.mocked(userManager.completeSignInFromRedirect).mockResolvedValue({
      access_token: "good-token",
      profile: {
        sub: "analyst-1",
        clearance: "OFFICIAL",
        org_unit: "unit-1",
        roles: [],
        receivable_handling_codes: [],
      },
    } as never);
    const signinRedirect = vi.fn();
    vi.mocked(userManager.getUserManager).mockReturnValue({ signinRedirect } as never);
    const sent: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      sent.push(url);
      if (url.endsWith("/v1/ontology")) {
        return new Response(JSON.stringify({ edge_types: [], entity_types: [] }), { status: 200 });
      }
      if (url.includes("/v1/ingest/recipes")) return new Response(null, { status: 401 });
      return new Promise<Response>(() => undefined);
    });
    render(<App />);
    // The first authenticated call has succeeded once the ontology has been asked for.
    await vi.waitFor(() => expect(sent.some((u) => u.endsWith("/v1/ontology"))).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 0));
    return signinRedirect;
  }

  test("a 401 on a call no Glass code watches (the Ingest Studio's) starts the silent re-sign-in", async () => {
    const signinRedirect = await signedInWithOntologyLoaded();

    await fetch(`${API}/v1/ingest/recipes`, { headers: { Authorization: "Bearer good-token" } });

    await vi.waitFor(() => expect(signinRedirect).toHaveBeenCalledWith({ prompt: "none" }));
  });

  test("two refusals at once start one re-sign-in, not two", async () => {
    const signinRedirect = await signedInWithOntologyLoaded();

    await Promise.all([
      fetch(`${API}/v1/ingest/recipes`, { headers: { Authorization: "Bearer good-token" } }),
      fetch(`${API}/v1/ingest/recipes`, { headers: { Authorization: "Bearer good-token" } }),
    ]);

    await vi.waitFor(() => expect(signinRedirect).toHaveBeenCalled());
    expect(signinRedirect).toHaveBeenCalledTimes(1);
  });

  test("a 401 for some other token does not sign the analyst out", async () => {
    const signinRedirect = await signedInWithOntologyLoaded();

    await fetch(`${API}/v1/ingest/recipes`, { headers: { Authorization: "Bearer an-older-token" } });

    expect(signinRedirect).not.toHaveBeenCalled();
  });
});
