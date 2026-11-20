/**
 * ADR-152 decision 8 (numbered 6 in the brief's layout): the security policy on every response, and
 * nothing from another address. No `unsafe-inline`, no `unsafe-eval`, no Superset exception.
 */
import { describe, expect, it } from "vitest";

import { build } from "../support/build.js";
import { nonceOf, parsePolicy, request, signIn } from "../support/http.js";

/** The ADR's directive list, in full. `NONCE` stands for the request's own. */
const EXPECTED: Record<string, string> = {
  "default-src": "'self'",
  "script-src": "'self' 'nonce-NONCE'",
  "style-src": "'self' 'nonce-NONCE'",
  "img-src": "'self' data:",
  "worker-src": "'self'",
  "connect-src": "'self'",
  "frame-src": "'none'",
  "frame-ancestors": "'none'",
  "object-src": "'none'",
  "base-uri": "'self'",
  "form-action": "'self'",
};

async function responses() {
  const { app } = build();
  const { cookie } = await signIn(app);
  return [
    ["the page", await request(app).get("/").set("Cookie", cookie)],
    ["the health route", await request(app).get("/healthz")],
    ["a 404", await request(app).get("/no/such/page").set("Cookie", cookie)],
    ["a 404 with no session", await request(app).get("/no/such/page")],
    ["a redirect", await request(app).get("/")],
    ["a refused request", await request(app).post("/session/sign-out").set("Cookie", cookie)],
    ["a HEAD", await request(app).head("/healthz")],
  ] as const;
}

describe("the security policy", () => {
  it("is exactly the ADR's directive list on every response, with the response's own nonce", async () => {
    for (const [name, res] of await responses()) {
      const header = res.headers["content-security-policy"] as string | undefined;
      expect(header, name).toBeDefined();
      const policy = parsePolicy(header);
      const nonce = nonceOf(header);
      const expected = new Map(Object.entries(EXPECTED).map(([k, v]) => [k, v.replace("NONCE", nonce)]));
      expect([...policy.keys()].sort(), name).toEqual([...expected.keys()].sort());
      for (const [directive, value] of expected) expect(policy.get(directive), `${name}: ${directive}`).toBe(value);
      expect(res.headers["content-security-policy-report-only"], name).toBeUndefined();
    }
  });

  it("has no unsafe-inline, no unsafe-eval, no wildcard, no other address, and no report-only twin", async () => {
    for (const [name, res] of await responses()) {
      const header = res.headers["content-security-policy"] as string;
      expect(header, name).not.toMatch(/unsafe-inline|unsafe-eval|unsafe-hashes|wasm-unsafe-eval/);
      expect(header, name).not.toMatch(/\*|https?:|blob:|superset/i);
    }
  });

  it("gives each response a fresh nonce, long enough to be unguessable", async () => {
    const { app } = build();
    const seen = new Set<string>();
    for (let i = 0; i < 20; i++) {
      const res = await request(app).get("/healthz");
      const nonce = nonceOf(res.headers["content-security-policy"] as string);
      expect(nonce.length).toBeGreaterThanOrEqual(22); // 16 random bytes as base64
      seen.add(nonce);
    }
    expect(seen.size).toBe(20);
  });

  it("puts the same nonce on the page's script tag as in the policy, and on no inline style", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    const res = await request(app).get("/").set("Cookie", cookie);
    const nonce = nonceOf(res.headers["content-security-policy"] as string);
    const tags = [...res.text.matchAll(/<script\b[^>]*>/g)].map((m) => m[0]);
    expect(tags.length).toBeGreaterThan(0);
    for (const tag of tags) expect(tag).toContain(`nonce="${nonce}"`);
    expect(res.text).not.toMatch(/\sstyle\s*=/i); // no inline style attribute
    expect(res.text).not.toMatch(/<style\b(?![^>]*nonce=)/i);

    const other = await request(app).get("/").set("Cookie", cookie);
    expect(nonceOf(other.headers["content-security-policy"] as string)).not.toBe(nonce);
    expect(other.text).not.toContain(`nonce="${nonce}"`);
  });
});

describe("the other headers", () => {
  it("are nosniff, same-origin referrer and same-origin opener policy on every response", async () => {
    for (const [name, res] of await responses()) {
      expect(res.headers["x-content-type-options"], name).toBe("nosniff");
      expect(res.headers["referrer-policy"], name).toBe("same-origin");
      expect(res.headers["cross-origin-opener-policy"], name).toBe("same-origin");
    }
  });

  it("have no Strict-Transport-Security: the front proxy owns it", async () => {
    for (const [name, res] of await responses()) {
      expect(res.headers["strict-transport-security"], name).toBeUndefined();
    }
  });

  it("do not name the software", async () => {
    for (const [name, res] of await responses()) {
      expect(res.headers["x-powered-by"], name).toBeUndefined();
    }
  });

  it("forbid storing a page that is a person's own", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    const res = await request(app).get("/").set("Cookie", cookie);
    expect(res.headers["cache-control"]).toMatch(/no-store/);
  });
});
