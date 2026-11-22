/**
 * Slice SE8c, acceptance (the page service's half; the Conduit's is `tests/services/api/test_sign_in_events.py`).
 * RULINGS SE8, the owner's word of 21 November 2026: sign-ins are recorded by the product, with no change to any
 * identity provider's configuration. The page service reports its sign-in callback and its sign-out to the
 * Conduit's `POST /v1/session-events`, with the person's own token; refused sign-in attempts stay in the
 * identity provider's own log, and the page service's own log says why in a word from a closed list, never in
 * the provider's words.
 *
 * Every case is the real app (`createApp`) over real HTTP. The sign-in that matters is the real authorisation-code
 * round trip against the fake Keycloak (`test/support/fakeKeycloak.ts`, which refuses what the real one refuses);
 * the cases about the report's failures use the one-shot provider seam, which reaches the same `startSession`. The
 * Conduit is a fake HTTP server that RECORDS every request it gets (method, target, every header, raw headers, the
 * body) so a refusal by the page service shows as no request, and that REFUSES what the real Conduit refuses
 * (rule 15; `services/api/app.py`):
 *  - no `Authorization: Bearer`, or a token it does not know or has expired: 401 `{"detail": ...}`;
 *  - a body that is not JSON, or is JSON with a field other than `kind`, or a `kind` outside `sign_in` and
 *    `sign_out`: 422 (the route's body model forbids extra fields, so a caller cannot name whose event it is);
 *  - any other path 404 and any other method 405.
 * Tokens, secrets, codes and states are made when the tests run; nothing here is a value anyone could use.
 *
 * Which test fails if (rule 12):
 *  - the callback stops reporting: "a successful callback reports sign_in…" (and `the assertions fail for a service
 *    that makes no call`, which runs the same assertion against an app whose reporter does nothing);
 *  - sign-out stops reporting: "sign-out reports sign_out…" (likewise);
 *  - a refused sign-in is reported: "a refused sign-in reports nothing…" (state, cookie, provider error, replay);
 *  - the Conduit being down, silent, or refusing stops a sign-in or sign-out: the cases of "the Conduit is down…";
 *  - a token, cookie, code, state, secret or provider address reaches the Conduit's request (beyond the bearer in
 *    its one header) or any log line: "nothing but the bearer…";
 *  - the refusal's log repeats the provider's words: "the log says the class of a refusal…".
 *
 * Folders walked: `apps/pages/server` is exercised by running it (`createApp`, `createOidcFlow`), not read.
 * Nothing here is a keyboard action (no new control), so `keyboard.spec.ts` has no step to add (rule 13).
 * Owed to a live stack: a real Conduit answering the route, and a real Keycloak's own refusal (the live step is off).
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, Server } from "node:http";
import type { AddressInfo } from "node:net";

import type { Express } from "express";
import type { Response } from "supertest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApp } from "../../server/app.js";
import type { ForwardSettings } from "../../server/config.js";
import { Secret } from "../../server/config.js";
import { IdentityProviderRefused, IdentityProviderUnavailable, REFUSAL_REASONS } from "../../server/identity.js";
import type { CodeFlowProvider, IdentityProvider, ProviderSession } from "../../server/identity.js";
import { LOGIN_COOKIE_NAME } from "../../server/loginState.js";
import { createOidcFlow } from "../../server/oidc.js";
import { COOKIE_NAME } from "../../server/sessionPolicy.js";
import { MemorySessionStore, SESSION_KEY_PREFIX } from "../../server/sessionStore.js";
import type { SessionEventReporter } from "../../server/sessionEvents.js";
import { captureOutput } from "../support/capture.js";
import type { Captured } from "../support/capture.js";
import { testClock } from "../support/clock.js";
import type { TestClock } from "../support/clock.js";
import { startFakeKeycloak } from "../support/fakeKeycloak.js";
import type { FakeKeycloak } from "../support/fakeKeycloak.js";
import { TEST_SESSION_SECRET, cookieFrom, csrfFromPage, request, setCookies } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

vi.setConfig({ testTimeout: 20_000 });

const CLIENT_ID = "osprey-pages";
const ORIGIN = "https://pages.test.example";
const ROUTE = "/v1/session-events";
const REFUSED_WORDS = "Sign-in was refused. Nothing about your access has changed.";

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

async function until(what: string, condition: () => boolean, ms = 4000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await sleep(5);
  }
}

/** Shaped like a signed access token; made now, at random, written nowhere. */
function mintToken(): string {
  return `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`;
}

// --- the fake Conduit ------------------------------------------------------------------------------------

interface Seen {
  method: string;
  url: string;
  headers: IncomingHttpHeaders;
  rawHeaders: string[];
  body: string;
  /** What the fake answered. */
  status: number;
}

interface FakeConduit {
  url: string;
  seen: Seen[];
  /** Tokens it answers 401 to, as it does a token that has expired. */
  expired: Set<string>;
  /** Answers every call with this status, whatever was asked. */
  force: number | undefined;
  /** Never answers: a Conduit that is silent. */
  hang: boolean;
  /** Answers with a redirect to this address: a Conduit that sends the caller elsewhere. */
  redirectTo: string | undefined;
  stop(): Promise<void>;
}

const conduits: Server[] = [];

/** `accepts` says which bearers it knows; the real Conduit verifies the signature, this knows the ones the test minted. */
async function startConduit(accepts: (token: string) => boolean): Promise<FakeConduit> {
  const fake: FakeConduit = {
    url: "",
    seen: [],
    expired: new Set(),
    force: undefined,
    hang: false,
    redirectTo: undefined,
    stop: () => new Promise((resolve) => server.close(() => resolve())),
  };
  const sockets = new Set<import("node:net").Socket>();
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      const record: Seen = {
        method: req.method ?? "",
        url: req.url ?? "",
        headers: req.headers,
        rawHeaders: req.rawHeaders,
        body: Buffer.concat(chunks).toString("utf8"),
        status: 0,
      };
      fake.seen.push(record);
      if (fake.hang) return; // never answers
      const answer = (status: number, body: unknown): void => {
        record.status = status;
        const raw = JSON.stringify(body);
        res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(raw) });
        res.end(raw);
      };
      if (fake.redirectTo !== undefined) {
        record.status = 307;
        res.writeHead(307, { Location: fake.redirectTo, "Content-Length": 0 });
        res.end();
        return;
      }
      if (fake.force !== undefined) return answer(fake.force, { detail: "forced" });
      const header = req.headers.authorization;
      const token = typeof header === "string" && /^Bearer /i.test(header) ? header.slice(7) : undefined;
      if (token === undefined) return answer(401, { detail: "Not authenticated" });
      if (fake.expired.has(token)) return answer(401, { detail: "token rejected: Signature has expired" });
      if (!accepts(token)) return answer(401, { detail: "token rejected: Signature verification failed" });
      if (req.url !== ROUTE) return answer(404, { detail: "Not Found" });
      if (req.method !== "POST") return answer(405, { detail: "Method Not Allowed" });
      let parsed: unknown;
      try {
        parsed = JSON.parse(record.body);
      } catch {
        return answer(422, { detail: [{ type: "json_invalid" }] });
      }
      const ok =
        typeof parsed === "object" &&
        parsed !== null &&
        Object.keys(parsed).length === 1 &&
        ["sign_in", "sign_out"].includes((parsed as { kind?: unknown }).kind as string);
      if (!/^application\/json/i.test(req.headers["content-type"] ?? "") || !ok) return answer(422, { detail: [{ type: "literal_error" }] });
      return answer(200, { recorded: true });
    });
  });
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
  });
  const stop = fake.stop;
  fake.stop = async () => {
    for (const socket of sockets) socket.destroy();
    await stop();
  };
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  fake.url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  conduits.push(server);
  return fake;
}

/** An address nothing listens on: the Conduit is down. */
async function closedAddress(): Promise<string> {
  const probe = createServer();
  await new Promise<void>((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const port = (probe.address() as AddressInfo).port;
  await new Promise<void>((resolve) => probe.close(() => resolve()));
  return `http://127.0.0.1:${port}`;
}

// --- the rigs --------------------------------------------------------------------------------------------

let captured: Captured | undefined;
const cleanups: Array<() => Promise<void>> = [];

afterEach(async () => {
  captured?.restore();
  captured = undefined;
  while (cleanups.length) await cleanups.pop()?.();
});

function forwardTo(conduitUrl: string): ForwardSettings {
  return { conduitUrl, bodyMaxBytes: 1024 * 1024, uploadMaxBytes: 1024 * 1024, upstreamTimeoutSeconds: 5 };
}

interface Rig {
  app: Express;
  store: MemorySessionStore;
  clock: TestClock;
  conduit: FakeConduit;
  /** Everything the service wrote to a log, by the console, the streams and `deps.log`. */
  output(): string;
  /** The tokens the one-shot provider has handed out. */
  minted: string[];
  misses(): number;
}

interface RigOptions {
  /** The Conduit's address, when it is not the fake's own (down). */
  conduitUrl?: string;
  /** No Conduit address at all. */
  noConduit?: boolean;
  timeoutMs?: number;
  codeFlow?: CodeFlowProvider;
  reporter?: SessionEventReporter;
  accepts?: (token: string) => boolean;
}

async function rig(options: RigOptions = {}): Promise<Rig> {
  const minted: string[] = [];
  const conduit = await startConduit(options.accepts ?? ((t) => minted.includes(t)));
  cleanups.push(() => conduit.stop());
  const clock = testClock();
  const store = new MemorySessionStore({ clock });
  const logged: string[] = [];
  const identityProvider: IdentityProvider = {
    async signIn(): Promise<ProviderSession> {
      const accessToken = mintToken();
      minted.push(accessToken);
      return {
        subject: "sub-alex",
        displayName: "Alex Example",
        accessToken,
        refreshToken: mintToken(),
        idToken: mintToken(),
        idpSessionExpiresAt: clock() + 36_000_000,
      };
    },
  };
  captured = captureOutput();
  const app = createApp({
    store,
    identityProvider,
    ...(options.codeFlow ? { codeFlow: options.codeFlow } : {}),
    clock,
    sessionSecret: TEST_SESSION_SECRET,
    ...(options.noConduit ? {} : { forward: forwardTo(options.conduitUrl ?? conduit.url) }),
    ...(options.timeoutMs === undefined ? {} : { sessionEventTimeoutMs: options.timeoutMs }),
    ...(options.reporter ? { sessionEvents: options.reporter } : {}),
    log: (message) => {
      logged.push(message);
    },
  });
  const reporter = (app.locals as { sessionEvents?: SessionEventReporter }).sessionEvents;
  return {
    app,
    store,
    clock,
    conduit,
    output: () => `${captured?.text() ?? ""}\n${logged.join("\n")}`,
    minted,
    misses: () => reporter?.misses ?? 0,
  };
}

/** The one-shot seam's sign-in: the same `startSession` the callback ends in. */
async function signInOnce(r: Rig): Promise<{ cookie: string; csrf: string; token: string }> {
  const res = await request(r.app).get("/session/sign-in");
  expect(res.status).toBe(302);
  const cookie = cookieFrom(res);
  const page = await request(r.app).get("/").set("Cookie", cookie);
  return { cookie, csrf: csrfFromPage(page.text), token: r.minted[r.minted.length - 1] as string };
}

async function signOut(r: Rig, signed: { cookie: string; csrf: string }): Promise<Response> {
  return request(r.app).post("/session/sign-out").set("Cookie", signed.cookie).type("form").send(`_csrf=${signed.csrf}`);
}

const sessionKeys = (r: Rig): string[] => r.store.keys().filter((k) => k.startsWith(SESSION_KEY_PREFIX));

/** The report is fire-and-forget (a sign-in is never held for it), so a test waits for it. */
async function reported(r: Rig, count: number): Promise<void> {
  await until(`${count} request(s) at the Conduit`, () => r.conduit.seen.length >= count);
  await sleep(30);
  expect(r.conduit.seen.length).toBe(count);
}

function bearerOf(seen: Seen): string {
  return (seen.headers.authorization ?? "").replace(/^Bearer /, "");
}

// --- the real round trip ---------------------------------------------------------------------------------

interface Real extends Rig {
  fake: FakeKeycloak;
  clientSecret: string;
}

const keycloaks: FakeKeycloak[] = [];
afterEach(async () => {
  while (keycloaks.length) await keycloaks.pop()?.stop();
});

async function realRig(options: Omit<RigOptions, "codeFlow" | "accepts"> = {}): Promise<Real> {
  const clientSecret = generateSecret();
  const fake = await startFakeKeycloak({ clientId: CLIENT_ID, clientSecret, redirectUri: `${ORIGIN}/session/callback` });
  keycloaks.push(fake);
  const clock = testClock();
  const flow = createOidcFlow(
    { issuer: fake.issuer, clientId: CLIENT_ID, clientSecret: new Secret(clientSecret), publicOrigin: ORIGIN },
    { now: clock },
  );
  const r = await rig({ ...options, codeFlow: flow, accepts: (t) => fake.issued.some((i) => i.accessToken === t) });
  return { ...r, fake, clientSecret };
}

function loginCookieOf(res: Pick<Response, "headers">): string {
  const mine = setCookies(res).find((c) => c.startsWith(`${LOGIN_COOKIE_NAME}=`));
  if (!mine) throw new Error("no login cookie was set");
  return mine.split(";")[0] as string;
}

interface Trip {
  started: Response;
  authorisationUrl: URL;
  loginCookie: string;
  callbackPath: string;
}

async function startTrip(r: Real): Promise<Trip> {
  const started = await request(r.app).get("/session/sign-in");
  expect(started.status).toBe(302);
  const authorisationUrl = new URL(started.headers["location"] as string);
  const back = new URL(r.fake.authorise(authorisationUrl.toString(), { username: "alex" }));
  return { started, authorisationUrl, loginCookie: loginCookieOf(started), callbackPath: `${back.pathname}${back.search}` };
}

async function callback(r: Real, path: string, cookie?: string): Promise<Response> {
  const req = request(r.app).get(path);
  if (cookie) req.set("Cookie", cookie);
  return req;
}

/** The assertions of a reported sign-in, as one function so a planted fault can be run against them. */
async function expectSignInReported(r: Real): Promise<void> {
  const trip = await startTrip(r);
  const done = await callback(r, trip.callbackPath, trip.loginCookie);
  expect(done.status).toBe(302);
  await reported(r, 1);
  const [seen] = r.conduit.seen as [Seen];
  expect(seen.method).toBe("POST");
  expect(seen.url).toBe(ROUTE);
  expect(JSON.parse(seen.body)).toEqual({ kind: "sign_in" });
  expect(bearerOf(seen)).toBe(r.fake.issued[0]?.accessToken);
  expect(seen.headers["content-type"]).toMatch(/^application\/json/);
}

describe("the callback reports the sign-in", () => {
  it("a successful callback reports sign_in with the person's own token, and a body of the kind alone", async () => {
    const r = await realRig();
    await expectSignInReported(r);
  });

  it("the assertions fail for a service that makes no call (rule 12, planted at the call)", async () => {
    const silent: SessionEventReporter = { async report() {}, async settled() {}, misses: 0 };
    const r = await realRig({ reporter: silent });
    await expect(expectSignInReported(r)).rejects.toThrow();
  });

  it("the same, by the one-shot seam: both reach startSession", async () => {
    const r = await rig();
    const signed = await signInOnce(r);
    await reported(r, 1);
    expect(JSON.parse((r.conduit.seen[0] as Seen).body)).toEqual({ kind: "sign_in" });
    expect(bearerOf(r.conduit.seen[0] as Seen)).toBe(signed.token);
  });

  it("each sign-in reports once, with its own token", async () => {
    const r = await rig();
    const first = await signInOnce(r);
    const second = await signInOnce(r);
    await reported(r, 2);
    expect(r.conduit.seen.map(bearerOf)).toEqual([first.token, second.token]);
  });
});

describe("sign-out reports the sign-out", () => {
  it("sign-out reports sign_out with the session's token, then the session is gone", async () => {
    const r = await rig();
    const signed = await signInOnce(r);
    await reported(r, 1);
    const res = await signOut(r, signed);
    expect(res.status).toBe(303);
    await reported(r, 2);
    const out = r.conduit.seen[1] as Seen;
    expect(JSON.parse(out.body)).toEqual({ kind: "sign_out" });
    expect(bearerOf(out)).toBe(signed.token);
    expect(sessionKeys(r)).toEqual([]);
    expect(setCookies(res).some((c) => c.startsWith(`${COOKIE_NAME}=;`))).toBe(true);
  });

  it("the service asks its reporter for both kinds, in order (a sign-out that stops calling is red here)", async () => {
    const calls: Array<[string, string]> = [];
    const spy: SessionEventReporter = {
      async report(kind, token) {
        calls.push([kind, token]);
      },
      async settled() {},
      misses: 0,
    };
    const r = await rig({ reporter: spy });
    const signed = await signInOnce(r);
    await signOut(r, signed);
    expect(calls).toEqual([
      ["sign_in", signed.token],
      ["sign_out", signed.token],
    ]);
  });

  it("the assertions fail for a service whose sign-out makes no call (rule 12, planted at the call)", async () => {
    const r = await rig({ reporter: { async report() {}, async settled() {}, misses: 0 } });
    const signed = await signInOnce(r);
    await signOut(r, signed);
    await sleep(50);
    expect(() => {
      expect(r.conduit.seen.map((s) => (JSON.parse(s.body) as { kind: string }).kind)).toContain("sign_out");
    }).toThrow();
  });

  it("a sign-out after the token expired still deletes the session, records nothing, and logs without the token", async () => {
    const r = await rig();
    const signed = await signInOnce(r);
    await reported(r, 1);
    r.conduit.expired.add(signed.token);
    const res = await signOut(r, signed);
    expect(res.status).toBe(303);
    await reported(r, 2);
    expect((r.conduit.seen[1] as Seen).status).toBe(401);
    expect(sessionKeys(r)).toEqual([]);
    await until("the miss", () => r.misses() === 1);
    expect(r.output()).toMatch(/pages: session event not recorded: sign_out/);
    expect(r.output()).not.toContain(signed.token);
  });

  it("a sign-out with no session reports nothing", async () => {
    const r = await rig();
    const res = await request(r.app).post("/session/sign-out").type("form").send("_csrf=wrong");
    expect(res.status).toBeGreaterThanOrEqual(400);
    await sleep(50);
    expect(r.conduit.seen).toEqual([]);
  });
});

describe("the Conduit is down, silent or refusing: sign-in and sign-out go on", () => {
  it("down: the sign-in is a sign-in, the session is kept, the miss is counted and logged without the token", async () => {
    const r = await rig({ conduitUrl: await closedAddress() });
    const signed = await signInOnce(r);
    expect(sessionKeys(r).length).toBe(1);
    await until("the first miss", () => r.misses() === 1);
    const res = await signOut(r, signed);
    expect(res.status).toBe(303);
    expect(sessionKeys(r)).toEqual([]);
    await until("the second miss", () => r.misses() === 2);
    const said = r.output();
    expect(said).toMatch(/pages: session event not recorded: sign_in/);
    expect(said).toMatch(/pages: session event not recorded: sign_out/);
    expect(said).not.toContain(signed.token);
    for (const token of r.minted) expect(said).not.toContain(token);
  });

  it("silent: the sign-in is not held for it, and the call is given up", async () => {
    const r = await rig({ timeoutMs: 1500 });
    r.conduit.hang = true;
    const started = Date.now();
    const signed = await signInOnce(r);
    // Two requests (the sign-in, then the page) and no wait for a Conduit that will not answer for 1.5 s.
    expect(Date.now() - started).toBeLessThan(900);
    expect(sessionKeys(r).length).toBe(1);
    await until("the given-up call", () => r.misses() === 1, 4000);
    const res = await signOut(r, signed);
    expect(res.status).toBe(303);
    expect(sessionKeys(r)).toEqual([]);
  });

  it.each([401, 403, 404, 422, 429, 500, 502, 503])("a Conduit that answers %i is a miss, never a failed sign-in", async (status) => {
    const r = await rig();
    r.conduit.force = status;
    const signed = await signInOnce(r);
    await until("the miss", () => r.misses() === 1);
    expect(sessionKeys(r).length).toBe(1);
    const res = await signOut(r, signed);
    expect(res.status).toBe(303);
    await until("the second miss", () => r.misses() === 2);
    expect(r.output()).not.toContain(signed.token);
  });

  it("a Conduit that redirects is a miss, and the bearer goes nowhere else", async () => {
    const elsewhere = await startConduit(() => true);
    cleanups.push(() => elsewhere.stop());
    const r = await rig();
    r.conduit.redirectTo = `${elsewhere.url}${ROUTE}`;
    const signed = await signInOnce(r);
    await until("the miss", () => r.misses() === 1);
    expect(sessionKeys(r).length).toBe(1);
    await sleep(100);
    expect(elsewhere.seen).toEqual([]);
    expect(r.output()).not.toContain(signed.token);
  });

  it("with no Conduit address nothing is sent and nothing is counted", async () => {
    const r = await rig({ noConduit: true });
    const signed = await signInOnce(r);
    expect((await signOut(r, signed)).status).toBe(303);
    await sleep(50);
    expect(r.conduit.seen).toEqual([]);
    expect(r.misses()).toBe(0);
  });
});

describe("a refused sign-in reports nothing: refused attempts stay in the identity provider's own log", () => {
  it("a state that is not the flow's own, no login cookie, the provider's own error, a replay: no request at the Conduit", async () => {
    const r = await realRig();
    // The provider's own error on the callback, with synthetic words of its own in it.
    const t1 = await startTrip(r);
    const error = generateSecret(30);
    const res1 = await callback(r, `/session/callback?error=access_denied&error_description=${error}&state=${t1.authorisationUrl.searchParams.get("state")}`, t1.loginCookie);
    expect(res1.status).toBe(403);
    // A state that is not this sign-in's own.
    const t2 = await startTrip(r);
    const res2 = await callback(r, t2.callbackPath.replace(/state=[^&]+/, "state=not-the-flows"), t2.loginCookie);
    expect(res2.status).toBe(403);
    // No login cookie at all.
    const t3 = await startTrip(r);
    expect((await callback(r, t3.callbackPath)).status).toBe(403);
    // A replay: the first use signs in, the second finds no record.
    const t4 = await startTrip(r);
    expect((await callback(r, t4.callbackPath, t4.loginCookie)).status).toBe(302);
    await reported(r, 1);
    expect((await callback(r, t4.callbackPath, t4.loginCookie)).status).toBe(403);
    await sleep(100);
    expect(r.conduit.seen.length).toBe(1);
    expect(JSON.parse((r.conduit.seen[0] as Seen).body)).toEqual({ kind: "sign_in" });
  });

  it("a provider that is unreachable is no sign-in and reports nothing", async () => {
    const flow: CodeFlowProvider = {
      async begin() {
        return { authorizationUrl: "https://idp.invalid/auth", pending: { state: "s", nonce: "n", verifier: "v" } };
      },
      async complete() {
        throw new IdentityProviderUnavailable("down");
      },
    };
    const r = await rig({ codeFlow: flow });
    const started = await request(r.app).get("/session/sign-in");
    const res = await request(r.app).get("/session/callback?code=c&state=s").set("Cookie", loginCookieOf(started));
    expect(res.status).toBe(503);
    await sleep(50);
    expect(r.conduit.seen).toEqual([]);
  });
});

describe("the log says the class of a refusal, from a closed list, and never the provider's words", () => {
  /** A flow that fails the way a provider can: with words of its own, one of which looks like a secret. */
  function failing(make: (words: string) => Error): { flow: CodeFlowProvider; words: string } {
    const words = `error_description=${generateSecret(24)} client_secret=${generateSecret(24)}`;
    const flow: CodeFlowProvider = {
      async begin() {
        return { authorizationUrl: "https://idp.invalid/auth", pending: { state: "s", nonce: "n", verifier: "v" } };
      },
      async complete() {
        throw make(words);
      },
    };
    return { flow, words };
  }

  const makers: Array<[string, (words: string) => Error, number]> = [
    ["a refusal that carries the provider's message", (w) => new IdentityProviderRefused(w), 403],
    ["an unavailable provider that carries the provider's message", (w) => new IdentityProviderUnavailable(w), 503],
    ["an error of any other kind", (w) => new Error(w), 500],
  ];

  it.each(makers)("%s: the words are in no log line and no response", async (_name, make, status) => {
    const { flow, words } = failing(make);
    const r = await rig({ codeFlow: flow });
    const started = await request(r.app).get("/session/sign-in");
    const res = await request(r.app).get("/session/callback?code=c&state=s").set("Cookie", loginCookieOf(started));
    expect(res.status).toBe(status);
    expect(res.text).not.toContain(words.split(" ")[0] as string);
    const said = r.output();
    for (const part of words.split(" ")) expect(said).not.toContain(part.split("=")[1] as string);
    expect(said).toMatch(/pages: sign-in (refused|could not be completed|failed): /);
  });

  it("every refusal's log line carries one word of the closed list", async () => {
    const r = await realRig();
    const t1 = await startTrip(r);
    await callback(r, `/session/callback?error=access_denied&error_description=${generateSecret(20)}&state=${t1.authorisationUrl.searchParams.get("state")}`, t1.loginCookie);
    const t2 = await startTrip(r);
    await callback(r, t2.callbackPath.replace(/state=[^&]+/, "state=other"), t2.loginCookie);
    const t3 = await startTrip(r);
    await callback(r, t3.callbackPath);
    const t4 = await startTrip(r);
    await callback(r, t4.callbackPath, t4.loginCookie);
    await callback(r, t4.callbackPath, t4.loginCookie);
    r.fake.claimOverrides = { aud: "another-client" };
    const t5 = await startTrip(r);
    await callback(r, t5.callbackPath, t5.loginCookie);
    r.fake.claimOverrides = {};
    r.fake.signWithOtherKey = true;
    const t6 = await startTrip(r);
    await callback(r, t6.callbackPath, t6.loginCookie);
    const lines = r.output().split("\n").filter((l) => l.includes("pages: sign-in refused:"));
    expect(lines.length).toBeGreaterThanOrEqual(6);
    for (const line of lines) {
      const word = /pages: sign-in refused: (\S+)\s*$/.exec(line)?.[1];
      expect(word, line).toBeDefined();
      expect(REFUSAL_REASONS as readonly string[], line).toContain(word);
    }
  });

  it("the closed list is words of ours: lower-case letters and underscores, and the default is in it", () => {
    expect(REFUSAL_REASONS.length).toBeGreaterThanOrEqual(8);
    for (const reason of REFUSAL_REASONS) expect(reason).toMatch(/^[a-z]+(_[a-z]+)*$/);
    expect(REFUSAL_REASONS).toContain("refused");
    expect(new IdentityProviderRefused("x").reason).toBe("refused");
    expect(new IdentityProviderRefused("x", "state_mismatch").reason).toBe("state_mismatch");
  });
});

describe("nothing but the bearer: no token, cookie, code, state, secret or address is in a request or a log line", () => {
  it("the round trip, a sign-out and a failed report leave only the bearer, in its one header", async () => {
    const r = await realRig();
    const trip = await startTrip(r);
    const state = trip.authorisationUrl.searchParams.get("state") as string;
    const code = new URL(`${ORIGIN}${trip.callbackPath}`).searchParams.get("code") as string;
    const done = await callback(r, trip.callbackPath, trip.loginCookie);
    expect(done.status).toBe(302);
    const sessionCookie = cookieFrom(done);
    const home = await request(r.app).get("/").set("Cookie", sessionCookie);
    const csrf = csrfFromPage(home.text);
    await reported(r, 1);
    const out = await signOut(r, { cookie: sessionCookie, csrf });
    expect(out.status).toBe(303);
    await reported(r, 2);

    const issued = r.fake.issued[0];
    const bearer = issued?.accessToken as string;
    const forbidden: Record<string, string> = {
      "the refresh token": issued?.refreshToken as string,
      "the ID token": issued?.idToken as string,
      "the session cookie's value": sessionCookie.split("=")[1] as string,
      "the login cookie's value": trip.loginCookie.split("=")[1] as string,
      "the code": code,
      "the state": state,
      "the client's secret": r.clientSecret,
      "the session secret": TEST_SESSION_SECRET,
      "the anti-forgery token": csrf,
      "the provider's address": r.fake.issuer,
    };
    for (const seen of r.conduit.seen) {
      const raw = `${seen.rawHeaders.join("\n")}\n${seen.body}\n${seen.url}`;
      for (const [name, value] of Object.entries(forbidden)) expect(raw, `${name} in a request`).not.toContain(value);
      expect(seen.headers["cookie"]).toBeUndefined();
      expect(seen.headers["x-csrf-token"]).toBeUndefined();
      // The bearer is in the one header and nowhere else of the request.
      const rest = raw.replace(`Bearer ${bearer}`, "");
      expect(rest).not.toContain(bearer);
    }
    const said = r.output();
    for (const [name, value] of Object.entries({ ...forbidden, "the access token": bearer })) {
      if (name === "the provider's address") continue; // a log line of our own may name the realm's address at start-up, not here
      expect(said, `${name} in a log line`).not.toContain(value);
    }
  });

  it("the same scan finds a token written where the service would write it (planted)", async () => {
    const r = await rig();
    const signed = await signInOnce(r);
    console.error(`pages: session event not recorded: sign_in ${signed.token}`);
    expect(r.output()).toContain(signed.token);
  });
});
