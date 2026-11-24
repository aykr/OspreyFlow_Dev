/**
 * Slice PL9b, acceptance, second half: signing out ends the person's session at the identity provider too, and the provider's
 * own logout ends the page service's sessions (ADR-152 decision 4, ADR-050 Amendment 4 point 4; the owner's rule: "signed out"
 * in the pages must not leave the person signed in at the provider).
 *
 * The identity provider is the fake Keycloak (`test/support/fakeKeycloak.ts`), which REFUSES what Keycloak refuses (rule 15):
 * its end-session address ends a session only when given a valid `id_token_hint` (with none it shows a confirmation page and
 * ends nothing), refuses a `post_logout_redirect_uri` that is not registered exactly, and signs logout tokens as Keycloak does.
 * Every case that says "ended" reads the provider's own record of the session, not the service's.
 *
 * Which test fails if the behaviour is wrong (rule 12):
 * - a sign-out that ends only the pages session: "ends the pages session first, then the provider's" (the provider's session
 *   is still alive, and its refresh token still works);
 * - a sign-out with no hint, or a return address that is not the registered one: the same case (the fake ends nothing);
 * - a sign-out that leaves the pages session alive when the provider cannot be reached: "a provider that cannot be reached ...";
 * - the ID token in the sign-out form's own answer (a redirect after a form post is held to `form-action 'self'` by a
 *   browser): "the first answer carries no token ...";
 * - a back-channel route that ends sessions on a token that fails a check: the table "a logout token that fails one check ends
 *   nothing", one plant for each check the brief names, each followed by the genuine token ending the session (so the route,
 *   and not a broken fixture, is what refused);
 * - a replay: "a token already used is refused" (sequential, and two at once);
 * - a logout that ends more than it names (another person, another provider session) or less (every page session of one
 *   provider session; every session of a subject): "a valid token ends the sessions it names and no others";
 * - who may call the route: "who may call the route".
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { SignJWT, generateKeyPair } from "jose";

import { IdentityProviderUnavailable } from "../../server/identity.js";
import { IDP_INDEX_PREFIX, SESSION_KEY_PREFIX, STAGED_KEY_PREFIX } from "../../server/sessionStore.js";
import { captureOutput } from "../support/capture.js";
import { BACKCHANNEL_EVENT } from "../support/fakeKeycloak.js";
import type { LogoutTokenPlant } from "../support/fakeKeycloak.js";
import { everythingIn, request, setCookies } from "../support/http.js";
import { CLIENT_ID, ORIGIN, clearsSessionCookie, csrfOf, expectNoSecret, rig, signInAs, stopRigs } from "../support/providerRig.js";
import type { Person, Rig } from "../support/providerRig.js";

vi.setConfig({ testTimeout: 30_000 });
afterEach(stopRigs);

const REFUSAL = { status: 400, text: "Refused" };
/** Where Keycloak sends its logout token: written here as the realm client names it (`tests/harness/test_realm_pages_client.py` pins it to the service's own route). */
const BACKCHANNEL_LOGOUT_PATH = "/session/back-channel-logout";

function sessionKeys(r: Rig): string[] {
  return r.store.keys().filter((key) => key.startsWith(SESSION_KEY_PREFIX));
}

function indexKeys(r: Rig): string[] {
  return r.store.keys().filter((key) => key.startsWith(IDP_INDEX_PREFIX));
}

/** True while the person's cookie still gets their home page. */
async function alive(r: Rig, person: Pick<Person, "cookie">): Promise<boolean> {
  return (await request(r.app).get("/").set("Cookie", person.cookie)).status === 200;
}

function deliver(r: Rig, token: string): ReturnType<ReturnType<typeof request>["post"]> {
  return request(r.app).post(BACKCHANNEL_LOGOUT_PATH).type("form").send({ logout_token: token });
}

describe("sign-out at the provider", () => {
  it("ends the pages session first, then the provider's, with the hint and the registered return address", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    const idToken = r.fake.issued[person.issuedAt]!.idToken;
    const refreshToken = r.fake.issued[person.issuedAt]!.refreshToken;

    const out = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: csrf });
    expect(out.status).toBe(303);
    // The pages session is ended before the provider is asked for anything.
    expect(sessionKeys(r)).toEqual([]);
    expect(clearsSessionCookie(out)).toBe(true);
    expect(r.fake.endSessionRequests).toEqual([]);
    expect(r.fake.sessions.get(person.sid)?.ended).toBe(false);

    // The person's browser follows the answer, with no cookie (the session is gone), to the provider's end-session address.
    const hop = await request(r.app).get(out.headers["location"] as string);
    expect(hop.status).toBe(302);
    expect(hop.headers["cache-control"]).toBe("no-store");
    const target = new URL(hop.headers["location"] as string);
    expect(target.origin + target.pathname).toBe(`${r.fake.issuer}/protocol/openid-connect/logout`);
    expect(target.searchParams.get("id_token_hint")).toBe(idToken);
    expect(target.searchParams.get("post_logout_redirect_uri")).toBe(`${ORIGIN}/`);
    expect(target.searchParams.get("client_id")).toBe(CLIENT_ID);

    const end = await fetch(target, { redirect: "manual" });
    expect(end.status).toBe(302);
    expect(end.headers.get("location")).toBe(`${ORIGIN}/`);
    // The provider's own record: the session is ended there, and its refresh token no longer works.
    expect(r.fake.sessions.get(person.sid)?.ended, "the person is signed out at the provider").toBe(true);
    const again = await fetch(`${r.fake.issuer}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: refreshToken, client_id: CLIENT_ID, client_secret: r.clientSecret }),
    });
    expect(again.status).toBe(400);
    expect(((await again.json()) as { error_description: string }).error_description).toBe("Session not active");
    // Ending the pages session left nothing of it in the store, not even its index.
    expect(indexKeys(r)).toEqual([]);
  });

  it("the first answer carries no token: the ID token is only in the last hop, a plain navigation", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    const captured = captureOutput();
    let out, hop;
    try {
      out = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: csrf });
      hop = await request(r.app).get(out.headers["location"] as string);
    } finally {
      captured.restore();
    }
    // A redirect that follows a form post is held to the page's `form-action 'self'` by a browser: the first answer stays on
    // this origin and holds only an opaque, single-use address.
    expect(out.headers["location"]).toMatch(/^\/session\/[a-z-]+(\/[a-z-]+)*\?[A-Za-z0-9_=-]+$/);
    expectNoSecret(r, everythingIn(out), "the sign-out answer");
    expectNoSecret(r, captured.text(), "the console");
    expectNoSecret(r, r.log.join("\n"), "the log");
    // The last hop is the one place the hint is; it is never cached or stored by a proxy.
    expect(everythingIn(hop)).toContain("id_token_hint=");
    expect(hop.headers["cache-control"]).toBe("no-store");
    expect(hop.headers["referrer-policy"]).toBe("same-origin");
  });

  it("the hand-off address is single use, and says nothing to anyone it is not for", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    const out = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: csrf });
    const address = out.headers["location"] as string;
    expect((await request(r.app).get(address)).headers["location"]).toContain("/protocol/openid-connect/logout");
    const second = await request(r.app).get(address);
    expect(second.status).toBe(302);
    expect(second.headers["location"], "a second use finds nothing, and goes home").toBe("/");
    const made = await request(r.app).get("/session/sign-out/provider?r=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQ");
    expect(made.headers["location"]).toBe("/");
    // The same answer without a query, and in the same shape for anything else.
    expect((await request(r.app).get(address.split("?")[0] as string)).headers["location"]).toBe("/");
    expect(everythingIn(second)).not.toContain("id_token_hint");
  });

  it("a provider that cannot be reached leaves no pages session", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    await r.fake.stop();
    const out = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: csrf });
    expect(out.status).toBe(303);
    expect(out.headers["location"]).toMatch(/^\//);
    expect(sessionKeys(r)).toEqual([]);
    expect(clearsSessionCookie(out)).toBe(true);
    expect(indexKeys(r)).toEqual([]);
    expect((await request(r.app).get("/v1/me").set("Cookie", person.cookie)).status).toBe(401);
  });

  it("a provider whose end-session address cannot be had still ends the pages session, in fixed words", async () => {
    const marker = `PROVIDER-WORDS-${Math.random().toString(36).slice(2)}`;
    const r = await rig({
      wrapFlow: (flow) => ({
        ...flow,
        endSessionUrl: () => Promise.reject(new IdentityProviderUnavailable(marker)),
      }),
    });
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    const out = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: csrf });
    expect(out.status).toBe(303);
    expect(out.headers["location"]).toBe("/");
    expect(sessionKeys(r)).toEqual([]);
    expect(clearsSessionCookie(out)).toBe(true);
    const said = r.log.filter((line) => line.startsWith("pages: sign-out: "));
    expect(said).toHaveLength(1);
    expect(r.log.join("\n")).not.toContain(marker);
  });

  it("a session that holds no ID token sends the client and the return address, and no hint", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    const key = `${SESSION_KEY_PREFIX}${person.id}`;
    const parsed = JSON.parse((await r.store.get(key)) as string) as { auth: Record<string, unknown> };
    delete parsed.auth["idToken"];
    await r.store.set(key, JSON.stringify(parsed), 600);
    const out = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: csrf });
    const hop = await request(r.app).get(out.headers["location"] as string);
    const target = new URL(hop.headers["location"] as string);
    expect(target.searchParams.has("id_token_hint")).toBe(false);
    expect(target.searchParams.get("client_id")).toBe(CLIENT_ID);
    expect(target.searchParams.get("post_logout_redirect_uri")).toBe(`${ORIGIN}/`);
    expect(sessionKeys(r)).toEqual([]);
  });

  it("who may sign out: only a session with the anti-forgery token; anyone else ends nothing and reaches no provider", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    const noToken = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({});
    expect(noToken.status).toBe(403);
    const wrong = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: `${csrf}x` });
    expect(wrong.status).toBe(403);
    const noSession = await request(r.app).post("/session/sign-out").type("form").send({ _csrf: csrf });
    expect(noSession.status).toBe(403);
    expect(await alive(r, person)).toBe(true);
    expect(r.fake.endSessionRequests).toEqual([]);
    expect(r.fake.sessions.get(person.sid)?.ended).toBe(false);
    // A GET never signs anyone out.
    expect((await request(r.app).get("/session/sign-out").set("Cookie", person.cookie)).status).toBe(404);
    expect(await alive(r, person)).toBe(true);
  });
});

describe("the fake provider's end-session address refuses what Keycloak refuses (rule 15)", () => {
  it("ends a session only for a valid hint and a registered return address", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const issued = r.fake.issued[person.issuedAt]!;
    const base = `${r.fake.issuer}/protocol/openid-connect/logout`;
    const go = (query: Record<string, string>): Promise<Response> => fetch(`${base}?${new URLSearchParams(query)}`, { redirect: "manual" });
    const ended = (): boolean | undefined => r.fake.sessions.get(person.sid)?.ended;

    // No hint: a confirmation page, and nothing ended.
    expect((await go({ client_id: CLIENT_ID, post_logout_redirect_uri: `${ORIGIN}/` })).status).toBe(200);
    expect(ended()).toBe(false);
    // A return address that is not the registered one, exactly: refused, and nothing ended.
    for (const wrong of [ORIGIN, `${ORIGIN}/elsewhere`, "https://evil.example/", `${ORIGIN}//`]) {
      expect((await go({ id_token_hint: issued.idToken, post_logout_redirect_uri: wrong })).status, wrong).toBe(400);
      expect(ended()).toBe(false);
    }
    // A hint the realm did not sign: refused.
    const { privateKey } = await generateKeyPair("RS256", { modulusLength: 2048 });
    const forged = await new SignJWT({ iss: r.fake.issuer, aud: CLIENT_ID, azp: CLIENT_ID, sid: person.sid, sub: "sub-alex" })
      .setProtectedHeader({ alg: "RS256", kid: "fake-keycloak-key-1" })
      .sign(privateKey);
    expect((await go({ id_token_hint: forged })).status).toBe(400);
    expect(ended()).toBe(false);
    // A hint for another client: refused.
    expect((await go({ id_token_hint: issued.idToken, client_id: "another-client" })).status).toBe(400);
    expect(ended()).toBe(false);
    // The genuine request ends it.
    expect((await go({ id_token_hint: issued.idToken, client_id: CLIENT_ID, post_logout_redirect_uri: `${ORIGIN}/` })).status).toBe(302);
    expect(ended()).toBe(true);
  });
});

/** Three people in two pages sessions of one person and one of another: what a logout must tell apart. */
async function world(): Promise<{ r: Rig; a: Person; b: Person; c: Person }> {
  const r = await rig({ fake: { users: ["alex", "blake"] } });
  const a = await signInAs(r, { username: "alex" });
  const b = await signInAs(r, { username: "alex" }); // the same person, another browser: another provider session
  const c = await signInAs(r, { username: "blake" });
  return { r, a, b, c };
}

describe("back-channel logout: a valid token ends the sessions it names and no others", () => {
  it("names one provider session by `sid`: that session ends, another of the same person and another person's do not", async () => {
    const { r, a, b, c } = await world();
    expect(new Set([a.sid, b.sid, c.sid]).size).toBe(3);
    const res = await deliver(r, await r.fake.logoutToken(a.sid));
    expect(res.status).toBe(200);
    expect(res.headers["cache-control"]).toBe("no-store");
    expect(res.text).toBe("");
    expect(setCookies(res)).toEqual([]);
    expect(await alive(r, a)).toBe(false);
    expect(await alive(r, b)).toBe(true);
    expect(await alive(r, c)).toBe(true);
    expect(sessionKeys(r).sort()).toEqual([`${SESSION_KEY_PREFIX}${b.id}`, `${SESSION_KEY_PREFIX}${c.id}`].sort());
  });

  it("one provider session held by two pages sessions (single sign-on) ends both", async () => {
    const { r, a, c } = await world();
    const second = await signInAs(r, { username: "alex", sessionId: a.sid });
    expect(second.sid).toBe(a.sid);
    expect(sessionKeys(r)).toHaveLength(3);
    expect((await deliver(r, await r.fake.logoutToken(a.sid))).status).toBe(200);
    expect(await alive(r, a)).toBe(false);
    expect(await alive(r, second)).toBe(false);
    expect(await alive(r, c)).toBe(true);
  });

  it("names a person by `sub` alone: every session of that person ends, no one else's", async () => {
    const { r, a, b, c } = await world();
    expect((await deliver(r, await r.fake.logoutToken(a.sid, { claims: { sid: null } }))).status).toBe(200);
    expect(await alive(r, a)).toBe(false);
    expect(await alive(r, b)).toBe(false);
    expect(await alive(r, c)).toBe(true);
  });

  it("answers the same, with nothing to say, when it names no session of ours", async () => {
    const { r, a, b, c } = await world();
    const named = await deliver(r, await r.fake.logoutToken(c.sid));
    const nobody = await deliver(r, await r.fake.logoutToken(c.sid, { claims: { sid: "a-session-nobody-holds", sub: "sub-nobody" } }));
    expect(nobody.status).toBe(named.status);
    expect(nobody.text).toBe(named.text);
    expect(nobody.headers["cache-control"]).toBe(named.headers["cache-control"]);
    expect(await alive(r, a)).toBe(true);
    expect(await alive(r, b)).toBe(true);
    expect(await alive(r, c)).toBe(false);
  });

  it("ends the folders the session held, and leaves no index behind", async () => {
    const { r, a, b } = await world();
    const folder = "f".repeat(43);
    await r.store.set(`${STAGED_KEY_PREFIX}${folder}`, JSON.stringify({ files: {} }), 600);
    const key = `${SESSION_KEY_PREFIX}${a.id}`;
    const parsed = JSON.parse((await r.store.get(key)) as string) as Record<string, unknown>;
    parsed["staged"] = [folder];
    await r.store.set(key, JSON.stringify(parsed), 600);
    expect(indexKeys(r).length).toBeGreaterThan(0);
    // Every index key has a limit no longer than the session's own.
    for (const index of indexKeys(r)) expect(r.store.ttl(index)).toBeLessThanOrEqual(r.store.ttl(`${SESSION_KEY_PREFIX}${a.id}`) ?? 0);
    expect((await deliver(r, await r.fake.logoutToken(a.sid))).status).toBe(200);
    expect(await r.store.get(`${STAGED_KEY_PREFIX}${folder}`)).toBeNull();
    expect(await alive(r, b)).toBe(true);
    // Only the other sessions' index entries are left: two keys (the provider's session and the subject) for each.
    expect(indexKeys(r).length).toBe(2 * (sessionKeys(r).length));
  });
});

/** One way a logout token can fail a check, shaped as the provider really sends it, with one thing wrong. */
interface Plant {
  name: string;
  token(r: Rig, who: Person): Promise<string>;
  /** The fixed class the service logs. */
  class: string;
}

const NOW = (r: Rig): number => r.fake.nowSeconds();

function plant(name: string, klass: string, bend: LogoutTokenPlant | ((r: Rig) => LogoutTokenPlant)): Plant {
  return { name, class: klass, token: (r, who) => r.fake.logoutToken(who.sid, typeof bend === "function" ? bend(r) : bend) };
}

const PLANTS: Plant[] = [
  plant("signed with a key the realm does not publish", "signature", { signedWith: "other" }),
  plant("not signed at all (alg none)", "signature", { signedWith: "none" }),
  plant("signed with a shared secret (HS256) instead of the realm's key", "signature", { signedWith: "hmac" }),
  plant("another issuer", "issuer", { claims: { iss: "https://evil.example/realms/osprey" } }),
  plant("the issuer with a slash added", "issuer", (r) => ({ claims: { iss: `${r.fake.issuer}/` } })),
  plant("another client as the audience", "audience", { claims: { aud: "another-client" } }),
  plant("an audience list that leaves this client out", "audience", { claims: { aud: ["another-client", "a-third"] } }),
  plant("no audience", "audience", { claims: { aud: null } }),
  plant("no events claim", "event", { claims: { events: null } }),
  plant("another event", "event", { claims: { events: { "http://schemas.openid.net/event/other": {} } } }),
  plant("the logout event with a value that is not an object", "event", { claims: { events: { [BACKCHANNEL_EVENT]: "yes" } } }),
  plant("a nonce", "nonce", { claims: { nonce: "n-0S6_WzA2Mj" } }),
  plant("neither `sub` nor `sid`", "subject", { claims: { sub: null, sid: null } }),
  plant("a `sid` that is not a string", "subject", { claims: { sid: 12345 } }),
  plant("a `sub` that is empty and no `sid`", "subject", { claims: { sub: "", sid: null } }),
  plant("issued an hour ago", "age", (r) => ({ claims: { iat: NOW(r) - 3600 } })),
  plant("issued an hour from now", "age", (r) => ({ claims: { iat: NOW(r) + 3600 } })),
  plant("no `iat`", "age", { claims: { iat: null } }),
  plant("an `exp` that has passed", "age", (r) => ({ claims: { exp: NOW(r) - 60 } })),
  plant("no `jti`", "jti", { claims: { jti: null } }),
  plant("an `jti` that is not a string", "jti", { claims: { jti: 7 } }),
  // The tokens the provider also signs, presented as a logout token.
  {
    name: "an ID token of the person's, with its nonce",
    class: "event",
    token: (r, who) => r.fake.idTokenFor(who.sid, { nonce: "n-0S6_WzA2Mj" }),
  },
  {
    name: "an ID token that also claims the logout event (its nonce still refuses it)",
    class: "nonce",
    token: (r, who) => r.fake.idTokenFor(who.sid, { nonce: "n-0S6_WzA2Mj", events: { [BACKCHANNEL_EVENT]: {} }, jti: "j-0123456789" }),
  },
  { name: "the person's access token", class: "audience", token: (r, who) => Promise.resolve(r.fake.issued[who.issuedAt]!.accessToken) },
  { name: "the person's refresh token", class: "audience", token: (r, who) => Promise.resolve(r.fake.issued[who.issuedAt]!.refreshToken) },
  { name: "text that is not a token", class: "malformed", token: () => Promise.resolve("not-a-jwt") },
  { name: "an empty token", class: "malformed", token: () => Promise.resolve("") },
  { name: "twenty thousand characters", class: "malformed", token: () => Promise.resolve("a".repeat(20_000)) },
];

describe("a logout token that fails one check ends nothing", () => {
  it.each(PLANTS)("$name", async (planted) => {
    const { r, a, b, c } = await world();
    const captured = captureOutput();
    let bad;
    try {
      bad = await deliver(r, await planted.token(r, a));
    } finally {
      captured.restore();
    }
    // A plain refusal with no detail, the same for every check, and nothing ended.
    expect({ status: bad.status, text: bad.text }).toEqual(REFUSAL);
    expect(bad.headers["cache-control"]).toBe("no-store");
    expect(setCookies(bad)).toEqual([]);
    for (const person of [a, b, c]) expect(await alive(r, person), "no session ended").toBe(true);
    expect(sessionKeys(r)).toHaveLength(3);
    // What is said is a fixed word of ours, never the token or its claims.
    const said = r.log.filter((line) => line.startsWith("pages: back-channel logout refused: "));
    expect(said).toEqual([`pages: back-channel logout refused: ${planted.class}`]);
    expectNoSecret(r, `${captured.text()}\n${r.log.join("\n")}\n${everythingIn(bad)}`, "what was said", [a.sid, "sub-alex"]);

    // The control: the same session, a genuine token, ends it, so the plant is what was refused.
    expect((await deliver(r, await r.fake.logoutToken(a.sid))).status).toBe(200);
    expect(await alive(r, a)).toBe(false);
    expect(await alive(r, b)).toBe(true);
  });

  it.each([
    ["no `logout_token` field", (r: Rig) => request(r.app).post(BACKCHANNEL_LOGOUT_PATH).type("form").send({})],
    ["two `logout_token` fields", (r: Rig, token: string) => request(r.app).post(BACKCHANNEL_LOGOUT_PATH).type("form").send(`logout_token=${token}&logout_token=${token}`)],
    ["the token in the query and not the body", (r: Rig, token: string) => request(r.app).post(`${BACKCHANNEL_LOGOUT_PATH}?logout_token=${token}`).type("form").send({})],
    ["a JSON body", (r: Rig, token: string) => request(r.app).post(BACKCHANNEL_LOGOUT_PATH).type("json").send({ logout_token: token })],
    ["a body that is not a form", (r: Rig, token: string) => request(r.app).post(BACKCHANNEL_LOGOUT_PATH).type("text/plain").send(`logout_token=${token}`)],
    ["a body over the limit", (r: Rig, token: string) => request(r.app).post(BACKCHANNEL_LOGOUT_PATH).type("form").send({ logout_token: token, pad: "x".repeat(40_000) })],
  ])("%s", async (_name, send) => {
    const { r, a, b, c } = await world();
    const token = await r.fake.logoutToken(a.sid);
    const bad = await send(r, token);
    expect({ status: bad.status, text: bad.text }).toEqual(REFUSAL);
    for (const person of [a, b, c]) expect(await alive(r, person)).toBe(true);
    // The same token, sent properly, is genuine: it had not been used up by the refusal.
    expect((await deliver(r, token)).status).toBe(200);
    expect(await alive(r, a)).toBe(false);
  });

  it("a token already used is refused, and the person's new session of the same provider session is not ended", async () => {
    const { r, a, c } = await world();
    const token = await r.fake.logoutToken(a.sid);
    expect((await deliver(r, token)).status).toBe(200);
    expect(await alive(r, a)).toBe(false);
    // The person signs in again at the provider session they still hold (single sign-on); the old token is sent once more.
    const again = await signInAs(r, { username: "alex", sessionId: a.sid });
    expect(again.sid).toBe(a.sid);
    const replay = await deliver(r, token);
    expect({ status: replay.status, text: replay.text }).toEqual(REFUSAL);
    expect(await alive(r, again), "the new session is not ended by an old token").toBe(true);
    expect(await alive(r, c)).toBe(true);
    // A fresh token for it does end it.
    expect((await deliver(r, await r.fake.logoutToken(a.sid))).status).toBe(200);
    expect(await alive(r, again)).toBe(false);
  });

  it("two copies of one token at once: one is accepted, one refused", async () => {
    const { r, a } = await world();
    const token = await r.fake.logoutToken(a.sid);
    const results = await Promise.all([deliver(r, token), deliver(r, token)]);
    expect(results.map((x) => x.status).sort()).toEqual([200, 400]);
    expect(await alive(r, a)).toBe(false);
  });

  it("a key set that cannot be had is 503 with nothing ended, and does not use the token up", async () => {
    const r = await rig({ fake: { users: ["alex"] } });
    // A provider session the service has never fetched the realm's keys for: begin a sign-in, which creates one at the provider.
    const started = await request(r.app).get("/session/sign-in");
    r.fake.authorise(started.headers["location"] as string);
    const sid = [...r.fake.sessions.keys()].at(-1) as string;
    const token = await r.fake.logoutToken(sid);
    r.fake.certsStatus = 500;
    const down = await deliver(r, token);
    expect(down.status).toBe(503);
    expect(down.text).toBe("Unavailable");
    expect(down.text).not.toContain(sid);
    r.fake.certsStatus = undefined;
    expect((await deliver(r, token)).status, "the same token, once the keys can be had").toBe(200);
  });
});

describe("who may call the route", () => {
  it("anyone may, with a genuine token and no session; a session cookie adds nothing and a refused token ends the caller's own session no more than another's", async () => {
    const { r, a, b, c } = await world();
    // With no cookie at all a genuine token works: the token is the credential.
    expect((await deliver(r, await r.fake.logoutToken(a.sid))).status).toBe(200);
    // With a person's own cookie and a token that fails: refused, and the caller's own session stands.
    const withCookie = await request(r.app)
      .post(BACKCHANNEL_LOGOUT_PATH)
      .set("Cookie", b.cookie)
      .type("form")
      .send({ logout_token: await r.fake.logoutToken(b.sid, { signedWith: "other" }) });
    expect({ status: withCookie.status, text: withCookie.text }).toEqual(REFUSAL);
    expect(await alive(r, b)).toBe(true);
    // A genuine token for another person's session, sent with this person's cookie, ends that session and not this one.
    expect((await request(r.app).post(BACKCHANNEL_LOGOUT_PATH).set("Cookie", b.cookie).type("form").send({ logout_token: await r.fake.logoutToken(c.sid) })).status).toBe(200);
    expect(await alive(r, b)).toBe(true);
    expect(await alive(r, c)).toBe(false);
    // The route reads and sets no session: no cookie comes back, whatever the answer.
    const answers = [
      await deliver(r, await r.fake.logoutToken(b.sid, { signedWith: "none" })),
      await deliver(r, await r.fake.logoutToken(b.sid, { claims: { sid: "nobody", sub: "sub-nobody" } })),
    ];
    for (const res of answers) expect(setCookies(res)).toEqual([]);
  });

  it("is a POST and nothing else, and needs no anti-forgery token while every other POST still does", async () => {
    const { r, a, b } = await world();
    const token = await r.fake.logoutToken(a.sid);
    for (const method of ["get", "put", "delete", "patch"] as const) {
      const res = await request(r.app)[method](`${BACKCHANNEL_LOGOUT_PATH}?logout_token=${token}`).set("Cookie", b.cookie);
      expect([403, 404, 405], method).toContain(res.status);
    }
    expect(await alive(r, a)).toBe(true);
    // No `_csrf` and no `X-CSRF-Token` above or in `deliver`: the provider's server cannot send one. Any other POST needs it.
    expect((await request(r.app).post("/_test/echo").set("Cookie", b.cookie).type("form").send({})).status).toBe(403);
    expect((await request(r.app).post("/session/callback").type("form").send({})).status).toBe(403);
  });

  it("does not exist when the service has no provider to take a token from", async () => {
    const r = await rig({ noCodeFlow: true });
    const res = await deliver(r, "anything");
    expect(res.status).toBe(404);
  });
});
