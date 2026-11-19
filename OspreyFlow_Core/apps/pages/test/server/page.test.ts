/**
 * ADR-152 decision 1: pages are complete when sent; with scripts off each still does its job. The one
 * page says who is signed in, from the session, and nothing else of the session.
 */
import { describe, expect, it } from "vitest";

import { COOKIE_NAME } from "../../server/sessions.js";
import { build } from "../support/build.js";
import { SENTINEL_SUBJECT, SENTINEL_TOKENS } from "../support/fakeProvider.js";
import { request, signIn } from "../support/http.js";

describe("GET /", () => {
  it("with no session answers 302 to the sign-in route", async () => {
    const { app } = build();
    const res = await request(app).get("/");
    expect(res.status).toBe(302);
    expect(res.headers["location"]).toBe("/session/sign-in");
    expect(res.text).not.toContain("Alex Example");
  });

  it("with a session shows the person's display name", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    const res = await request(app).get("/").set("Cookie", cookie);
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toMatch(/text\/html/);
    expect(res.text).toContain("Alex Example");
    expect(res.text).toContain('lang="en-GB"');
  });

  it("shows nothing else of the session: no subject, no token, no identifier, the anti-forgery token only in its form", async () => {
    const { app } = build();
    const { cookie, id, csrf } = await signIn(app);
    const res = await request(app).get("/").set("Cookie", cookie);
    expect(res.text).not.toContain(SENTINEL_SUBJECT);
    for (const token of Object.values(SENTINEL_TOKENS)) {
      expect(res.text).not.toContain(token);
      for (const piece of token.split(".")) expect(res.text).not.toContain(piece);
    }
    expect(res.text).not.toContain(id);
    expect(res.text).not.toContain(COOKIE_NAME);
    // The anti-forgery token is the session's, not a credential, and appears once: in the form.
    expect(res.text.split(csrf)).toHaveLength(2);
    expect(res.text).toContain(`name="_csrf" value="${csrf}"`);
  });

  it("escapes the display name: markup in a name is text", async () => {
    const { app } = build({ provider: { displayName: '<img src=x onerror="alert(1)"> & "Co"' } });
    const { cookie } = await signIn(app);
    const res = await request(app).get("/").set("Cookie", cookie);
    expect(res.text).not.toContain("<img src=x");
    expect(res.text).toContain("&lt;img src=x");
    expect(res.text).toContain("&amp;");
  });

  it("works with scripts off: no executable script, no handler, no inline style, and the sign-out is a real form", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    const res = await request(app).get("/").set("Cookie", cookie);
    for (const m of res.text.matchAll(/<script\b([^>]*)>/g)) {
      // A data block (ADR-152 decision 1's JSON block) is not run; nothing the page needs is a script.
      expect(m[1], "a script tag").toMatch(/type="application\/json"/);
      expect(m[1]).not.toMatch(/\bsrc=/);
    }
    expect(res.text).not.toMatch(/\son[a-z]+\s*=/i);
    expect(res.text).not.toMatch(/javascript:/i);
    expect(res.text).not.toMatch(/\sstyle\s*=/i);
    expect(res.text).not.toMatch(/<link\b[^>]*(?:href="https?:|href="\/\/)/i);
    expect(res.text).toMatch(/<form method="post" action="\/session\/sign-out">/);
    expect(res.text).toMatch(/<button type="submit">/);
  });
});

describe("the sign-in route", () => {
  it("with the fake provider starts a session and sends the person to the page", async () => {
    const { app } = build();
    const res = await request(app).get("/session/sign-in");
    expect(res.status).toBe(302);
    expect(res.headers["location"]).toBe("/");
  });
});

describe("GET /healthz", () => {
  it("answers with no session, no secret and no call to the identity provider or the store", async () => {
    // A provider that fails and a store that refuses everything: health must not touch either.
    const { app, store } = build({ provider: { unavailable: true } });
    const res = await request(app).get("/healthz");
    expect(res.status).toBe(200);
    expect(res.headers["set-cookie"]).toBeUndefined();
    expect(JSON.parse(res.text)).toEqual({ status: "ok" });
    expect(store.keys()).toEqual([]);
  });

  it("answers even with a session cookie it has no use for, and does not slide it", async () => {
    const { app, store, clock } = build();
    const { cookie } = await signIn(app);
    const [key] = store.keys() as [string];
    clock.advance(600);
    const before = store.ttl(key);
    const res = await request(app).get("/healthz").set("Cookie", cookie);
    expect(res.status).toBe(200);
    expect(store.ttl(key)).toBe(before);
  });
});

describe("an unknown path", () => {
  it("is a 404 in words, with no stack and no path echoed back", async () => {
    const { app } = build();
    const res = await request(app).get("/no-such-page<script>");
    expect(res.status).toBe(404);
    expect(res.text).toMatch(/could not be found/i);
    expect(res.text).not.toContain("<script>");
    expect(res.text).not.toMatch(/at .*\.(ts|js):\d+/);
  });
});
