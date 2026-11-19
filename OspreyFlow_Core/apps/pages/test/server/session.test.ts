/**
 * ADR-152 decision 4 and ADR-050 Amendment 4: the person's tokens stay on the server, in Valkey, every
 * key with a time limit; the browser holds one opaque identifier in one cookie.
 *
 * Every case goes through the real app factory and an HTTP client, with the request as Express
 * receives it (a method, a path, a `Cookie` header); the store is reached through its interface, and
 * the in-memory one refuses what Valkey refuses (rule 15): a write with no TTL, a key without the
 * prefix, a value over the limit.
 */
import express from "express";
import { describe, expect, it } from "vitest";

import { ABSOLUTE_SECONDS, COOKIE_NAME, IDLE_SECONDS } from "../../server/sessions.js";
import { MemorySessionStore, SESSION_KEY_PREFIX } from "../../server/sessionStore.js";
import { build } from "../support/build.js";
import { SENTINEL_TOKENS } from "../support/fakeProvider.js";
import {
  assertNoTokenLeak,
  csrfFromPage,
  idFrom,
  request,
  setCookies,
  signIn,
} from "../support/http.js";

describe("the session is stored with a time limit on every key", () => {
  it("writes the session under the service's own prefix, with a TTL no longer than the idle hour", async () => {
    const { app, store } = build();
    const { id } = await signIn(app);

    const keys = store.keys();
    expect(keys).toEqual([`${SESSION_KEY_PREFIX}${id}`]);
    for (const key of keys) {
      expect(key.startsWith("pages-session:")).toBe(true);
      const ttl = store.ttl(key);
      expect(ttl).not.toBeNull();
      expect(ttl as number).toBeGreaterThan(0);
      expect(ttl as number).toBeLessThanOrEqual(IDLE_SECONDS);
    }
    expect(IDLE_SECONDS).toBe(3600);
    expect(ABSOLUTE_SECONDS).toBe(8 * 3600);
  });

  it("signs in against the refusing store: no write of the service's own lacks a TTL", async () => {
    // The in-memory store throws on a write with no TTL, as Valkey's `noeviction` would make it a
    // leak. A sign-in that wrote one would answer 500 here, not 302.
    const { app } = build();
    const res = await request(app).get("/session/sign-in");
    expect(res.status).toBe(302);
  });

  it("keeps the TTL no longer than the identity provider's own session", async () => {
    const { app, store } = build({ provider: { idpSessionSeconds: 600 } });
    const { cookie } = await signIn(app);
    const [key] = store.keys() as [string];
    expect(store.ttl(key) as number).toBeLessThanOrEqual(600);

    // And it stays so when the session slides.
    await request(app).get("/").set("Cookie", cookie);
    expect(store.ttl(key) as number).toBeLessThanOrEqual(600);
  });

  it("never lets a sliding renewal outlast the absolute lifetime", async () => {
    const { app, store, clock } = build();
    const { cookie } = await signIn(app);
    const [key] = store.keys() as [string];
    // Active every half hour for seven and a half hours.
    for (let i = 0; i < 15; i++) {
      clock.advance(1800);
      const res = await request(app).get("/").set("Cookie", cookie);
      expect(res.status).toBe(200);
    }
    // Half an hour of the eight remains, so the key's life is half an hour, not the idle hour.
    expect(store.ttl(key) as number).toBeLessThanOrEqual(1800);
  });
});

describe("the cookie", () => {
  it("is named osprey_pages, HttpOnly, Secure, SameSite=Lax, with no Domain", async () => {
    const { app } = build();
    const res = await request(app).get("/session/sign-in");
    const cookies = setCookies(res);
    expect(cookies).toHaveLength(1);
    const cookie = cookies[0] as string;
    expect(cookie.startsWith(`${COOKIE_NAME}=`)).toBe(true);
    expect(COOKIE_NAME).toBe("osprey_pages");
    const attributes = cookie.split(";").slice(1).map((a) => a.trim().toLowerCase());
    expect(attributes).toContain("httponly");
    expect(attributes).toContain("secure");
    expect(attributes).toContain("samesite=lax");
    expect(attributes.some((a) => a.startsWith("domain"))).toBe(false);
  });

  it("holds 32 random bytes as base64url, a new one at each sign-in", async () => {
    const { app } = build();
    const a = idFrom(await request(app).get("/session/sign-in"));
    const b = idFrom(await request(app).get("/session/sign-in"));
    expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(b).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(a).not.toBe(b);
  });

  it("is never one the browser chose: a planted identifier is not adopted at sign-in", async () => {
    const { app, store } = build();
    const planted = "A".repeat(43);
    const res = await request(app).get("/session/sign-in").set("Cookie", `${COOKIE_NAME}=${planted}`);
    expect(idFrom(res)).not.toBe(planted);
    expect(store.keys()).not.toContain(`${SESSION_KEY_PREFIX}${planted}`);
    const page = await request(app).get("/").set("Cookie", `${COOKIE_NAME}=${planted}`);
    expect(page.status).toBe(302);
  });

  it.each([
    ["an unknown identifier", `${COOKIE_NAME}=${"B".repeat(43)}`],
    ["an empty value", `${COOKIE_NAME}=`],
    ["a value with a wildcard in it", `${COOKIE_NAME}=*`],
    ["a value that is far too long", `${COOKIE_NAME}=${"C".repeat(5000)}`],
    ["a cookie that is malformed", `${COOKIE_NAME}`],
  ])("treats %s as no session, in words and without an error", async (_name, header) => {
    const { app } = build();
    const res = await request(app).get("/").set("Cookie", header);
    expect(res.status).toBe(302);
    expect(res.headers["location"]).toBe("/session/sign-in");
  });
});

describe("no token leaves the server", () => {
  it("is in no body, header or cookie of any route, with sentinel tokens in the session", async () => {
    const { app, store } = build();

    // The sentinels really are in the session record, so a scan finding nothing means something.
    const first = await request(app).get("/session/sign-in");
    assertNoTokenLeak(first, "GET /session/sign-in");
    const [key] = store.keys() as [string];
    const stored = await store.get(key);
    expect(stored).toContain(SENTINEL_TOKENS.accessToken);
    expect(stored).toContain(SENTINEL_TOKENS.refreshToken);

    const cookie = `${COOKIE_NAME}=${idFrom(first)}`;
    const home = await request(app).get("/").set("Cookie", cookie);
    assertNoTokenLeak(home, "GET /");
    const csrf = csrfFromPage(home.text);

    const everyRoute = [
      () => request(app).get("/").set("Cookie", cookie),
      () => request(app).head("/").set("Cookie", cookie),
      () => request(app).options("/").set("Cookie", cookie),
      () => request(app).get("/healthz").set("Cookie", cookie),
      () => request(app).get("/healthz"),
      () => request(app).get("/no-such-page").set("Cookie", cookie),
      () => request(app).get("/").set("Cookie", `${COOKIE_NAME}=${"Z".repeat(43)}`),
      () => request(app).post("/session/sign-out").set("Cookie", cookie), // refused: no token
      () => request(app).post("/session/sign-out").set("Cookie", cookie).type("form").send("_csrf=wrong"),
      () => request(app).post("/session/sign-out").set("Cookie", cookie).type("form").send("%"),
    ];
    for (const send of everyRoute) {
      const res = await send();
      assertNoTokenLeak(res, `${res.status} ${JSON.stringify(res.request?.url)}`);
    }

    // Last, sign-out with the real token: its cookie header carries no token either.
    const out = await request(app).post("/session/sign-out").set("Cookie", cookie).type("form").send(`_csrf=${csrf}`);
    expect(out.status).toBe(303);
    assertNoTokenLeak(out, "POST /session/sign-out");

    // Signing in again while holding a session ends that one and starts another: nothing leaks there either.
    const held = await signIn(app);
    const again = await request(app).get("/session/sign-in").set("Cookie", held.cookie);
    assertNoTokenLeak(again, "GET /session/sign-in with a cookie");
    expect(store.keys()).toHaveLength(1);
  });

  it("is caught by the scan when one is put in the cookie, a header or the body (the scan itself)", async () => {
    const leaky = (where: "cookie" | "header" | "body" | "second-cookie") => {
      const app = express();
      app.get("/", (_req, res) => {
        if (where === "cookie") res.cookie(COOKIE_NAME, SENTINEL_TOKENS.accessToken, { httpOnly: true });
        if (where === "second-cookie") res.cookie("osprey_refresh", "x".repeat(43));
        if (where === "header") res.set("X-Debug", SENTINEL_TOKENS.refreshToken);
        res.send(where === "body" ? `<p>${SENTINEL_TOKENS.idToken}</p>` : "ok");
      });
      return app;
    };
    for (const where of ["cookie", "header", "body", "second-cookie"] as const) {
      const res = await request(leaky(where)).get("/");
      expect(() => assertNoTokenLeak(res, where), where).toThrow();
    }
    // And a clean response passes, so the scan does not simply throw.
    const quiet = express();
    quiet.get("/", (_req, res) => {
      res.send("ok");
    });
    const clean = await request(quiet).get("/");
    expect(() => assertNoTokenLeak(clean, "clean")).not.toThrow();
  });
});

describe("a record past its lifetime is refused, and gone", () => {
  it("refuses a session idle for more than an hour, and the key is gone", async () => {
    const { app, store, clock } = build();
    const { cookie, id } = await signIn(app);
    clock.advance(IDLE_SECONDS + 1);
    const res = await request(app).get("/").set("Cookie", cookie);
    expect(res.status).toBe(302);
    expect(res.headers["location"]).toBe("/session/sign-in");
    expect(store.keys()).not.toContain(`${SESSION_KEY_PREFIX}${id}`);
    expect(store.keys()).toEqual([]);
  });

  it("slides: a request inside the hour gives another hour", async () => {
    const { app, clock } = build();
    const { cookie } = await signIn(app);
    for (let i = 0; i < 3; i++) {
      clock.advance(IDLE_SECONDS - 60);
      const res = await request(app).get("/").set("Cookie", cookie);
      expect(res.status).toBe(200);
    }
  });

  it("refuses a session past eight hours, however active, and the key is gone", async () => {
    const { app, store, clock } = build();
    const { cookie } = await signIn(app);
    for (let i = 0; i < 16; i++) {
      clock.advance(1800);
      // At exactly eight hours the lifetime is spent; before it the session is live.
      const res = await request(app).get("/").set("Cookie", cookie);
      expect(res.status, `after ${(i + 1) * 30} minutes`).toBe(i < 15 ? 200 : 302);
    }
    expect(store.keys()).toEqual([]);
    clock.advance(1);
    const later = await request(app).get("/").set("Cookie", cookie);
    expect(later.status).toBe(302);
  });

  it("refuses and deletes a record past its absolute lifetime even if the store did not expire it", async () => {
    // A store whose own expiry has not fired (its clock is stopped): the service's check of the
    // record's own creation time is what refuses it, and deletes it.
    const stoppedAt = Date.UTC(2026, 10, 19, 9, 0, 0);
    const { app, store, clock } = build({ storeClock: () => stoppedAt });
    const { cookie, id } = await signIn(app);
    clock.advance(ABSOLUTE_SECONDS + 1);
    // The store still holds it: that is the point of the case.
    expect(store.keys()).toEqual([`${SESSION_KEY_PREFIX}${id}`]);

    const res = await request(app).get("/").set("Cookie", cookie);
    expect(res.status).toBe(302);
    expect(res.headers["location"]).toBe("/session/sign-in");
    expect(store.keys()).toEqual([]);
  });

  it("refuses a session past the identity provider's own, and the key is gone", async () => {
    const { app, store, clock } = build({ provider: { idpSessionSeconds: 600 } });
    const { cookie } = await signIn(app);
    clock.advance(601);
    const res = await request(app).get("/").set("Cookie", cookie);
    expect(res.status).toBe(302);
    expect(store.keys()).toEqual([]);
  });
});

describe("sign-out", () => {
  it("deletes the key and clears the cookie", async () => {
    const { app, store } = build();
    const { cookie, id, csrf } = await signIn(app);
    expect(store.keys()).toEqual([`${SESSION_KEY_PREFIX}${id}`]);

    const res = await request(app).post("/session/sign-out").set("Cookie", cookie).type("form").send(`_csrf=${csrf}`);
    expect(res.status).toBe(303);
    expect(res.headers["location"]).toBe("/");

    expect(store.keys()).toEqual([]);
    const cleared = setCookies(res).find((c) => c.startsWith(`${COOKIE_NAME}=`)) as string;
    expect(cleared).toBeDefined();
    expect(cleared.split(";")[0]).toBe(`${COOKIE_NAME}=`);
    const attributes = cleared.split(";").slice(1).map((a) => a.trim().toLowerCase());
    expect(attributes.some((a) => a.startsWith("expires=thu, 01 jan 1970"))).toBe(true);
    expect(attributes).toContain("httponly");
    expect(attributes).toContain("secure");
    expect(attributes).toContain("samesite=lax");
    expect(attributes.some((a) => a.startsWith("domain"))).toBe(false);

    // The old cookie, replayed, is no session.
    const again = await request(app).get("/").set("Cookie", cookie);
    expect(again.status).toBe(302);
  });

  it("answers an unreachable identity provider in words, with no session started and nothing said of access", async () => {
    const { app, store } = build({ provider: { unavailable: true } });
    const res = await request(app).get("/session/sign-in");
    expect(res.status).toBe(503);
    expect(res.text).toMatch(/not available/i);
    expect(res.text).not.toMatch(/revoked|denied|not allowed/i);
    expect(setCookies(res)).toEqual([]);
    expect(store.keys()).toEqual([]);
  });
});
