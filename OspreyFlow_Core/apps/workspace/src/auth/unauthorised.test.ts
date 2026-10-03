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
