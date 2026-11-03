// Any 401 the Conduit sends to a request carrying the signed-in token means the sign-in has gone
// stale (seen 3 October 2026: after `make refresh` restarted the identity provider, the Ingest
// Studio and the case menu showed "401" as raw errors while the Glass itself re-signed in, because
// only the Glass's own calls were wired to the re-sign-in). The fix is at the class: watch every
// call the page makes to the Conduit, rather than asking each screen to remember.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installUnauthorisedWatch } from "./unauthorised";

const API = "http://api";
let original: typeof fetch;
let uninstall: (() => void) | null = null;

beforeEach(() => {
  original = globalThis.fetch;
});
afterEach(() => {
  uninstall?.();
  uninstall = null;
  globalThis.fetch = original;
});

function setup(status: number, token = "tok") {
  const onUnauthorised = vi.fn();
  const underlying = vi.fn(async () => new Response(JSON.stringify({ detail: "x" }), { status }));
  globalThis.fetch = underlying as unknown as typeof fetch;
  uninstall = installUnauthorisedWatch({ apiBaseUrl: API, getToken: () => token, onUnauthorised });
  return { onUnauthorised, underlying };
}

const bearer = (token = "tok") => ({ headers: { Authorization: `Bearer ${token}` } });

describe("installUnauthorisedWatch", () => {
  it("reports a 401 to the Conduit on a request carrying the signed-in token", async () => {
    const { onUnauthorised } = setup(401);
    await fetch(`${API}/v1/ingest/recipes`, bearer());
    expect(onUnauthorised).toHaveBeenCalledTimes(1);
  });

  it("hands the response back untouched, so each screen still sees its own error", async () => {
    setup(401);
    const response = await fetch(`${API}/v1/ingest/recipes`, bearer());
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ detail: "x" });
  });

  it.each([200, 201, 403, 404, 500])("does nothing for a %i", async (status) => {
    const { onUnauthorised } = setup(status);
    await fetch(`${API}/v1/cases`, bearer());
    expect(onUnauthorised).not.toHaveBeenCalled();
  });

  it("ignores a 401 from some other host", async () => {
    const { onUnauthorised } = setup(401);
    await fetch("http://elsewhere/v1/x", bearer());
    expect(onUnauthorised).not.toHaveBeenCalled();
  });

  it("ignores a 401 on a request that carried no token (a sign-in call is not a stale sign-in)", async () => {
    const { onUnauthorised } = setup(401);
    await fetch(`${API}/v1/anything`);
    expect(onUnauthorised).not.toHaveBeenCalled();
  });

  it("ignores a 401 for an old token, so a slow request sent before re-signing in cannot sign the analyst out again", async () => {
    const { onUnauthorised } = setup(401, "the-new-token");
    await fetch(`${API}/v1/ingest/recipes`, bearer("the-old-token"));
    expect(onUnauthorised).not.toHaveBeenCalled();
  });

  it("recognises the token however the headers were given", async () => {
    const { onUnauthorised } = setup(401);
    await fetch(`${API}/a`, { headers: new Headers({ authorization: "Bearer tok" }) });
    await fetch(`${API}/b`, { headers: [["Authorization", "Bearer tok"]] });
    await fetch(new Request(`${API}/c`, { headers: { Authorization: "Bearer tok" } }));
    expect(onUnauthorised).toHaveBeenCalledTimes(3);
  });

  it("does nothing while nobody is signed in", async () => {
    const { onUnauthorised } = setup(401, "");
    await fetch(`${API}/v1/x`, { headers: { Authorization: "Bearer " } });
    expect(onUnauthorised).not.toHaveBeenCalled();
  });

  it("puts the original fetch back when uninstalled", async () => {
    const { underlying } = setup(401);
    uninstall?.();
    uninstall = null;
    expect(globalThis.fetch).toBe(underlying);
  });

  it("does not pull out a fetch that someone else has since wrapped", async () => {
    setup(401);
    const later = vi.fn();
    globalThis.fetch = later as unknown as typeof fetch;
    uninstall?.();
    uninstall = null;
    expect(globalThis.fetch).toBe(later);
  });

  it("passes a network failure through as it was thrown", async () => {
    const onUnauthorised = vi.fn();
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("network down");
    }) as unknown as typeof fetch;
    uninstall = installUnauthorisedWatch({ apiBaseUrl: API, getToken: () => "tok", onUnauthorised });
    await expect(fetch(`${API}/v1/x`, bearer())).rejects.toThrow("network down");
    expect(onUnauthorised).not.toHaveBeenCalled();
  });
});

// ADR-050 Amendment 1 (build order step 18b, rehearsal defect D1): the token is renewed in the
// background, and every screen keeps the token it was given at sign-in, so a renewal re-renders
// nothing and no screen reloads what it holds; the watch sends the renewed token in its place.
describe("installUnauthorisedWatch with a renewed token", () => {
  function sentAuthorisation(call: unknown[]): string | null {
    const [input, init] = call as [RequestInfo | URL, RequestInit | undefined];
    if (input instanceof Request) return input.headers.get("authorization");
    return new Headers(init?.headers).get("authorization");
  }

  it("sends the renewed token in place of the one the screen holds, however the headers were given", async () => {
    const underlying = vi.fn(async () => new Response("{}", { status: 200 }));
    globalThis.fetch = underlying as unknown as typeof fetch;
    uninstall = installUnauthorisedWatch({
      apiBaseUrl: API, getToken: () => "tok", currentToken: () => "renewed", onUnauthorised: vi.fn(),
    });
    await fetch(`${API}/a`, bearer());
    await fetch(`${API}/b`, { headers: new Headers({ authorization: "Bearer tok" }), method: "POST", body: "x" });
    await fetch(`${API}/c`, { headers: [["Authorization", "Bearer tok"]] });
    await fetch(new Request(`${API}/d`, { headers: { Authorization: "Bearer tok" } }));
    expect(underlying.mock.calls.map((call) => sentAuthorisation(call as unknown[]))).toEqual(Array(4).fill("Bearer renewed"));
  });

  it("never sends the token anywhere but the Conduit", async () => {
    const underlying = vi.fn(async () => new Response("{}", { status: 200 }));
    globalThis.fetch = underlying as unknown as typeof fetch;
    uninstall = installUnauthorisedWatch({
      apiBaseUrl: API, getToken: () => "tok", currentToken: () => "renewed", onUnauthorised: vi.fn(),
    });
    await fetch("http://elsewhere/x", bearer());
    expect(sentAuthorisation(underlying.mock.calls[0] as unknown[])).toBe("Bearer tok");
  });

  it("a call refused while a renewal was due is made once more with the renewed token, and the screen sees that answer", async () => {
    let current = "tok";
    const underlying = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) =>
      new Headers(init?.headers).get("authorization") === "Bearer renewed"
        ? new Response(JSON.stringify({ ok: true }), { status: 200 })
        : new Response(null, { status: 401 }),
    );
    globalThis.fetch = underlying as unknown as typeof fetch;
    const onUnauthorised = vi.fn(async () => {
      current = "renewed";
      return true;
    });
    uninstall = installUnauthorisedWatch({ apiBaseUrl: API, getToken: () => "tok", currentToken: () => current, onUnauthorised });

    const response = await fetch(`${API}/v1/cases`, { ...bearer(), method: "POST", body: JSON.stringify({ a: 1 }) });
    expect(response.status).toBe(200);
    expect(onUnauthorised).toHaveBeenCalledTimes(1);
    expect(underlying).toHaveBeenCalledTimes(2);
    expect(underlying.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({ a: 1 }));
  });

  it("a call is made once more at most: a second refusal is handed back", async () => {
    let current = "tok";
    const underlying = vi.fn(async () => new Response(null, { status: 401 }));
    globalThis.fetch = underlying as unknown as typeof fetch;
    const onUnauthorised = vi.fn(async () => {
      current = current === "tok" ? "renewed" : "renewed-again";
      return true;
    });
    uninstall = installUnauthorisedWatch({ apiBaseUrl: API, getToken: () => "tok", currentToken: () => current, onUnauthorised });
    const response = await fetch(`${API}/v1/cases`, bearer());
    expect(response.status).toBe(401);
    expect(underlying).toHaveBeenCalledTimes(2);
    expect(onUnauthorised).toHaveBeenCalledTimes(1);
  });

  it("when no renewed token came, the refusal is handed back as it was and nothing is sent again", async () => {
    const underlying = vi.fn(async () => new Response(null, { status: 401 }));
    globalThis.fetch = underlying as unknown as typeof fetch;
    uninstall = installUnauthorisedWatch({ apiBaseUrl: API, getToken: () => "tok", onUnauthorised: vi.fn(async () => false) });
    expect((await fetch(`${API}/v1/cases`, bearer())).status).toBe(401);
    expect(underlying).toHaveBeenCalledTimes(1);
  });
});
