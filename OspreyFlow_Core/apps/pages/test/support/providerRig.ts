/**
 * The page service against a fake Keycloak and a fake Conduit, for the cases that renew a token and sign out at the provider
 * (slice PL9b: `renewal.test.ts`, `providerLogout.test.ts`).
 *
 * The identity provider is `fakeKeycloak.ts`, which refuses what Keycloak refuses (`CLAUDE.md` rule 15). The Conduit is the
 * small server below: it accepts a bearer only if the provider issued it and it has not ended **by the provider's own clock**,
 * as the real Conduit refuses an expired token with a 401 (`services/api` verifies `exp`), and it records every call with the
 * bearer it carried, so a test can see which token was sent and that none was sent after a refusal.
 *
 * Two clocks move together: the service's (the session's lifetimes, the renewal margin) and the provider's (when its tokens end).
 * `advance` moves both.
 */
import { createServer } from "node:http";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import type { Express } from "express";
import type { Response } from "supertest";

import { createApp } from "../../server/app.js";
import type { RenewalOptions } from "../../server/accessToken.js";
import type { ForwardSettings } from "../../server/config.js";
import { Secret } from "../../server/config.js";
import type { CodeFlowProvider } from "../../server/identity.js";
import { LOGIN_COOKIE_NAME } from "../../server/loginState.js";
import { createOidcFlow } from "../../server/oidc.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import type { SessionStore } from "../../server/sessionStore.js";
import { noSessionEvents } from "./noSessionEvents.js";
import { testClock } from "./clock.js";
import type { TestClock } from "./clock.js";
import { startFakeKeycloak } from "./fakeKeycloak.js";
import type { FakeKeycloak, FakeKeycloakOptions } from "./fakeKeycloak.js";
import { TEST_SESSION_SECRET, cookieFrom, csrfFromPage, idFrom, request, setCookies } from "./http.js";
import { generateSecret } from "./secret.js";

export const CLIENT_ID = "osprey-pages";
export const ORIGIN = "https://pages.test.example";
export const REDIRECT_URI = `${ORIGIN}/session/callback`;

export interface Call {
  method: string;
  path: string;
  /** The bearer the call carried, or undefined. */
  bearer: string | undefined;
  status: number;
  /** The request body as the Conduit received it (UTF-8), so that a test can see a form was carried whole. */
  body: string;
}

export interface Upstream {
  url: string;
  calls: Call[];
  stop(): Promise<void>;
}

/** The payload of a JWT, unverified: the fake Conduit reads `exp`, and checks the provider issued the token. */
function expOf(token: string): number | undefined {
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1] as string, "base64url").toString("utf8")) as { exp?: unknown };
    return typeof payload.exp === "number" ? payload.exp : undefined;
  } catch {
    return undefined;
  }
}

async function startUpstream(fake: FakeKeycloak): Promise<Upstream> {
  const calls: Call[] = [];
  const server: Server = createServer((req, res) => {
    const header = req.headers.authorization;
    const bearer = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    const known = bearer !== undefined && fake.issued.some((issued) => issued.accessToken === bearer);
    const exp = bearer === undefined ? undefined : expOf(bearer);
    const live = known && exp !== undefined && exp > fake.nowSeconds();
    const status = live ? 200 : 401;
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      calls.push({ method: req.method ?? "GET", path: req.url ?? "", bearer, status, body: Buffer.concat(chunks).toString("utf8") });
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(live ? { ok: true } : { detail: "Not authenticated" }));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return {
    url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
    calls,
    stop: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => {
          resolve();
        });
      }),
  };
}

export interface RigOptions {
  fake?: Partial<Omit<FakeKeycloakOptions, "clientId" | "clientSecret" | "redirectUri">>;
  /** What the service is configured with, when it is not the fake's own client secret. */
  heldSecret?: string;
  renewal?: RenewalOptions;
  /** Wraps the in-memory store before the app sees it (a test that serves a stale read, or watches every call). */
  wrapStore?: (inner: MemorySessionStore) => SessionStore;
  /** Wraps the real flow (a test that makes one part of it fail). */
  wrapFlow?: (flow: CodeFlowProvider) => CodeFlowProvider;
  /** Without a code flow at all: the one-shot seam's app. */
  noCodeFlow?: boolean;
}

export interface Rig {
  fake: FakeKeycloak;
  upstream: Upstream;
  app: Express;
  store: MemorySessionStore;
  clock: TestClock;
  clientSecret: string;
  /** Everything the service logged through its `log`. */
  log: string[];
  /** Moves the service's clock and the provider's together. */
  advance(seconds: number): void;
}

const running: { stop(): Promise<void> }[] = [];

/** Stops every fake a rig started: call it from `afterEach`. */
export async function stopRigs(): Promise<void> {
  while (running.length) await running.pop()?.stop();
}

export async function rig(options: RigOptions = {}): Promise<Rig> {
  const clientSecret = generateSecret();
  const fake = await startFakeKeycloak({
    clientId: CLIENT_ID,
    clientSecret,
    redirectUri: REDIRECT_URI,
    ...options.fake,
  });
  running.push(fake);
  const upstream = await startUpstream(fake);
  running.push(upstream);
  // The service's clock starts where the provider's is, so that a token the provider signs "now" is now to the service too.
  const clock = testClock(Date.now());
  const log: string[] = [];
  const flow = createOidcFlow(
    { issuer: fake.issuer, clientId: CLIENT_ID, clientSecret: new Secret(options.heldSecret ?? clientSecret), publicOrigin: ORIGIN },
    { now: clock },
  );
  const store = new MemorySessionStore({ clock });
  const forward: ForwardSettings = { conduitUrl: upstream.url, bodyMaxBytes: 1_000_000, uploadMaxBytes: 10_000_000, upstreamTimeoutSeconds: 10 };
  const app = createApp({
    store: options.wrapStore ? options.wrapStore(store) : store,
    stagedStore: store,
    identityProvider: { signIn: () => Promise.reject(new Error("the one-shot seam is not used")) },
    ...(options.noCodeFlow ? {} : { codeFlow: options.wrapFlow ? options.wrapFlow(flow) : flow }),
    clock,
    sessionSecret: TEST_SESSION_SECRET,
    forward,
    sessionEvents: noSessionEvents,
    log: (message) => {
      log.push(message);
    },
    ...(options.renewal ? { renewal: options.renewal } : {}),
    extraRoutes: (router) => {
      router.all("/_test/echo", (_req, res) => {
        res.status(200).type("text/plain").send("accepted");
      });
      // A form's page: it answers with the field it was sent, so that a test sees the body was read whole and not lost.
      router.post("/_test/form", (req, res) => {
        const body = req.body as Record<string, unknown>;
        res.status(200).type("text/plain").send(`received: ${typeof body["note"] === "string" ? body["note"] : "(nothing)"}`);
      });
    },
  });
  return {
    fake,
    upstream,
    app,
    store,
    clock,
    clientSecret,
    log,
    advance(seconds) {
      clock.advance(seconds);
      fake.advance(seconds);
    },
  };
}

export interface Person {
  /** The `Cookie` request header, as the browser sends it. */
  cookie: string;
  /** The pages session's identifier: the store's key is named after it. */
  id: string;
  /** The provider's own session identifier (`sid`) for this sign-in. */
  sid: string;
  /** The ID token and the tokens the provider issued at this sign-in. */
  issuedAt: number;
  username: string;
}

function loginCookieOf(res: Pick<Response, "headers">): string {
  const mine = setCookies(res).find((c) => c.startsWith(`${LOGIN_COOKIE_NAME}=`));
  if (!mine) throw new Error("no login cookie was set");
  return mine.split(";")[0] as string;
}

/** The whole round trip, as one browser makes it. `sessionId` is a provider session the browser already holds (single sign-on). */
export async function signInAs(
  r: Rig,
  options: { username?: string; sessionId?: string; returnTo?: string } = {},
): Promise<Person> {
  const username = options.username ?? "alex";
  const path = options.returnTo === undefined ? "/session/sign-in" : `/session/sign-in?returnTo=${encodeURIComponent(options.returnTo)}`;
  const started = await request(r.app).get(path);
  if (started.status !== 302) throw new Error(`sign-in answered ${started.status}`);
  const callbackUrl = new URL(
    r.fake.authorise(started.headers["location"] as string, {
      username,
      ...(options.sessionId === undefined ? {} : { sessionId: options.sessionId }),
    }),
  );
  const callback = await request(r.app)
    .get(`${callbackUrl.pathname}${callbackUrl.search}`)
    .set("Cookie", loginCookieOf(started));
  if (callback.status !== 302) throw new Error(`the callback answered ${callback.status}`);
  const issued = r.fake.issued.at(-1);
  if (!issued) throw new Error("the provider issued nothing");
  return { cookie: cookieFrom(callback), id: idFrom(callback), sid: issued.sid, issuedAt: r.fake.issued.length - 1, username };
}

/** The anti-forgery token of a signed-in person, read off their home page. */
export async function csrfOf(r: Rig, person: Pick<Person, "cookie">): Promise<string> {
  const page = await request(r.app).get("/").set("Cookie", person.cookie);
  if (page.status !== 200) throw new Error(`the home page answered ${page.status}`);
  return csrfFromPage(page.text);
}

/** True when the response clears the session cookie: an empty value and an end in the past. */
export function clearsSessionCookie(res: Pick<Response, "headers">): boolean {
  return setCookies(res).some((c) => /^osprey_pages=;/.test(c) && /(Max-Age=0|Expires=Thu, 01 Jan 1970)/i.test(c));
}

/** Every piece of a token a log, a header or a page must not carry: whole, and its three segments. */
function pieces(token: string): string[] {
  return [token, ...token.split(".").filter((p) => p.length >= 16)];
}

/** What nobody but the service and the provider may see, in a text: every token the provider issued, the client secret, the session secret. */
export function secretsOf(r: Rig, extra: string[] = []): string[] {
  return [
    ...r.fake.issued.flatMap((i) => [...pieces(i.accessToken), ...pieces(i.refreshToken), ...pieces(i.idToken)]),
    ...r.fake.issued.flatMap((i) => [i.accessMarker, i.refreshMarker]),
    r.clientSecret,
    TEST_SESSION_SECRET,
    ...extra,
  ].filter((s) => s !== "");
}

/** Throws when a secret is in the text, in any of the forms a proxy or a log could write it, or any token-shaped string is. */
export function expectNoSecret(r: Rig, text: string, where: string, extra: string[] = []): void {
  for (const secret of secretsOf(r, extra)) {
    for (const form of [secret, encodeURIComponent(secret), Buffer.from(secret).toString("base64"), Buffer.from(secret).toString("base64url")]) {
      if (text.includes(form)) throw new Error(`${where}: a secret (${secret.slice(0, 12)}…) is in what was said`);
    }
  }
  if (/eyJ[A-Za-z0-9_-]{8,}\./.test(text)) throw new Error(`${where}: a token-shaped string is in what was said`);
}
