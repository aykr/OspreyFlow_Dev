/**
 * Slice SE8c, round 2: the provider's address is in no log line of any path the slice touches.
 *
 * The brief (item 6): "a record never carries ... an address of the provider (synthetic values placed in each at run
 * time; asserted absent from every audit column and every log line of each path)". `sign-in-events.test.ts` scans the
 * round trip's log for every other value and leaves the provider's address out; this file scans for it, on every path:
 * the callback and sign-out that succeed, a report the Conduit refuses or never receives, a refusal by the provider
 * and a provider that fails with its own address in its words.
 *
 * The address is the fake Keycloak's own, made when the test runs (a port the operating system gave): the whole
 * issuer, and its host and port alone (which an error naming only where it could not connect would carry).
 * Every case reads `captureOutput` (the console and both streams) and the `log` the app was given.
 *
 * Which test fails if (rule 12): the callback, the sign-out or a failed report names the provider's address in a log
 * line: each "…leaves no address…" case; the scan itself stops finding one: "the scan finds the address…" (planted at the
 * shapes the service's own lines take: `deps.log` and `console.error`).
 *
 * Folders walked: `apps/pages/server` is run (`createApp`, `createOidcFlow`), not read. No keyboard action (rule 13).
 */
import { createServer } from "node:http";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it, vi } from "vitest";

import { createApp } from "../../server/app.js";
import { Secret } from "../../server/config.js";
import { IdentityProviderRefused, IdentityProviderUnavailable } from "../../server/identity.js";
import type { CodeFlowProvider } from "../../server/identity.js";
import { LOGIN_COOKIE_NAME } from "../../server/loginState.js";
import { createOidcFlow } from "../../server/oidc.js";
import type { SessionEventReporter } from "../../server/sessionEvents.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { captureOutput } from "../support/capture.js";
import type { Captured } from "../support/capture.js";
import { testClock } from "../support/clock.js";
import { startFakeKeycloak } from "../support/fakeKeycloak.js";
import type { FakeKeycloak } from "../support/fakeKeycloak.js";
import { TEST_SESSION_SECRET, cookieFrom, csrfFromPage, request, setCookies } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

vi.setConfig({ testTimeout: 20_000 });

const CLIENT_ID = "osprey-pages";
const ORIGIN = "https://pages.test.example";

let captured: Captured | undefined;
const cleanups: Array<() => Promise<void>> = [];

afterEach(async () => {
  captured?.restore();
  captured = undefined;
  while (cleanups.length) await cleanups.pop()?.();
});

/** The values that name the provider: the issuer whole, and where it listens. */
function addressesOf(fake: FakeKeycloak): Record<string, string> {
  const url = new URL(fake.issuer);
  return { "the issuer": fake.issuer, "the provider's host and port": url.host, "the provider's realm path": url.pathname };
}

/** What a scan finds: the names of the values a text carries. Used on the service's output and on a planted line. */
function carried(text: string, values: Record<string, string>): string[] {
  return Object.entries(values)
    .filter(([, value]) => text.includes(value))
    .map(([name]) => name);
}

/** A Conduit that answers every report with `status`, or is not there (`down`). */
async function conduit(status: number | "down"): Promise<string> {
  const probe: Server = createServer((req, res) => {
    req.resume();
    req.on("end", () => {
      res.writeHead(status === "down" ? 200 : status, { "Content-Type": "application/json" });
      res.end("{}");
    });
  });
  await new Promise<void>((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${(probe.address() as AddressInfo).port}`;
  if (status === "down") await new Promise<void>((resolve) => probe.close(() => resolve()));
  else cleanups.push(() => new Promise<void>((resolve) => probe.close(() => resolve())));
  return url;
}

interface Rig {
  app: ReturnType<typeof createApp>;
  fake: FakeKeycloak;
  clientSecret: string;
  addresses: Record<string, string>;
  /** Everything of the app's own logging, by the console, the streams and `deps.log`. */
  output(): string;
  reporter: SessionEventReporter;
}

async function rig(
  conduitStatus: number | "down",
  codeFlow?: (fake: FakeKeycloak) => CodeFlowProvider,
  /** Plants a fault at `deps.log`, the one function the reporter's miss line goes through. */
  decorate?: (message: string, fake: FakeKeycloak) => string,
): Promise<Rig> {
  const clientSecret = generateSecret();
  const fake = await startFakeKeycloak({ clientId: CLIENT_ID, clientSecret, redirectUri: `${ORIGIN}/session/callback` });
  cleanups.push(() => fake.stop());
  const clock = testClock();
  const flow =
    codeFlow?.(fake) ??
    createOidcFlow(
      { issuer: fake.issuer, clientId: CLIENT_ID, clientSecret: new Secret(clientSecret), publicOrigin: ORIGIN },
      { now: clock },
    );
  const url = await conduit(conduitStatus);
  const logged: string[] = [];
  captured = captureOutput();
  const app = createApp({
    store: new MemorySessionStore({ clock }),
    identityProvider: { signIn: () => Promise.reject(new Error("the code flow is used")) },
    codeFlow: flow,
    clock,
    sessionSecret: TEST_SESSION_SECRET,
    forward: { conduitUrl: url, bodyMaxBytes: 1024 * 1024, uploadMaxBytes: 1024 * 1024, upstreamTimeoutSeconds: 5 },
    sessionEventTimeoutMs: 1500,
    log: (message) => {
      logged.push(decorate ? decorate(message, fake) : message);
    },
  });
  return {
    app,
    fake,
    clientSecret,
    addresses: addressesOf(fake),
    output: () => `${captured?.text() ?? ""}\n${logged.join("\n")}`,
    reporter: (app.locals as { sessionEvents: SessionEventReporter }).sessionEvents,
  };
}

function loginCookieOf(res: { headers: Record<string, unknown> }): string {
  const mine = setCookies(res as never).find((c) => c.startsWith(`${LOGIN_COOKIE_NAME}=`));
  if (!mine) throw new Error("no login cookie was set");
  return mine.split(";")[0] as string;
}

/** The whole round trip, then sign-out, and the report's end awaited so its log line (if any) is in the output. */
async function signInAndOut(r: Rig): Promise<void> {
  const started = await request(r.app).get("/session/sign-in");
  expect(started.status).toBe(302);
  const authorisationUrl = new URL(started.headers["location"] as string);
  const back = new URL(r.fake.authorise(authorisationUrl.toString(), { username: "alex" }));
  const done = await request(r.app)
    .get(`${back.pathname}${back.search}`)
    .set("Cookie", loginCookieOf(started));
  expect(done.status).toBe(302);
  const cookie = cookieFrom(done);
  const home = await request(r.app).get("/").set("Cookie", cookie);
  const out = await request(r.app)
    .post("/session/sign-out")
    .set("Cookie", cookie)
    .type("form")
    .send(`_csrf=${csrfFromPage(home.text)}`);
  expect(out.status).toBe(303);
  await r.reporter.settled();
}

describe("the provider's address is in no log line of the callback, the sign-out or a failed report", () => {
  it("a sign-in and a sign-out that are recorded leave no address", async () => {
    const r = await rig(200);
    await signInAndOut(r);
    expect(r.reporter.misses).toBe(0);
    expect(carried(r.output(), r.addresses)).toEqual([]);
  });

  it.each([401, 422, 429, 500, 503])("a Conduit that answers %i leaves a miss line and no address", async (status) => {
    const r = await rig(status);
    await signInAndOut(r);
    expect(r.reporter.misses).toBe(2);
    expect(r.output()).toMatch(/pages: session event not recorded: sign_in: /);
    expect(r.output()).toMatch(/pages: session event not recorded: sign_out: /);
    expect(carried(r.output(), r.addresses)).toEqual([]);
  });

  it("a Conduit that is down leaves a miss line and no address", async () => {
    const r = await rig("down");
    await signInAndOut(r);
    expect(r.reporter.misses).toBe(2);
    expect(r.output()).toMatch(/pages: session event not recorded: sign_in: the Conduit could not be reached/);
    expect(carried(r.output(), r.addresses)).toEqual([]);
  });

  it("a refusal by the provider on the callback, with its own address in its words, leaves no address", async () => {
    const r = await rig(200);
    const started = await request(r.app).get("/session/sign-in");
    const authorisationUrl = new URL(started.headers["location"] as string);
    const state = authorisationUrl.searchParams.get("state") as string;
    const res = await request(r.app)
      .get(`/session/callback?error=access_denied&error_description=${encodeURIComponent(r.fake.issuer)}&state=${state}`)
      .set("Cookie", loginCookieOf(started));
    expect(res.status).toBe(403);
    expect(res.text).not.toContain(r.fake.issuer);
    expect(r.output()).toMatch(/pages: sign-in refused: /);
    expect(carried(r.output(), r.addresses)).toEqual([]);
  });

  it.each([
    ["a refusal", (words: string) => new IdentityProviderRefused(words), 403],
    ["an unavailable provider", (words: string) => new IdentityProviderUnavailable(words), 503],
    ["an error of any other kind", (words: string) => new Error(words), 500],
  ] as Array<[string, (words: string) => Error, number]>)(
    "%s that names the provider's address in its message leaves no address in the log or the response",
    async (_name, make, status) => {
      const r = await rig(200, (fake) => ({
        async begin() {
          return { authorizationUrl: `${fake.issuer}/auth`, pending: { state: "s", nonce: "n", verifier: "v" } };
        },
        async complete() {
          throw make(`could not reach ${fake.issuer}/protocol/openid-connect/token`);
        },
      }));
      const started = await request(r.app).get("/session/sign-in");
      const res = await request(r.app).get("/session/callback?code=c&state=s").set("Cookie", loginCookieOf(started));
      expect(res.status).toBe(status);
      expect(res.text).not.toContain(r.fake.issuer);
      expect(r.output()).toMatch(/pages: sign-in (refused|could not be completed|failed): /);
      expect(carried(r.output(), r.addresses)).toEqual([]);
    },
  );
});

describe("the scan finds the address (rule 15: planted at the shapes the service's own lines take)", () => {
  it("in a miss line of the real reporter whose log names where the Conduit report went wrong, the provider's address", async () => {
    const r = await rig("down", undefined, (message, fake) => `${message} (${fake.issuer})`);
    await signInAndOut(r);
    expect(r.reporter.misses).toBe(2);
    expect(carried(r.output(), r.addresses)).toEqual(["the issuer", "the provider's host and port", "the provider's realm path"]);
  });

  it("in a line written to the console, as the refusal line is, found through the capture the real cases use", async () => {
    const r = await rig(200);
    console.error(`pages: sign-in refused: ${r.fake.issuer}`);
    expect(carried(r.output(), r.addresses)).toContain("the issuer");
  });

  it("in a line that names only where the connection failed", async () => {
    const r = await rig(200);
    console.error(`pages: sign-in could not be completed: connect ECONNREFUSED ${new URL(r.fake.issuer).host}`);
    expect(carried(r.output(), r.addresses)).toEqual(["the provider's host and port"]);
  });

  it("and the real output of the same app, before any plant, carries none of the three", async () => {
    const r = await rig(200);
    await signInAndOut(r);
    expect(carried(r.output(), r.addresses)).toEqual([]);
  });
});
