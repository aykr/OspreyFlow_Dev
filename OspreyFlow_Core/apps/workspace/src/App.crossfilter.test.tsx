// @vitest-environment jsdom
//
// A brush on the timeline dims the graph (`spec/02_GLASS_FRONTEND.md` §2 rule 3), and the status
// bar says how much (rule 4). Seen on the owner's deployment, 8 October 2026: a brush fetched the
// right first-seen figures and nothing dimmed, "0 dimmed by filter". The cross-filter store is made
// once there is a token, and the effect that listens to it ran at mount and again only for a new
// case. Signed in through the identity provider, the token arrives after mount, so the effect found
// no store and never listened; `npm run dev`'s token is there at mount, so nothing else saw it.
// This signs in after mount, as the deployed Glass does.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, expect, test, vi } from "vitest";

import type { App as AppComponent } from "./App";
import type { CrossFilterStore } from "./crossfilter/store";

vi.mock("./canvas/GlassCanvas", () => ({ GlassCanvas: () => null }));
vi.mock("./map/MapView", () => ({ MapView: () => null }));

const made: CrossFilterStore[] = [];
vi.mock("./crossfilter/store", async () => {
  const actual = await vi.importActual<typeof import("./crossfilter/store")>("./crossfilter/store");
  return {
    ...actual,
    createCrossFilterStore: (...args: Parameters<typeof actual.createCrossFilterStore>) => {
      const store = actual.createCrossFilterStore(...args);
      made.push(store);
      return store;
    },
  };
});

vi.mock("./auth/userManager", async () => {
  const actual =
    await vi.importActual<typeof import("./auth/userManager")>("./auth/userManager");
  return {
    ...actual,
    isSignInRedirectCallback: vi.fn(() => true),
    completeSignInFromRedirect: vi.fn(async () => ({
      access_token: "good-token",
      profile: {
        sub: "analyst-1",
        clearance: "OFFICIAL",
        org_unit: "unit-1",
        roles: [],
        receivable_handling_codes: [],
      },
    })),
    clearRedirectCallbackParams: vi.fn(),
    getUserManager: vi.fn(() => ({ signinRedirect: vi.fn() }) as never),
    signIn: vi.fn(),
    signOut: vi.fn(),
  };
});

vi.mock("./map/providers", async () => {
  const actual = await vi.importActual<typeof import("./map/providers")>("./map/providers");
  return { ...actual, fetchMapConfig: vi.fn(() => new Promise(() => undefined)) };
});

let App!: typeof AppComponent;
beforeAll(async () => {
  const g = globalThis as { WebGL2RenderingContext?: unknown; WebGLRenderingContext?: unknown };
  g.WebGL2RenderingContext ??= class {};
  g.WebGLRenderingContext ??= class {};
  ({ App } = await import("./App"));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
  sessionStorage.clear();
  made.length = 0;
});

test("a filter's dimming reaches the status bar when the sign-in completes after the Glass opened", async () => {
  window.history.replaceState({}, "", "/?investigation=case-1");
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
    if (String(input).endsWith("/v1/ontology")) {
      return new Response(JSON.stringify({ edge_types: [], entity_types: [] }), { status: 200 });
    }
    return new Promise<Response>(() => undefined);
  });

  render(<App />);
  const bar = await screen.findByRole("status");
  expect(made).toHaveLength(1);

  made[0]!.store.setState({ dimmedNodeIds: new Set(["a", "b"]), dimmedCount: 2 });

  await vi.waitFor(() => expect(bar.textContent).toContain("2 dimmed by filter"));
});
