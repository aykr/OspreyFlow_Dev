/**
 * Slice PL9a, acceptance: the page service's own sign-in, the authorisation-code round trip against a
 * Keycloak realm (ADR-152 decisions 4 and 5, ADR-050 Amendment 4, ADR-044).
 *
 * Every case drives the real app over real HTTP (supertest starts the app's server) against a fake
 * Keycloak that refuses what the real one refuses (`test/support/fakeKeycloak.ts`, the twin of
 * `tests/harness/fake_idp.py`; `CLAUDE.md` rule 15): a wrong or missing client secret, a code used twice
 * or past its time, a wrong redirect address, a wrong or missing PKCE verifier. Secrets and tokens are
 * made when the test runs; nothing here is a value anyone could use.
 *
 * Which test fails if the flow returns the wrong thing (rule 12):
 * - a callback that does not check `state`: "a state that is not the flow's own is refused" and "a state
 *   from an earlier sign-in is refused" and "a login cookie from another browser is refused";
 * - a login record that survives its first read: "a second use of the same callback is refused" and
 *   "two callbacks at once let one through";
 * - an ID token taken on trust: "an ID token that does not verify is refused" (wrong `iss`, `aud`,
 *   signature, `exp`), and "a nonce that is not the flow's own is refused";
 * - a token that reaches the browser, a log or an error: "the round trip" and every refusal's leak scan;
 * - a returnTo that leaves the application: "a returnTo that leaves the application is dropped to the home page";
 * - a provider's words repeated to the person: "the provider's own error is refused in fixed words";
 * - an unreachable provider told as a refusal, or the reverse: "an unreachable provider is a 503" and
 *   "a wrong client secret is a refusal";
 * - a session that outlives the provider's own: "the session key lives no longer than the provider's session";
 * - the settings: "settings" (unset leaves 503, partial refuses, short secret refused, nothing printed).
 */
import { inspect } from "node:util";

import type { Express } from "express";
import type { Response } from "supertest";
import { afterEach, describe, expect, it } from "vitest";

import { Secret, loadConfig } from "../../server/config.js";
import { LOGIN_COOKIE_NAME } from "../../server/loginState.js";
import { createOidcFlow } from "../../server/oidc.js";
import { COOKIE_NAME } from "../../server/sessionPolicy.js";
import { LOGIN_KEY_PREFIX, MemorySessionStore, SESSION_KEY_PREFIX } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { build } from "../support/build.js";
import { captureOutput } from "../support/capture.js";
import { testClock } from "../support/clock.js";
import type { TestClock } from "../support/clock.js";
import { AuthorisationRefused, CONDUIT_AUDIENCE, startFakeKeycloak } from "../support/fakeKeycloak.js";
import type { FakeKeycloak } from "../support/fakeKeycloak.js";
import { TEST_SESSION_SECRET, cookieFrom, csrfFromPage, everythingIn, idFrom, request, setCookies } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

const CLIENT_ID = "osprey-pages";
const ORIGIN = "https://pages.test.example";
const REDIRECT_URI = `${ORIGIN}/session/callback`;
const REFUSED_WORDS = "Sign-in was refused. Nothing about your access has changed.";
const UNAVAILABLE_WORDS = "Sign-in is not available just now. Nothing about your access has changed.";

interface Rig {
  fake: FakeKeycloak;
  app: Express;
  store: MemorySessionStore;
  clock: TestClock;
  clientSecret: string;
}

const fakes: FakeKeycloak[] = [];
afterEach(async () => {
  while (fakes.length) await fakes.pop()?.stop();
});

/** The service against a fake Keycloak. `heldSecret` is what the service is configured with, when it is not the fake's own. */
async function rig(options: { heldSecret?: string; fakeOptions?: { codeTtlSeconds?: number } } = {}): Promise<Rig> {
  const clientSecret = generateSecret();
  const fake = await startFakeKeycloak({ clientId: CLIENT_ID, clientSecret, redirectUri: REDIRECT_URI, ...options.fakeOptions });
  fakes.push(fake);
  const clock = testClock();
  const flow = createOidcFlow(
    { issuer: fake.issuer, clientId: CLIENT_ID, clientSecret: new Secret(options.heldSecret ?? clientSecret), publicOrigin: ORIGIN },
    { now: clock },
  );
  const built = build({ codeFlow: flow, clock });
  return { fake, app: built.app, store: built.store, clock, clientSecret };
}

function loginCookieOf(res: Pick<Response, "headers">): string {
  const mine = setCookies(res).find((c) => c.startsWith(`${LOGIN_COOKIE_NAME}=`));
  if (!mine) throw new Error("no login cookie was set");
  return mine.split(";")[0] as string;
}

function sessionKeys(store: MemorySessionStore): string[] {
  return store.keys().filter((key) => key.startsWith(SESSION_KEY_PREFIX));
}

function loginKeys(store: MemorySessionStore): string[] {
  return store.keys().filter((key) => key.startsWith(LOGIN_KEY_PREFIX));
}

interface Started {
  res: Response;
  location: URL;
  cookie: string;
}

/** The person follows the sign-in link: the service answers with the provider's address and a login cookie. */
async function start(r: Rig, options: { returnTo?: string; cookie?: string } = {}): Promise<Started> {
  const path = options.returnTo === undefined ? "/session/sign-in" : `/session/sign-in?returnTo=${encodeURIComponent(options.returnTo)}`;
  const req = request(r.app).get(path);
  if (options.cookie) req.set("Cookie", options.cookie);
  const res = await req;
  expect(res.status).toBe(302);
  return { res, location: new URL(res.headers["location"] as string), cookie: loginCookieOf(res) };
}

/** The person signs in at the provider; the provider sends the browser back to the callback. */
function comeBack(r: Rig, started: Started, username = "alex"): string {
  const callback = new URL(r.fake.authorise(started.location.toString(), { username }));
  return `${callback.pathname}${callback.search}`;
}

async function callbackWith(r: Rig, path: string, cookie?: string): Promise<Response> {
  const req = request(r.app).get(path);
  if (cookie) req.set("Cookie", cookie);
  return req;
}

/** The whole round trip, as one browser makes it. */
async function signInFully(r: Rig, options: { returnTo?: string; cookie?: string } = {}): Promise<{ started: Started; callback: Response }> {
  const started = await start(r, options);
  const callback = await callbackWith(r, comeBack(r, started), [started.cookie, options.cookie].filter(Boolean).join("; "));
  return { started, callback };
}

function hasSessionCookie(res: Pick<Response, "headers">): boolean {
  return setCookies(res).some((c) => c.startsWith(`${COOKIE_NAME}=`) && !/^[^=]+=;/.test(c));
}

/** Refused: `403`, the fixed words, no session, no session cookie, the login cookie cleared. */
function expectRefused(r: Rig, res: Response): void {
  expect(res.status).toBe(403);
  expect(res.text).toContain(REFUSED_WORDS);
  expect(hasSessionCookie(res)).toBe(false);
  expect(sessionKeys(r.store)).toEqual([]);
  const login = setCookies(res).find((c) => c.startsWith(`${LOGIN_COOKIE_NAME}=`));
  expect(login, "the login cookie is cleared on every answer to a callback").toMatch(/^[^=]+=;.*(Max-Age=0|Expires=Thu, 01 Jan 1970)/i);
}

/** Every piece of a token a log, a header or a page must not carry: whole, and its three segments. */
function pieces(token: string): string[] {
  return [token, ...token.split(".").filter((p) => p.length >= 16)];
}

function secretsOf(r: Rig): string[] {
  return [
    ...r.fake.issued.flatMap((i) => [...pieces(i.accessToken), ...pieces(i.refreshToken), ...pieces(i.idToken)]),
    ...r.fake.issued.flatMap((i) => [i.accessMarker, i.refreshMarker]),
    r.clientSecret,
    TEST_SESSION_SECRET,
  ].filter((s) => s !== "");
}

/** Throws when any secret is in the text, in any of the forms a proxy or a log could write it. */
function expectNoSecret(r: Rig, text: string, where: string): void {
  for (const secret of secretsOf(r)) {
    for (const form of [secret, encodeURIComponent(secret), Buffer.from(secret).toString("base64"), Buffer.from(secret).toString("base64url")]) {
      if (text.includes(form)) throw new Error(`${where}: a secret (${secret.slice(0, 12)}…) is in what was said`);
    }
  }
  if (/eyJ[A-Za-z0-9_-]{8,}\./.test(text)) throw new Error(`${where}: a token-shaped string is in what was said`);
}

function expectNoSecretIn(r: Rig, res: Pick<Response, "headers" | "text">, where: string): void {
  expectNoSecret(r, everythingIn(res), where);
}

describe("the round trip", () => {
  it("starts at the provider with state, nonce, an S256 challenge and the exact redirect address, and holds the secrets on the server", async () => {
    const r = await rig();
    const captured = captureOutput();
    let started: Started;
    try {
      started = await start(r);
    } finally {
      captured.restore();
    }
    const query = started.location.searchParams;
    expect(started.location.origin + started.location.pathname).toBe(`${r.fake.issuer}/protocol/openid-connect/auth`);
    expect(query.get("response_type")).toBe("code");
    expect(query.get("client_id")).toBe(CLIENT_ID);
    expect(query.get("redirect_uri")).toBe(REDIRECT_URI);
    expect(query.get("scope")).toBe("openid");
    expect(query.get("code_challenge_method")).toBe("S256");
    expect(query.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(query.get("state")).toMatch(/^[A-Za-z0-9_-]{22,}$/);
    expect(query.get("nonce")).toMatch(/^[A-Za-z0-9_-]{22,}$/);
    expect(query.get("client_secret")).toBeNull();

    // The login cookie: signed, opaque, short-lived, and nothing of the flow in it.
    const setCookie = setCookies(started.res).find((c) => c.startsWith(`${LOGIN_COOKIE_NAME}=`)) as string;
    expect(setCookie).toMatch(/;\s*HttpOnly/i);
    expect(setCookie).toMatch(/;\s*Secure/i);
    expect(setCookie).toMatch(/;\s*SameSite=Lax/i);
    expect(setCookie).toMatch(/;\s*Max-Age=600(;|$)/i);
    expect(setCookie).not.toMatch(/;\s*Domain=/i);
    const value = started.cookie.slice(LOGIN_COOKIE_NAME.length + 1);
    expect(value).toMatch(/^[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$/);
    expect(hasSessionCookie(started.res), "no session exists before the callback").toBe(false);
    expect(sessionKeys(r.store)).toEqual([]);

    // The record is on the server under its own prefix, with a limit of ten minutes, and holds the verifier.
    const keys = loginKeys(r.store);
    expect(keys).toHaveLength(1);
    expect(keys[0]).toBe(`${LOGIN_KEY_PREFIX}${value.split(".")[0]}`);
    expect(r.store.ttl(keys[0] as string)).toBe(600);
    const record = JSON.parse((await r.store.get(keys[0] as string)) as string) as Record<string, string>;
    expect(record["state"]).toBe(query.get("state"));
    expect(record["nonce"]).toBe(query.get("nonce"));
    expect(record["verifier"]).toMatch(/^[A-Za-z0-9_-]{43,128}$/);
    // The verifier is the one secret of the start: it is in no response, header, cookie or log.
    expect(everythingIn(started.res)).not.toContain(record["verifier"]);
    expect(captured.text()).not.toContain(record["verifier"]);
    expect(started.cookie).not.toContain(query.get("state") as string);
  });

  it("creates a session at the callback: a new identifier, a cookie that is HttpOnly, Secure and SameSite=Lax, and the token only in the store", async () => {
    const r = await rig();
    // A browser that arrives with a session of its own (a fixation attempt, or an earlier sign-in).
    const first = await signInFully(r);
    const oldCookie = cookieFrom(first.callback);
    const oldId = idFrom(first.callback);
    expect(sessionKeys(r.store)).toEqual([`${SESSION_KEY_PREFIX}${oldId}`]);

    const captured = captureOutput();
    const responses: Response[] = [];
    let second: { started: Started; callback: Response };
    try {
      second = await signInFully(r, { cookie: oldCookie });
      responses.push(second.started.res, second.callback);
      const home = await request(r.app).get("/").set("Cookie", cookieFrom(second.callback));
      responses.push(home);
      expect(home.status).toBe(200);
      expect(home.text).toContain("Name of alex");
      const signOut = await request(r.app)
        .post("/session/sign-out")
        .set("Cookie", cookieFrom(second.callback))
        .type("form")
        .send({ _csrf: csrfFromPage(home.text) });
      responses.push(signOut);
    } finally {
      captured.restore();
    }
    const { callback } = second;
    expect(callback.status).toBe(302);
    expect(callback.headers["location"]).toBe("/");
    const newId = idFrom(callback);
    expect(newId).not.toBe(oldId);
    expect(sessionKeys(r.store), "the session the browser brought is ended, and signed out is gone").toEqual([]);

    const cookie = setCookies(callback).find((c) => c.startsWith(`${COOKIE_NAME}=`)) as string;
    expect(cookie).toMatch(/;\s*HttpOnly/i);
    expect(cookie).toMatch(/;\s*Secure/i);
    expect(cookie).toMatch(/;\s*SameSite=Lax/i);
    expect(cookie).not.toMatch(/;\s*Domain=/i);

    // Nowhere: not a response, a header, a cookie or a log.
    for (const res of responses) expectNoSecretIn(r, res, "a response");
    expectNoSecret(r, captured.text(), "the log");
    expect(responses.flatMap((res) => setCookies(res)).map((c) => (c.split("=")[0] as string))).toSatisfy((names: string[]) =>
      names.every((n) => n === COOKIE_NAME || n === LOGIN_COOKIE_NAME),
    );
  });

  it("keeps the access token as the bearer, with the refresh token, in the server's store", async () => {
    const r = await rig();
    const { callback } = await signInFully(r);
    const issued = r.fake.issued.at(-1)!;
    const raw = await r.store.get(`${SESSION_KEY_PREFIX}${idFrom(callback)}`);
    const stored = (JSON.parse(raw as string) as { auth: Record<string, unknown> }).auth;
    expect(stored["accessToken"]).toBe(issued.accessToken);
    expect(stored["refreshToken"]).toBe(issued.refreshToken);
    expect(stored["subject"]).toBe("sub-alex");
    expect(stored["displayName"]).toBe("Name of alex");
    // The access token is a signed JWT for the Conduit, not an opaque string.
    const payload = JSON.parse(Buffer.from(issued.accessToken.split(".")[1] as string, "base64url").toString("utf8")) as Record<string, unknown>;
    expect(payload["aud"]).toBe(CONDUIT_AUDIENCE);
  });

  it("sends the person on to a returnTo inside the application", async () => {
    const r = await rig();
    const { callback } = await signInFully(r, { returnTo: "/studio/pipelines?open=3#top" });
    expect(callback.status).toBe(302);
    expect(callback.headers["location"]).toBe("/studio/pipelines?open=3#top");
  });

  it.each(["//evil.example", "https://evil.example", "/\\evil", "/\\/evil.example", "javascript:alert(1)", "/\t/evil.example", "/\n/evil.example", "evil", "", "/a\\b"])(
    "a returnTo that leaves the application is dropped to the home page: %j",
    async (returnTo) => {
      const r = await rig();
      const { callback } = await signInFully(r, { returnTo });
      expect(callback.status).toBe(302);
      expect(callback.headers["location"]).toBe("/");
    },
  );

  it("the session key lives no longer than the provider's session, and no longer than the idle hour", async () => {
    const r = await rig();
    const { callback } = await signInFully(r);
    // The fake's refresh token lasts 1800 seconds: the provider's own session ends then.
    expect(r.store.ttl(`${SESSION_KEY_PREFIX}${idFrom(callback)}`)).toBe(1800);

    const r2 = await rig();
    r2.fake.refreshExpiresIn = undefined;
    const second = await signInFully(r2);
    expect(r2.store.ttl(`${SESSION_KEY_PREFIX}${idFrom(second.callback)}`), "no word of the provider's session: the idle hour").toBe(3600);
  });
});

describe("a refused sign-in changes nothing and says so in fixed words", () => {
  it("a state that is not the flow's own is refused, and the provider is not asked", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started).replace(/state=[^&]+/, "state=not-the-flows-own");
    const res = await callbackWith(r, path, started.cookie);
    expectRefused(r, res);
    expect(r.fake.tokenCalls).toBe(0);
    expect(loginKeys(r.store), "the record is gone once read").toEqual([]);
  });

  it("a state from an earlier sign-in is refused", async () => {
    const r = await rig();
    const earlier = await start(r);
    const earlierPath = comeBack(r, earlier);
    const ok = await callbackWith(r, earlierPath, earlier.cookie);
    expect(ok.status).toBe(302);
    const calls = r.fake.tokenCalls;
    const later = await start(r);
    const res = await callbackWith(r, earlierPath, later.cookie);
    // The earlier session stays; no second one is made.
    expect(res.status).toBe(403);
    expect(res.text).toContain(REFUSED_WORDS);
    expect(hasSessionCookie(res)).toBe(false);
    expect(sessionKeys(r.store)).toHaveLength(1);
    expect(r.fake.tokenCalls).toBe(calls);
  });

  it("no login cookie is refused, and the provider is not asked", async () => {
    const r = await rig();
    const started = await start(r);
    const res = await callbackWith(r, comeBack(r, started));
    expectRefused(r, res);
    expect(r.fake.tokenCalls).toBe(0);
  });

  it("a login cookie whose signature is not ours is refused, and so is one for a record that is not there", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started);
    const [id] = started.cookie.slice(LOGIN_COOKIE_NAME.length + 1).split(".") as [string];
    const forged = `${LOGIN_COOKIE_NAME}=${id}.${"A".repeat(43)}`;
    expectRefused(r, await callbackWith(r, path, forged));
    const stranger = `${LOGIN_COOKIE_NAME}=${"B".repeat(43)}.${"A".repeat(43)}`;
    expectRefused(r, await callbackWith(r, path, stranger));
    expect(r.fake.tokenCalls).toBe(0);
    expect(loginKeys(r.store), "a forged cookie reads nothing, and so burns nothing").toHaveLength(1);
  });

  it("a login cookie from another browser is refused", async () => {
    const r = await rig();
    const mine = await start(r);
    const theirs = await start(r);
    const res = await callbackWith(r, comeBack(r, mine), theirs.cookie);
    expectRefused(r, res);
    expect(r.fake.tokenCalls).toBe(0);
  });

  it("a second use of the same callback is refused, and makes no second session", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started);
    const first = await callbackWith(r, path, started.cookie);
    expect(first.status).toBe(302);
    expect(sessionKeys(r.store)).toHaveLength(1);
    const second = await callbackWith(r, path, started.cookie);
    expect(second.status).toBe(403);
    expect(second.text).toContain(REFUSED_WORDS);
    expect(hasSessionCookie(second)).toBe(false);
    expect(sessionKeys(r.store)).toHaveLength(1);
    expect(r.fake.tokenCalls, "the provider was asked once").toBe(1);
  });

  it("two callbacks at once let one through", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started);
    const both = await Promise.all([callbackWith(r, path, started.cookie), callbackWith(r, path, started.cookie)]);
    expect(both.map((res) => res.status).sort()).toEqual([302, 403]);
    expect(sessionKeys(r.store)).toHaveLength(1);
    expect(r.fake.tokenCalls).toBe(1);
  });

  it("a login record is good for ten minutes and no longer", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started);
    r.clock.advance(601);
    const res = await callbackWith(r, path, started.cookie);
    expectRefused(r, res);
    expect(r.fake.tokenCalls).toBe(0);
  });

  it("a callback with no code is refused, and the provider is not asked", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started).replace(/code=[^&]+&?/, "");
    expectRefused(r, await callbackWith(r, path, started.cookie));
    expect(r.fake.tokenCalls).toBe(0);
  });

  it("a callback that names another issuer is refused, and the provider is not asked", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started).replace(/iss=[^&]+/, `iss=${encodeURIComponent("https://evil.example/realms/osprey")}`);
    expectRefused(r, await callbackWith(r, path, started.cookie));
    expect(r.fake.tokenCalls).toBe(0);
  });

  it("the provider's own error is refused in fixed words, never in the provider's", async () => {
    const r = await rig();
    const started = await start(r);
    const words = `PROVIDER-WORDS-${generateSecret(12)}`;
    const callback = new URL(comeBack(r, started), ORIGIN);
    const state = callback.searchParams.get("state") as string;
    const path = `/session/callback?${new URLSearchParams({ error: "access_denied", error_description: words, state, iss: r.fake.issuer }).toString()}`;
    const captured = captureOutput();
    let res: Response;
    try {
      res = await callbackWith(r, path, started.cookie);
    } finally {
      captured.restore();
    }
    expectRefused(r, res);
    expect(everythingIn(res)).not.toContain(words);
    expect(everythingIn(res)).not.toContain("access_denied");
    expect(captured.text()).not.toContain(words);
    expect(r.fake.tokenCalls).toBe(0);
    expect(loginKeys(r.store)).toEqual([]);
  });

  it.each([
    ["an issuer that is not the realm's", { iss: "https://evil.example/realms/osprey" }],
    ["an audience that is not this client", { aud: "another-client" }],
    ["an expiry in the past", { exp: Math.floor(Date.now() / 1000) - 3600 }],
  ])("an ID token that does not verify is refused: %s", async (_name, overrides) => {
    const r = await rig();
    r.fake.claimOverrides = overrides;
    const captured = captureOutput();
    let res: Response;
    try {
      const started = await start(r);
      res = await callbackWith(r, comeBack(r, started), started.cookie);
    } finally {
      captured.restore();
    }
    expectRefused(r, res);
    expect(r.fake.tokenCalls, "it was the token that was wrong, so the provider was asked").toBe(1);
    expectNoSecretIn(r, res, "the refusal");
    expectNoSecret(r, captured.text(), "the log");
  });

  it("an ID token signed by another key is refused", async () => {
    const r = await rig();
    r.fake.signWithOtherKey = true;
    const started = await start(r);
    const res = await callbackWith(r, comeBack(r, started), started.cookie);
    expectRefused(r, res);
    expect(r.fake.tokenCalls).toBe(1);
  });

  it("an answer with no ID token is refused", async () => {
    const r = await rig();
    r.fake.omitIdToken = true;
    const started = await start(r);
    expectRefused(r, await callbackWith(r, comeBack(r, started), started.cookie));
  });

  it("a nonce that is not the flow's own is refused", async () => {
    const r = await rig();
    r.fake.claimOverrides = { nonce: "a-nonce-from-another-flow" };
    const started = await start(r);
    expectRefused(r, await callbackWith(r, comeBack(r, started), started.cookie));
    expect(r.fake.tokenCalls).toBe(1);
  });

  it("a wrong client secret is a refusal: the provider says no, and the words are ours", async () => {
    const r = await rig({ heldSecret: generateSecret() });
    const captured = captureOutput();
    let res: Response;
    try {
      const started = await start(r);
      res = await callbackWith(r, comeBack(r, started), started.cookie);
    } finally {
      captured.restore();
    }
    expectRefused(r, res);
    expect(r.fake.tokenCalls).toBe(1);
    expect(everythingIn(res)).not.toMatch(/invalid_client|Invalid client credentials/i);
    expectNoSecret(r, captured.text(), "the log");
  });

  it("an expired code is refused, and the words are ours", async () => {
    const r = await rig({ fakeOptions: { codeTtlSeconds: 30 } });
    const started = await start(r);
    const path = comeBack(r, started);
    r.fake.advance(31);
    const res = await callbackWith(r, path, started.cookie);
    expectRefused(r, res);
    expect(r.fake.tokenCalls).toBe(1);
    expect(everythingIn(res)).not.toMatch(/invalid_grant|Code not valid/i);
  });
});

describe("an unreachable provider is not an access refusal (ADR-044)", () => {
  it("is a 503 at the start, with no cookie and no record", async () => {
    const r = await rig();
    await r.fake.stop();
    fakes.pop();
    const res = await request(r.app).get("/session/sign-in");
    expect(res.status).toBe(503);
    expect(res.text).toContain(UNAVAILABLE_WORDS);
    expect(setCookies(res)).toEqual([]);
    expect(r.store.keys()).toEqual([]);
  });

  it("is a 503 at the callback, with no session", async () => {
    const r = await rig();
    const started = await start(r);
    const path = comeBack(r, started);
    await r.fake.stop();
    fakes.pop();
    const res = await callbackWith(r, path, started.cookie);
    expect(res.status).toBe(503);
    expect(res.text).toContain(UNAVAILABLE_WORDS);
    expect(hasSessionCookie(res)).toBe(false);
    expect(sessionKeys(r.store)).toEqual([]);
  });

  it("is a 503 when the token address answers with a server error", async () => {
    const r = await rig();
    r.fake.tokenStatus = 500;
    const started = await start(r);
    const res = await callbackWith(r, comeBack(r, started), started.cookie);
    expect(res.status).toBe(503);
    expect(res.text).toContain(UNAVAILABLE_WORDS);
    expect(sessionKeys(r.store)).toEqual([]);
  });
});

describe("sign-out (local, in this slice)", () => {
  it("destroys the session and the cookie, and the anti-forgery check still guards it", async () => {
    const r = await rig();
    const { callback } = await signInFully(r);
    const cookie = cookieFrom(callback);
    const home = await request(r.app).get("/").set("Cookie", cookie);
    const csrf = csrfFromPage(home.text);

    const refused = await request(r.app).post("/session/sign-out").set("Cookie", cookie).type("form").send({});
    expect(refused.status).toBe(403);
    expect(sessionKeys(r.store)).toHaveLength(1);

    const out = await request(r.app).post("/session/sign-out").set("Cookie", cookie).type("form").send({ _csrf: csrf });
    expect(out.status).toBe(303);
    expect(sessionKeys(r.store)).toEqual([]);
    expect(setCookies(out).find((c) => c.startsWith(`${COOKIE_NAME}=`))).toMatch(/^[^=]+=;.*(Max-Age=0|Expires=Thu, 01 Jan 1970)/i);

    const after = await request(r.app).get("/").set("Cookie", cookie);
    expect(after.status).toBe(302);
    expect(after.headers["location"]).toBe("/session/sign-in");
  });
});

describe("the fake refuses what Keycloak refuses (rule 15)", () => {
  async function codeFor(r: Rig, mutate?: (url: URL) => void): Promise<{ code: string; verifierOf: Started }> {
    const started = await start(r);
    if (mutate) mutate(started.location);
    const callback = new URL(r.fake.authorise(started.location.toString()));
    return { code: callback.searchParams.get("code") as string, verifierOf: started };
  }

  async function exchange(r: Rig, form: Record<string, string>, headers: Record<string, string> = {}): Promise<{ status: number; body: Record<string, unknown> }> {
    const res = await fetch(`${r.fake.issuer}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", ...headers },
      body: new URLSearchParams(form),
    });
    return { status: res.status, body: (await res.json()) as Record<string, unknown> };
  }

  /** The verifier the service stored for a started flow, read from the store as a test may. */
  async function verifierOf(r: Rig, started: Started): Promise<string> {
    const id = started.cookie.slice(LOGIN_COOKIE_NAME.length + 1).split(".")[0] as string;
    return (JSON.parse((await r.store.get(`${LOGIN_KEY_PREFIX}${id}`)) as string) as { verifier: string }).verifier;
  }

  const base = (r: Rig, code: string, verifier: string): Record<string, string> => ({
    grant_type: "authorization_code",
    code,
    redirect_uri: REDIRECT_URI,
    code_verifier: verifier,
    client_id: CLIENT_ID,
  });

  it("authenticates the client: a wrong or missing secret is 401 invalid_client, by form or by Basic header", async () => {
    const r = await rig();
    const { code, verifierOf: started } = await codeFor(r);
    const verifier = await verifierOf(r, started);
    for (const secret of [generateSecret(), ""]) {
      const wrong = await exchange(r, { ...base(r, code, verifier), client_secret: secret });
      expect(wrong.status).toBe(401);
      expect(wrong.body["error"]).toBe("invalid_client");
    }
    const none = await exchange(r, base(r, code, verifier));
    expect(none.status).toBe(401);
    const basic = await exchange(r, { ...base(r, code, verifier), client_id: "" }, { Authorization: `Basic ${Buffer.from(`${CLIENT_ID}:${generateSecret()}`).toString("base64")}` });
    expect(basic.status).toBe(401);
    // The right secret, by either way, is let in (and the code was not burned by the refusals above).
    const good = await exchange(r, { ...base(r, code, verifier), client_secret: r.clientSecret });
    expect(good.status).toBe(200);
    const access = JSON.parse(Buffer.from((good.body["access_token"] as string).split(".")[1] as string, "base64url").toString("utf8")) as Record<string, unknown>;
    expect(access["aud"]).toBe(CONDUIT_AUDIENCE);
  });

  it("a code is single use even when the first try was wrong, and a wrong or missing verifier is refused", async () => {
    const r = await rig();
    const { code, verifierOf: started } = await codeFor(r);
    const verifier = await verifierOf(r, started);
    const form = { ...base(r, code, verifier), client_secret: r.clientSecret };
    const wrong = await exchange(r, { ...form, code_verifier: "w".repeat(43) });
    expect(wrong.status).toBe(400);
    expect(wrong.body["error"]).toBe("invalid_grant");
    const again = await exchange(r, form);
    expect(again.status, "the right verifier after a wrong one: the code is already spent").toBe(400);

    const second = await codeFor(r);
    const missing = await exchange(r, { ...base(r, second.code, "x"), code_verifier: "", client_secret: r.clientSecret });
    expect(missing.status).toBe(400);
  });

  it("a code expires, and a wrong redirect address is refused at the token address", async () => {
    const r = await rig({ fakeOptions: { codeTtlSeconds: 30 } });
    const stale = await codeFor(r);
    r.fake.advance(31);
    const expired = await exchange(r, { ...base(r, stale.code, await verifierOf(r, stale.verifierOf)), client_secret: r.clientSecret });
    expect(expired.status).toBe(400);
    expect(expired.body["error"]).toBe("invalid_grant");

    const fresh = await codeFor(r);
    const wrongUri = await exchange(r, {
      ...base(r, fresh.code, await verifierOf(r, fresh.verifierOf)),
      redirect_uri: `${ORIGIN}/elsewhere`,
      client_secret: r.clientSecret,
    });
    expect(wrongUri.status).toBe(400);
  });

  it("refuses at the authorisation address: a wrong redirect address, a plain challenge, an unknown client, no state", async () => {
    const r = await rig();
    const started = await start(r);
    const attempt = (change: (q: URLSearchParams) => void): string => {
      const url = new URL(started.location.toString());
      change(url.searchParams);
      return url.toString();
    };
    expect(() => r.fake.authorise(attempt((q) => q.set("redirect_uri", `${ORIGIN}/elsewhere`)))).toThrow(AuthorisationRefused);
    expect(() => r.fake.authorise(attempt((q) => q.set("code_challenge_method", "plain")))).toThrow(AuthorisationRefused);
    expect(() => r.fake.authorise(attempt((q) => q.set("client_id", "someone-else")))).toThrow(AuthorisationRefused);
    expect(() => r.fake.authorise(attempt((q) => q.delete("state")))).toThrow(AuthorisationRefused);
    expect(() => r.fake.authorise(attempt((q) => q.delete("code_challenge")))).toThrow(AuthorisationRefused);
  });
});

describe("settings", () => {
  const issuer = "https://id.example.org/realms/osprey";
  const base = { OSPREY_PAGES_SESSION_SECRET: generateSecret() } as const;
  const secret = generateSecret();

  it("unset, all three: sign-in is not configured", () => {
    expect(loadConfig({ ...base }).oidc).toBeUndefined();
  });

  it("with the issuer, the secret and the origin: configured, the client id defaulting to osprey-pages", () => {
    const config = loadConfig({
      ...base,
      OSPREY_PAGES_OIDC_ISSUER: issuer,
      OSPREY_PAGES_CLIENT_SECRET: secret,
      OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN,
    });
    expect(config.oidc?.issuer).toBe(issuer);
    expect(config.oidc?.clientId).toBe("osprey-pages");
    expect(config.oidc?.clientSecret.reveal()).toBe(secret);
    expect(config.oidc?.publicOrigin).toBe(ORIGIN);
    expect(loadConfig({ ...base, OSPREY_PAGES_OIDC_ISSUER: issuer, OSPREY_PAGES_CLIENT_SECRET: secret, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN, OSPREY_PAGES_CLIENT_ID: "other" }).oidc?.clientId).toBe("other");
  });

  it.each([
    ["only the issuer", { OSPREY_PAGES_OIDC_ISSUER: issuer, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN }, "OSPREY_PAGES_CLIENT_SECRET"],
    ["only the secret", { OSPREY_PAGES_CLIENT_SECRET: secret, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN }, "OSPREY_PAGES_OIDC_ISSUER"],
    ["only the client id", { OSPREY_PAGES_CLIENT_ID: "osprey-pages" }, "OSPREY_PAGES_OIDC_ISSUER"],
    ["no origin to name the callback by", { OSPREY_PAGES_OIDC_ISSUER: issuer, OSPREY_PAGES_CLIENT_SECRET: secret }, "OSPREY_PAGES_PUBLIC_ORIGIN"],
    ["an empty secret", { OSPREY_PAGES_OIDC_ISSUER: issuer, OSPREY_PAGES_CLIENT_SECRET: "", OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN }, "OSPREY_PAGES_CLIENT_SECRET"],
  ])("some set and not all: %s, refused naming what is missing", (_name, env, missing) => {
    expect(() => loadConfig({ ...base, ...env })).toThrow(missing);
    try {
      loadConfig({ ...base, ...env });
    } catch (error) {
      expect(String(error)).not.toContain(secret);
    }
  });

  it("a client secret under 32 characters is refused, naming the setting and the rule, never the value", () => {
    const short = generateSecret(31);
    let said = "";
    try {
      loadConfig({ ...base, OSPREY_PAGES_OIDC_ISSUER: issuer, OSPREY_PAGES_CLIENT_SECRET: short, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN });
    } catch (error) {
      said = String(error);
    }
    expect(said).toContain("OSPREY_PAGES_CLIENT_SECRET");
    expect(said).toMatch(/at least 32 characters/);
    expect(said).not.toContain(short);
    expect(said).not.toMatch(/\b31\b/);
  });

  it.each([
    ["https", "https://id.example.org/realms/osprey", true],
    ["http on 127.0.0.1", "http://127.0.0.1:8081/realms/osprey", true],
    ["http on localhost", "http://localhost:8081/realms/osprey", true],
    ["http on a name that is not loopback", "http://id.example.org/realms/osprey", false],
    ["http on an address that is not loopback", "http://10.0.0.5/realms/osprey", false],
    ["another scheme", "ftp://id.example.org/realms/osprey", false],
    ["not an address", "id.example.org", false],
    ["a user name and password", "https://user:pw-in-the-address@id.example.org/realms/osprey", false],
    ["a query", "https://id.example.org/realms/osprey?x=1", false],
  ])("the issuer: %s", (_name, value, accepted) => {
    const env = { ...base, OSPREY_PAGES_OIDC_ISSUER: value, OSPREY_PAGES_CLIENT_SECRET: secret, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN };
    if (accepted) {
      expect(loadConfig(env).oidc?.issuer).toBe(value);
    } else {
      expect(() => loadConfig(env)).toThrow(/OSPREY_PAGES_OIDC_ISSUER/);
      try {
        loadConfig(env);
      } catch (error) {
        expect(String(error)).not.toContain("pw-in-the-address");
      }
    }
  });

  it("the client secret is redacted wherever it could be printed", () => {
    const config = loadConfig({ ...base, OSPREY_PAGES_OIDC_ISSUER: issuer, OSPREY_PAGES_CLIENT_SECRET: secret, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN });
    for (const printed of [String(config.oidc?.clientSecret), `${config.oidc?.clientSecret as Secret}`, JSON.stringify(config), inspect(config, { depth: 6 })]) {
      expect(printed).not.toContain(secret);
    }
  });

  describe("through main, as the service starts", () => {
    const running: Running[] = [];
    afterEach(async () => {
      while (running.length) await running.pop()?.stop();
    });

    async function startWith(env: NodeJS.ProcessEnv) {
      const errors: string[] = [];
      const logs: string[] = [];
      const exits: number[] = [];
      const captured = captureOutput();
      let result: Running | undefined;
      try {
        result = await main(
          { OSPREY_PAGES_PORT: "0", OSPREY_PAGES_SESSION_SECRET: base.OSPREY_PAGES_SESSION_SECRET, ...env },
          { log: (m) => void logs.push(m), error: (m) => void errors.push(m), exit: (c) => void exits.push(c) },
          { store: new MemorySessionStore(), host: "127.0.0.1" },
        );
      } finally {
        captured.restore();
      }
      if (result) running.push(result);
      return { result, errors, logs, exits, output: captured.text() };
    }

    it("with none of the three set, sign-in answers 503, as it did before", async () => {
      const { result } = await startWith({});
      expect(result).toBeDefined();
      const res = await fetch(`http://127.0.0.1:${result?.port}/session/sign-in`, { redirect: "manual" });
      expect(res.status).toBe(503);
      expect(await res.text()).toContain(UNAVAILABLE_WORDS);
      const callback = await fetch(`http://127.0.0.1:${result?.port}/session/callback?code=x&state=y`, { redirect: "manual" });
      expect(callback.status).toBe(503);
    });

    it("with some set and not all, refuses to start in words naming the missing setting, and prints no value", async () => {
      const { result, errors, logs, exits, output } = await startWith({ OSPREY_PAGES_OIDC_ISSUER: issuer, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN });
      expect(result).toBeUndefined();
      expect(exits).toEqual([1]);
      expect(errors.join("\n")).toContain("OSPREY_PAGES_CLIENT_SECRET");
      expect(logs.join("\n")).not.toMatch(/listening/);
      for (const text of [errors.join("\n"), logs.join("\n"), output]) {
        expect(text).not.toContain(base.OSPREY_PAGES_SESSION_SECRET);
        expect(text).not.toContain(secret);
      }
    });

    it("with a short client secret, refuses to start without printing it", async () => {
      const short = generateSecret(20);
      const { result, errors, exits, output } = await startWith({
        OSPREY_PAGES_OIDC_ISSUER: issuer,
        OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN,
        OSPREY_PAGES_CLIENT_SECRET: short,
      });
      expect(result).toBeUndefined();
      expect(exits).toEqual([1]);
      expect(errors.join("\n")).toMatch(/OSPREY_PAGES_CLIENT_SECRET must be at least 32 characters/);
      expect(errors.join("\n") + output).not.toContain(short);
    });

    it("with all set, starts, and the start redirects to the provider's address with the secret nowhere", async () => {
      const clientSecret = generateSecret();
      const fake = await startFakeKeycloak({ clientId: CLIENT_ID, clientSecret, redirectUri: REDIRECT_URI });
      fakes.push(fake);
      const { result, errors, logs, output } = await startWith({
        OSPREY_PAGES_OIDC_ISSUER: fake.issuer,
        OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN,
        OSPREY_PAGES_CLIENT_SECRET: clientSecret,
      });
      expect(result).toBeDefined();
      const res = await fetch(`http://127.0.0.1:${result?.port}/session/sign-in`, { redirect: "manual", headers: { "X-Forwarded-Proto": "https" } });
      expect(res.status).toBe(302);
      const location = new URL(res.headers.get("location") as string);
      expect(`${location.origin}${location.pathname}`).toBe(`${fake.issuer}/protocol/openid-connect/auth`);
      expect(location.searchParams.get("redirect_uri")).toBe(REDIRECT_URI);
      const everything = `${errors.join("\n")}${logs.join("\n")}${output}${[...res.headers.entries()].join("\n")}${location.toString()}`;
      expect(everything).not.toContain(clientSecret);
      expect(everything).not.toContain(base.OSPREY_PAGES_SESSION_SECRET);
    });
  });
});
