// @vitest-environment jsdom
//
// `06_DECISIONS.md` ADR-050's tests-owed list, restated as the reworded rule-4 test (objection 7's
// resolution): "an unauthenticated Glass shows the sign-in screen and issues no /v1 call; a
// wrong-audience token is refused and the Glass shows the sign-in screen with the reason." Not the
// Conduit's own already-covered refusal (`tests/services/api/test_auth.py`'s own audience test) —
// this is the Glass-side assertion that has content: what the Glass itself does about it.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
