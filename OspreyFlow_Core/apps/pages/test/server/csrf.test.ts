/**
 * ADR-152 decision 5: a cookie now authenticates the browser's calls, so `pages` refuses a
 * state-changing request without a valid anti-forgery token for its session. The mechanism is a
 * synchroniser token held in the session, sent in the `_csrf` form field or the `X-CSRF-Token`
 * header, compared in constant time.
 *
 * Each case is the request as Express receives it: a method, a `Cookie` header, an `Origin`, a
 * body. The routes are the real ones plus `/_test/echo`, which the factory's seam adds for every
 * method, so PUT, PATCH and DELETE have somewhere to land.
 */
import { describe, expect, it } from "vitest";

import { tokensMatch } from "../../server/csrf.js";
import { COOKIE_NAME } from "../../server/sessions.js";
import { build } from "../support/build.js";
import { request, setCookies, signIn } from "../support/http.js";

const STATE_CHANGING = ["post", "put", "patch", "delete"] as const;
const SAFE = ["get", "head", "options"] as const;

describe.each(STATE_CHANGING)("%s", (method) => {
  const send = (app: ReturnType<typeof build>["app"], cookie?: string) => {
    const r = request(app)[method]("/_test/echo");
    return cookie === undefined ? r : r.set("Cookie", cookie);
  };

  it("with no token is refused 403, in words", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    const res = await send(app, cookie);
    expect(res.status).toBe(403);
    expect(res.text).toMatch(/could not be checked/i);
    expect(res.text).not.toContain("accepted");
  });

  it("with another session's token is refused 403", async () => {
    const { app } = build();
    const mine = await signIn(app);
    const theirs = await signIn(app);
    expect(theirs.csrf).not.toBe(mine.csrf);
    const asForm = await send(app, mine.cookie).type("form").send(`_csrf=${theirs.csrf}`);
    expect(asForm.status).toBe(403);
    const asHeader = await send(app, mine.cookie).set("X-CSRF-Token", theirs.csrf);
    expect(asHeader.status).toBe(403);
  });

  it("with an empty token is refused 403", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    expect((await send(app, cookie).type("form").send("_csrf=")).status).toBe(403);
    expect((await send(app, cookie).set("X-CSRF-Token", "")).status).toBe(403);
    expect((await send(app, cookie).set("X-CSRF-Token", "   ")).status).toBe(403);
  });

  it("with a token and no session at all is refused 403", async () => {
    const { app } = build();
    const { csrf } = await signIn(app);
    expect((await send(app).set("X-CSRF-Token", csrf)).status).toBe(403);
    expect((await send(app, `${COOKIE_NAME}=${"Q".repeat(43)}`).set("X-CSRF-Token", csrf)).status).toBe(403);
  });

  it("with the session's own token, in the form field, is accepted", async () => {
    const { app } = build();
    const { cookie, csrf } = await signIn(app);
    const res = await send(app, cookie).type("form").send(`_csrf=${csrf}&other=1`);
    expect(res.status).toBe(200);
    expect(res.text).toBe("accepted");
  });

  it("with the session's own token, in the header, is accepted", async () => {
    const { app } = build();
    const { cookie, csrf } = await signIn(app);
    const res = await send(app, cookie).set("X-CSRF-Token", csrf);
    expect(res.status).toBe(200);
  });

  it("is refused when a token is not its session's own at the moment it is sent (the session has ended)", async () => {
    const { app, clock } = build();
    const { cookie, csrf } = await signIn(app);
    clock.advance(3601);
    expect((await send(app, cookie).set("X-CSRF-Token", csrf)).status).toBe(403);
  });
});

describe("a forged cross-site request", () => {
  it("with the cookie, a foreign Origin and no token, is refused 403 and changes nothing", async () => {
    const { app, store } = build();
    const { cookie } = await signIn(app);
    const before = store.keys();
    const res = await request(app)
      .post("/session/sign-out")
      .set("Cookie", cookie)
      .set("Origin", "https://evil.example")
      .set("Referer", "https://evil.example/page")
      .type("form")
      .send("anything=1");
    expect(res.status).toBe(403);
    expect(store.keys()).toEqual(before); // the session was not ended
  });

  it("is not made acceptable by a method override header", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    const res = await request(app).post("/_test/echo").set("Cookie", cookie).set("X-HTTP-Method-Override", "GET");
    expect(res.status).toBe(403);
  });

  it("is not made acceptable by sending the session identifier as the token", async () => {
    const { app } = build();
    const { cookie, id } = await signIn(app);
    const res = await request(app).post("/_test/echo").set("Cookie", cookie).set("X-CSRF-Token", id);
    expect(res.status).toBe(403);
  });

  it("does not echo a token it refused, and sets no cookie", async () => {
    const { app } = build();
    const { cookie } = await signIn(app);
    const res = await request(app).post("/_test/echo").set("Cookie", cookie).type("form").send("_csrf=REFUSED-TOKEN-VALUE");
    expect(res.status).toBe(403);
    expect(res.text).not.toContain("REFUSED-TOKEN-VALUE");
    expect(setCookies(res)).toEqual([]);
  });
});

describe("the safe methods need no token (control)", () => {
  it.each(SAFE)("%s with no token is not refused", async (method) => {
    const { app } = build();
    const { cookie } = await signIn(app);
    for (const path of ["/", "/_test/echo"]) {
      const res = await request(app)[method](path).set("Cookie", cookie);
      expect(res.status, `${method} ${path}`).not.toBe(403);
      expect(res.status, `${method} ${path}`).toBeLessThan(400);
    }
    const anonymous = await request(app)[method]("/healthz");
    expect(anonymous.status).toBe(200);
  });
});

describe("the comparison", () => {
  it("is false for an empty, a shorter, a longer and a different token, and true only for the same", () => {
    const real = "A".repeat(43);
    expect(tokensMatch(real, real)).toBe(true);
    expect(tokensMatch("", "")).toBe(false);
    expect(tokensMatch("", real)).toBe(false);
    expect(tokensMatch(real, "")).toBe(false);
    expect(tokensMatch(real.slice(1), real)).toBe(false);
    expect(tokensMatch(`${real}A`, real)).toBe(false);
    expect(tokensMatch(`${"A".repeat(42)}B`, real)).toBe(false);
    expect(tokensMatch(undefined, real)).toBe(false);
  });
});
