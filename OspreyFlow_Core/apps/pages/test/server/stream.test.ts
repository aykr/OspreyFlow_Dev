/**
 * Live updates through the page service (ADR-152 decision 5; X2 of decision 11; slice CO3).
 *
 * The page service holds the person's tokens on the server, so it is the one that opens the WebSocket
 * to the Conduit, with the person's access token in an `Authorization: Bearer` header, and the browser's
 * socket is only ever to the page service. Every case below is a real HTTP upgrade request through the
 * service's own server (a `ws` client with a Cookie header and an Origin), not a call to a helper, and
 * the Conduit is a fake WebSocket server that RECORDS what it receives and REFUSES what the real
 * Conduit refuses (rule 15; `services/api/app.py`, `_authenticate_websocket` and the `stream` route).
 *
 * HOW THE REAL CONDUIT REFUSES. Every refusal on the stream route is sent BEFORE `websocket.accept()`: a
 * credential it will not serve (close 1008), a principal store that is down (close 1013, "try again
 * later"), a principal admitted to named routes alone, a ticket or principal no longer in standing, and
 * an investigation the person may not read. Under uvicorn a close before accept reaches the client as
 * the handshake answered HTTP 403 with NO body, NO close code and NO reason. So the fake's default
 * refusal is exactly that, for: no Authorization header and no ticket; a bearer it does not know; a
 * ticket it does not know; a `token` or `access_token` in the URL (ignored, so refused as missing); and
 * a store that is down (`storeDown`). The five cannot be told apart by the page service, and a store
 * outage ("try again later", 1013) looks to it exactly like a refused credential (1008). The page
 * service therefore closes the browser's socket 1008, "the Conduit refused the connection", for every
 * HTTP 401 or 403 from the Conduit: the Glass gets the same today through nginx. Telling the two apart
 * needs the Conduit to accept the socket and then close it, so the code survives the handshake: that is
 * a backlog row for the owner (the Conduit is not changed by this slice, ADR-152 X2).
 *
 * A close AFTER accept (the stream running) carries a code and a reason, and the page service relays
 * both unchanged to the browser, 1008 and 1013 included; `closeFrom` is the fake doing that, and the
 * cases that use it say so.
 * The fake checks no Origin, as the real one does not (CORS does not gate a WebSocket).
 *
 * OWED, the live half of `test_the_stream_through_pages_carries_only_what_the_person_may_read`: that the
 * Conduit itself shows a person only what the person may read over this socket (the existing
 * `test_websocket_auth.py` cases, run through the proxy) is proved against the REAL Conduit, which this
 * slice cannot start. The pure half is here: the proxy carries the right person's token and nothing the
 * browser sent. The live proof is a backlog row, due once the page service is wired into a deployment.
 */
import { createServer, request as httpRequest } from "node:http";
import type { IncomingHttpHeaders, IncomingMessage, Server } from "node:http";
import type { AddressInfo } from "node:net";
import type { Duplex } from "node:stream";

import { afterEach, describe, expect, it } from "vitest";
import { WebSocket, WebSocketServer } from "ws";
import type { RawData } from "ws";

import type { IdentityProvider } from "../../server/identity.js";
import { Secret, loadConfig } from "../../server/config.js";
import { createOidcFlow } from "../../server/oidc.js";
import { SIGNED_OUT_WORDS } from "../../server/v1.js";
import { COOKIE_NAME } from "../../server/sessionPolicy.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import type { SessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { captureOutput } from "../support/capture.js";
import { testClock } from "../support/clock.js";
import type { TestClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request, signedCookie, TEST_SESSION_SECRET } from "../support/http.js";
import { noSessionEvents } from "../support/noSessionEvents.js";
import { startFakeKeycloak } from "../support/fakeKeycloak.js";
import type { FakeKeycloak } from "../support/fakeKeycloak.js";
import { CLIENT_ID, ORIGIN as RIG_ORIGIN, REDIRECT_URI, expectNoSecret, signInAs } from "../support/providerRig.js";
import { generateSecret } from "../support/secret.js";

const SECRET_NAME = "OSPREY_PAGES_SESSION_SECRET";
const ORIGIN = "https://osprey.test";
const STREAM_PATH = "/v1/investigations/inv-1/stream";
/** How often the service looks at its open sockets, in a test: the clock is moved by hand, so this is short. */
const CHECK_MS = 10;
/** A credential planted in an address, made now: a refusal must name the setting and never repeat it. */
const CREDENTIAL = generateSecret(16);

// --- waiting ----------------------------------------------------------------------------------------------

async function until(what: string, condition: () => boolean, ms = 3000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

async function settle(ms = 12 * CHECK_MS): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

// --- tokens: made now, at random, written nowhere (rule 15) ------------------------------------------------

/** Shaped like a signed access token (three dot-separated segments, the first starting `eyJ`). */
function mintToken(): string {
  return `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`;
}

// --- the fake Conduit --------------------------------------------------------------------------------------

interface Frame {
  text: string;
  binary: boolean;
  bytes: Buffer;
}

function frameOf(data: RawData, binary: boolean): Frame {
  const bytes = Buffer.isBuffer(data)
    ? data
    : Array.isArray(data)
      ? Buffer.concat(data)
      : Buffer.from(data as ArrayBuffer);
  return { text: bytes.toString("utf8"), binary, bytes };
}

interface Seen {
  url: string;
  headers: IncomingHttpHeaders;
  frames: Frame[];
  closed?: { code: number; reason: string };
  socket?: WebSocket;
}

class FakeConduit {
  /** TCP connections of any kind: a refusal by the page service must show here as none at all. */
  tcp = 0;
  /** Connections the fake accepted (upgraded). */
  readonly seen: Seen[] = [];
  /** Handshakes the fake refused with HTTP 403, before accepting: what each carried, never a frame. */
  readonly refused: Seen[] = [];
  readonly tokens = new Set<string>();
  readonly tickets = new Set<string>();
  /** The principal store is down: the real Conduit closes 1013 before accept, which is HTTP 403 on the wire. */
  storeDown = false;
  /** When set, it alone says whether a bearer is served (`tokens` is not read): the real Conduit verifies the signature and `exp`, and refuses a token that has ended. */
  tokenLive: ((token: string) => boolean) | undefined;
  private readonly http: Server;
  private readonly wss: WebSocketServer;
  port = 0;

  constructor() {
    this.http = createServer();
    this.http.on("connection", () => {
      this.tcp += 1;
    });
    this.wss = new WebSocketServer({ noServer: true });
    this.wss.on("connection", (socket, req) => this.onConnection(socket, req));
    this.http.on("upgrade", (req: IncomingMessage, socket: Duplex, head: Buffer) => {
      if (this.refusal(req) !== null) {
        // As uvicorn answers a close before accept: HTTP 403, empty body, no close code, no reason.
        this.refused.push({ url: req.url ?? "", headers: req.headers, frames: [] });
        socket.on("error", () => undefined);
        socket.end("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        return;
      }
      this.wss.handleUpgrade(req, socket, head, (ws) => this.wss.emit("connection", ws, req));
    });
  }

  static async start(): Promise<FakeConduit> {
    const fake = new FakeConduit();
    await new Promise<void>((resolve) => fake.http.listen(0, "127.0.0.1", resolve));
    fake.port = (fake.http.address() as AddressInfo).port;
    return fake;
  }

  get httpUrl(): string {
    return `http://127.0.0.1:${this.port}`;
  }

  /** Why the real Conduit will not serve a connection (it never says so on the wire), or null when it serves it. */
  private refusal(req: IncomingMessage): string | null {
    if (this.storeDown) return "the principal store is unavailable";
    const header = req.headers["authorization"] ?? "";
    if (header.toLowerCase().startsWith("bearer ")) {
      const bearer = header.slice("bearer ".length);
      if (this.tokenLive !== undefined) return this.tokenLive(bearer) ? null : "invalid or expired bearer token";
      return this.tokens.has(bearer) ? null : "invalid bearer token";
    }
    // Only `ticket` is read from the URL; a `token` or an `access_token` there is ignored.
    const ticket = new URL(req.url ?? "/", "http://fake").searchParams.get("ticket") ?? "";
    if (ticket === "") return "missing bearer token or ws-ticket";
    return this.tickets.has(ticket) ? null : "ws-ticket is missing, expired, or already redeemed";
  }

  private onConnection(socket: WebSocket, req: IncomingMessage): void {
    const seen: Seen = { url: req.url ?? "", headers: req.headers, frames: [], socket };
    this.seen.push(seen);
    socket.on("message", (data, binary) => seen.frames.push(frameOf(data, binary)));
    socket.on("close", (code, reason) => {
      seen.closed = { code, reason: reason.toString("utf8") };
    });
  }

  push(index: number, data: string | Buffer, binary = false): void {
    this.seen[index]?.socket?.send(data, { binary });
  }

  closeFrom(index: number, code: number, reason: string): void {
    this.seen[index]?.socket?.close(code, reason);
  }

  /** The whole of what the fake received on one connection, as one string to search. */
  everythingSeen(): string {
    return JSON.stringify([...this.seen, ...this.refused].map((s) => ({ url: s.url, headers: s.headers, frames: s.frames.map((f) => f.text) })));
  }

  async stop(): Promise<void> {
    for (const client of this.wss.clients) client.terminate();
    await new Promise<void>((resolve) => this.wss.close(() => resolve()));
    await new Promise<void>((resolve) => {
      this.http.close(() => resolve());
      this.http.closeAllConnections();
    });
  }
}

// --- the browser ------------------------------------------------------------------------------------------

interface Browser {
  socket: WebSocket;
  frames: Frame[];
  closed?: { code: number; reason: string };
}

type Outcome = { upgraded: Browser } | { refused: number } | { failed: string };

interface UpgradeOptions {
  path?: string;
  cookie?: string | null;
  /** The Origin header; `null` sends none. */
  origin?: string | null;
  headers?: Record<string, string>;
}

/** A browser's upgrade request, as `ws` makes one: the status of a refusal, or the open socket. */
function upgrade(port: number, options: UpgradeOptions = {}): Promise<Outcome> {
  const origin = options.origin === undefined ? ORIGIN : options.origin;
  const headers: Record<string, string> = { ...options.headers };
  if (options.cookie) headers["Cookie"] = options.cookie;
  return new Promise((resolve) => {
    const socket = new WebSocket(`ws://127.0.0.1:${port}${options.path ?? STREAM_PATH}`, {
      headers,
      ...(origin === null ? {} : { origin }),
    });
    const browser: Browser = { socket, frames: [] };
    socket.on("message", (data, binary) => browser.frames.push(frameOf(data, binary)));
    socket.on("close", (code, reason) => {
      browser.closed = { code, reason: reason.toString("utf8") };
    });
    socket.on("open", () => resolve({ upgraded: browser }));
    socket.on("unexpected-response", (_req, res) => {
      res.resume();
      socket.terminate();
      resolve({ refused: res.statusCode ?? 0 });
    });
    socket.on("error", (error) => resolve({ failed: error.message }));
  });
}

const rawSockets: Duplex[] = [];

/**
 * An upgrade request written exactly as given, for a path a `ws` client would tidy before sending (a dot
 * segment is resolved by the URL parser): the status of the refusal, or "upgraded".
 */
function rawUpgrade(port: number, path: string, cookie: string): Promise<number | "upgraded"> {
  return new Promise((resolve, reject) => {
    const req = httpRequest({
      host: "127.0.0.1",
      port,
      path,
      headers: {
        Connection: "Upgrade",
        Upgrade: "websocket",
        "Sec-WebSocket-Version": "13",
        "Sec-WebSocket-Key": Buffer.from(generateSecret(16)).toString("base64"),
        Origin: ORIGIN,
        Cookie: cookie,
      },
    });
    req.on("response", (res) => {
      res.resume();
      resolve(res.statusCode ?? 0);
    });
    req.on("upgrade", (_res, socket) => {
      rawSockets.push(socket); // kept open until the test ends, as a browser's would be
      resolve("upgraded");
    });
    req.on("error", reject);
    req.end();
  });
}

/** The bare answer to a handshake: its status line's code and its body, as bytes on the wire (no close code exists there). */
function rawAnswer(port: number, path: string, headers: Record<string, string> = {}): Promise<{ status: number; body: string } | "upgraded"> {
  return new Promise((resolve, reject) => {
    const req = httpRequest({
      host: "127.0.0.1",
      port,
      path,
      headers: {
        Connection: "Upgrade",
        Upgrade: "websocket",
        "Sec-WebSocket-Version": "13",
        "Sec-WebSocket-Key": Buffer.from(generateSecret(16)).toString("base64"),
        ...headers,
      },
    });
    req.on("response", (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (chunk: Buffer) => chunks.push(chunk));
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString("utf8") }));
    });
    req.on("upgrade", (_res, socket) => {
      rawSockets.push(socket);
      resolve("upgraded");
    });
    req.on("error", reject);
    req.end();
  });
}

function opened(outcome: Outcome): Browser {
  if (!("upgraded" in outcome)) throw new Error(`expected an upgrade, got ${JSON.stringify(outcome)}`);
  return outcome.upgraded;
}

// --- the page service, started as `main.ts` starts it ---------------------------------------------------------

interface Person {
  who: string;
  accessToken: string;
  cookie: string;
}

interface Pages {
  port: number;
  clock: TestClock;
  store: MemorySessionStore;
  base: string;
  io: { logs: string[]; errors: string[]; exits: number[] };
  signIn(who: string): Promise<Person>;
  stop(): Promise<void>;
}

interface StartOptions {
  env?: NodeJS.ProcessEnv;
  /** Left out, the fake Conduit's address and the public origin are both set. */
  conduit?: FakeConduit | null;
  wrapStore?: (inner: MemorySessionStore) => SessionStore;
}

const everyone: Running[] = [];
const fakes: FakeConduit[] = [];
const sockets: Browser[] = [];

afterEach(async () => {
  for (const raw of rawSockets.splice(0)) raw.destroy();
  for (const browser of sockets.splice(0)) browser.socket.terminate();
  while (everyone.length) await everyone.pop()?.stop();
  while (fakes.length) await fakes.pop()?.stop();
});

async function conduit(): Promise<FakeConduit> {
  const fake = await FakeConduit.start();
  fakes.push(fake);
  return fake;
}

/** The real `main`, with the in-memory store, a free loopback port, a hand-moved clock and a provider that knows two people. */
async function startPages(options: StartOptions = {}): Promise<Pages> {
  const clock = testClock();
  const memory = new MemorySessionStore({ clock });
  const upstream = options.conduit === undefined ? await conduit() : options.conduit;
  const tokens = new Map<string, string>();
  const provider: IdentityProvider = {
    async signIn({ query }) {
      const who = typeof query["who"] === "string" ? query["who"] : "a";
      const accessToken = tokens.get(who) ?? mintToken();
      tokens.set(who, accessToken);
      upstream?.tokens.add(accessToken);
      return {
        subject: `sub-${who}`,
        displayName: `Person ${who}`,
        accessToken,
        refreshToken: mintToken(),
        idpSessionExpiresAt: clock() + 36000 * 1000,
      };
    },
  };
  const io = { logs: [] as string[], errors: [] as string[], exits: [] as number[] };
  const env: NodeJS.ProcessEnv = {
    OSPREY_PAGES_PORT: "0",
    [SECRET_NAME]: TEST_SESSION_SECRET,
    ...(upstream ? { OSPREY_PAGES_CONDUIT_URL: upstream.httpUrl, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN } : {}),
    ...options.env,
  };
  const running = await main(
    env,
    { log: (m) => void io.logs.push(m), error: (m) => void io.errors.push(m), exit: (c) => void io.exits.push(c) },
    {
      store: options.wrapStore ? options.wrapStore(memory) : memory,
      identityProvider: provider,
      host: "127.0.0.1",
      clock,
      streamCheckMs: CHECK_MS,
      sessionEvents: noSessionEvents,
    },
  );
  if (!running) throw new Error(`the service did not start: ${io.errors.join(" / ")}`);
  everyone.push(running);
  const base = `http://127.0.0.1:${running.port}`;
  return {
    port: running.port,
    clock,
    store: memory,
    base,
    io,
    stop: () => running.stop(),
    async signIn(who) {
      const res = await request(base).get(`/session/sign-in?who=${who}`);
      if (res.status !== 302) throw new Error(`sign-in answered ${res.status}`);
      const accessToken = tokens.get(who);
      if (accessToken === undefined) throw new Error("the provider was not asked");
      return { who, accessToken, cookie: cookieFrom(res) };
    },
  };
}

/** Starts the service expecting it to refuse; returns what it said. */
async function startRefused(env: NodeJS.ProcessEnv) {
  const io = { logs: [] as string[], errors: [] as string[], exits: [] as number[] };
  const result = await main(
    { OSPREY_PAGES_PORT: "0", [SECRET_NAME]: TEST_SESSION_SECRET, ...env },
    { log: (m) => void io.logs.push(m), error: (m) => void io.errors.push(m), exit: (c) => void io.exits.push(c) },
    { store: new MemorySessionStore(), host: "127.0.0.1" },
  );
  if (result) everyone.push(result);
  return { result, ...io };
}

function connected(fake: FakeConduit, count: number): Promise<void> {
  return until(`${count} connection(s) at the fake Conduit`, () => fake.seen.length >= count);
}

/** Header names `ws` itself sends on an upgrade; anything else reaching the Conduit came from somewhere. */
const WS_OWN_HEADERS = new Set([
  "host",
  "connection",
  "upgrade",
  "sec-websocket-version",
  "sec-websocket-key",
  "sec-websocket-extensions",
  "authorization",
]);

// ==================================================================================================================

describe("the fake Conduit refuses what the real Conduit refuses (rule 15)", () => {
  /** The real shape of a refusal: HTTP 403, an empty body, and the fake never accepted the socket. */
  const refusedBeforeAccept = { status: 403, body: "" };

  async function direct(fake: FakeConduit, path: string, headers: Record<string, string> = {}) {
    return rawAnswer(fake.port, path, headers);
  }

  it("no Authorization header and no ticket: HTTP 403 before accept, no body, no code, no reason", async () => {
    const fake = await conduit();
    expect(await direct(fake, STREAM_PATH)).toEqual(refusedBeforeAccept);
    expect(fake.seen).toHaveLength(0);
    expect(fake.refused).toHaveLength(1);
  });

  it("a bearer in the URL is ignored, so refused as missing; an unknown bearer is refused the same way", async () => {
    const fake = await conduit();
    const good = mintToken();
    fake.tokens.add(good);
    for (const query of [`token=${good}`, `access_token=${good}`]) {
      expect(await direct(fake, `${STREAM_PATH}?${query}`), query.split("=")[0]).toEqual(refusedBeforeAccept);
    }
    expect(await direct(fake, STREAM_PATH, { Authorization: `Bearer ${mintToken()}` })).toEqual(refusedBeforeAccept);
    expect(fake.seen).toHaveLength(0);
    // The control: the same token in the header is served and stays open.
    const served = opened(await upgrade(fake.port, { origin: null, headers: { Authorization: `Bearer ${good}` } }));
    sockets.push(served);
    await settle();
    expect(served.closed).toBeUndefined();
    expect(fake.seen).toHaveLength(1);
  });

  it("a ticket it does not know is refused; one it knows is served", async () => {
    const fake = await conduit();
    fake.tickets.add("ticket-known");
    expect(await direct(fake, `${STREAM_PATH}?ticket=ticket-unknown`)).toEqual(refusedBeforeAccept);
    const good = opened(await upgrade(fake.port, { path: `${STREAM_PATH}?ticket=ticket-known`, origin: null }));
    sockets.push(good);
    await settle();
    expect(good.closed).toBeUndefined();
  });

  it("a principal store that is down refuses the very same way: nothing on the wire tells it from a refused credential", async () => {
    const fake = await conduit();
    const good = mintToken();
    fake.tokens.add(good);
    fake.storeDown = true;
    const outage = await direct(fake, STREAM_PATH, { Authorization: `Bearer ${good}` });
    const unknownCredential = await direct(fake, STREAM_PATH, { Authorization: `Bearer ${mintToken()}` });
    expect(outage).toEqual(refusedBeforeAccept);
    expect(outage).toEqual(unknownCredential);
    expect(fake.seen).toHaveLength(0);
  });
});

describe("test_the_stream_through_pages_carries_only_what_the_person_may_read", () => {
  it("with a session: one connection, the session's own bearer, the path alone, and nothing the browser sent", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const browserBearer = `Bearer ${mintToken()}`;
    const browserMarker = generateSecret(24);
    const queryMarker = generateSecret(24);

    const browser = opened(
      await upgrade(pages.port, {
        path: `${STREAM_PATH}?marker=${queryMarker}`,
        cookie: person.cookie,
        headers: { Authorization: browserBearer, "X-Browser-Marker": browserMarker, "User-Agent": `Agent-${browserMarker}` },
      }),
    );
    sockets.push(browser);
    await connected(fake, 1);
    await settle();

    expect(fake.seen).toHaveLength(1);
    const seen = fake.seen[0] as Seen;
    expect(seen.headers["authorization"]).toBe(`Bearer ${person.accessToken}`);
    expect(seen.url).toBe(STREAM_PATH); // the path alone: no query string, no marker
    expect(seen.headers["cookie"]).toBeUndefined();
    expect(seen.headers["origin"]).toBeUndefined();
    for (const name of Object.keys(seen.headers)) {
      expect(WS_OWN_HEADERS.has(name), `an unexpected header reached the Conduit: ${name}`).toBe(true);
    }
    const everything = fake.everythingSeen();
    for (const browserSent of [person.cookie, person.cookie.split("=")[1] as string, browserBearer, browserMarker, queryMarker]) {
      expect(everything).not.toContain(browserSent);
    }
    expect(fake.tcp).toBe(1);
    expect(browser.closed).toBeUndefined();
  });

  it("text and binary frames pass both ways unchanged, in order, the large ones whole", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    await connected(fake, 1);

    const big = Buffer.alloc(200 * 1024, 7);
    const binary = Buffer.from([0, 1, 2, 3, 250, 251, 255]);
    browser.socket.send('{"last_acknowledged_seq": 41}');
    browser.socket.send(binary, { binary: true });
    browser.socket.send(big, { binary: true });
    browser.socket.send("héllo ✓");
    await until("four frames at the Conduit", () => (fake.seen[0] as Seen).frames.length === 4);
    const received = (fake.seen[0] as Seen).frames;
    expect(received.map((f) => f.binary)).toEqual([false, true, true, false]);
    expect(received[0]?.text).toBe('{"last_acknowledged_seq": 41}');
    expect(received[1]?.bytes.equals(binary)).toBe(true);
    expect(received[2]?.bytes.equals(big)).toBe(true);
    expect(received[3]?.text).toBe("héllo ✓");

    fake.push(0, '{"type":"delta","seq":42}');
    fake.push(0, binary, true);
    fake.push(0, big, true);
    await until("three frames at the browser", () => browser.frames.length === 3);
    expect(browser.frames.map((f) => f.binary)).toEqual([false, true, true]);
    expect(browser.frames[0]?.text).toBe('{"type":"delta","seq":42}');
    expect(browser.frames[1]?.bytes.equals(binary)).toBe(true);
    expect(browser.frames[2]?.bytes.equals(big)).toBe(true);
    expect(fake.seen).toHaveLength(1);
  });

  it("a frame sent at once, before the Conduit has answered, is not lost", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    browser.socket.send("first");
    browser.socket.send("second");
    await until("both frames at the Conduit", () => (fake.seen[0]?.frames.length ?? 0) === 2);
    expect(fake.seen[0]?.frames.map((f) => f.text)).toEqual(["first", "second"]);
  });

  // The RUNNING-stream case: the Conduit accepted the socket and then closes it, so the code and the
  // reason survive, and the page service relays both unchanged (1008 and 1013 included).
  it.each([
    [1008, "no longer permitted"],
    [1013, "try again later"],
    [1000, "finished"],
    [4001, "an application's own code"],
  ])("a close from the running stream (after accept), %i: its code and reason reach the browser unchanged", async (code, reason) => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    await connected(fake, 1);
    fake.closeFrom(0, code, reason);
    await until("the close at the browser", () => browser.closed !== undefined);
    expect(browser.closed).toEqual({ code, reason });
  });

  // The REFUSED-handshake case, which is what the real Conduit does with every refusal (see the header):
  // HTTP 403 before accept. The browser is closed 1008, "the Conduit refused the connection".
  const REFUSED = { code: 1008, reason: "the Conduit refused the connection" };

  it("a person's token the Conduit does not know: refused before accept (HTTP 403), the browser is closed 1008", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    fake.tokens.clear(); // the Conduit no longer knows this token
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    await until("the close at the browser", () => browser.closed !== undefined);
    expect(browser.closed).toEqual(REFUSED);
    expect(fake.seen).toHaveLength(0); // never accepted
    expect(fake.refused).toHaveLength(1);
    expect(fake.refused[0]?.headers["authorization"]).toBe(`Bearer ${person.accessToken}`);
  });

  it("a Conduit whose principal store is down (the real one closes 1013 before accept, HTTP 403 on the wire): the browser is closed 1008, the same as a refused credential", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    fake.storeDown = true; // the person's token is a good one; the Conduit cannot look the person up
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    await until("the close at the browser", () => browser.closed !== undefined);
    // A "try again later" cannot be told from a refusal when it arrives as a bare HTTP 403: see the header.
    expect(browser.closed).toEqual(REFUSED);
    expect(fake.seen).toHaveLength(0);
    expect(fake.refused).toHaveLength(1);
  });

  it("a Conduit that cannot be reached closes the browser's socket 1013", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    await fake.stop();
    fakes.splice(fakes.indexOf(fake), 1);
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    await until("the close at the browser", () => browser.closed !== undefined);
    expect(browser.closed?.code).toBe(1013);
  });

  it("the browser closing closes the Conduit's side, with the browser's code", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    await connected(fake, 1);
    browser.socket.close(4002, "navigated away");
    await until("the close at the Conduit", () => fake.seen[0]?.closed !== undefined);
    expect(fake.seen[0]?.closed).toEqual({ code: 4002, reason: "navigated away" });
  });

  it("two people's sessions reach their own tokens, never each other's", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const a = await pages.signIn("a");
    const b = await pages.signIn("b");
    expect(a.accessToken).not.toBe(b.accessToken);

    const first = opened(await upgrade(pages.port, { cookie: a.cookie }));
    const second = opened(await upgrade(pages.port, { cookie: b.cookie }));
    const third = opened(await upgrade(pages.port, { cookie: a.cookie }));
    sockets.push(first, second, third);
    await connected(fake, 3);
    const bearers = fake.seen.map((s) => s.headers["authorization"]);
    expect(bearers.filter((h) => h === `Bearer ${a.accessToken}`)).toHaveLength(2);
    expect(bearers.filter((h) => h === `Bearer ${b.accessToken}`)).toHaveLength(1);
    expect(bearers).toHaveLength(3);
    // The frames of one person's socket are not the other's.
    first.socket.send("from-a");
    second.socket.send("from-b");
    await until("both frames", () => fake.seen.reduce((n, s) => n + s.frames.length, 0) === 2);
    const byBearer = new Map(fake.seen.map((s) => [s.headers["authorization"], s.frames.map((f) => f.text)] as const));
    expect(byBearer.get(`Bearer ${b.accessToken}`)).toEqual(["from-b"]);
  });

  describe("with no session, or one that has ended: 401, and the Conduit sees no connection at all", () => {
    it("no cookie, an unrelated cookie, a forged signature, a signed unknown identifier, and garbage", async () => {
      const fake = await conduit();
      const pages = await startPages({ conduit: fake });
      const person = await pages.signIn("a");
      const id = decodeURIComponent(person.cookie.split("=")[1] as string).slice(2, 45);
      const forged = `${COOKIE_NAME}=${encodeURIComponent(`s:${id}.${"A".repeat(43)}`)}`;
      const unknown = signedCookie("x".repeat(43)); // a valid signature, for a session nobody has
      const wrongSecret = signedCookie(id, generateSecret(48)); // the real identifier, signed by another key
      for (const cookie of [null, "theme=dark", forged, unknown, wrongSecret, `${COOKIE_NAME}=garbage`, `${COOKIE_NAME}=`]) {
        expect(await upgrade(pages.port, { cookie }), String(cookie)).toEqual({ refused: 401 });
      }
      expect(fake.tcp).toBe(0);
      expect(fake.seen).toHaveLength(0);
    });

    it("a session past its idle hour", async () => {
      const fake = await conduit();
      const pages = await startPages({ conduit: fake });
      const person = await pages.signIn("a");
      pages.clock.advance(3601);
      expect(await upgrade(pages.port, { cookie: person.cookie })).toEqual({ refused: 401 });
      expect(fake.tcp).toBe(0);
    });

    it("a session that was signed out", async () => {
      const fake = await conduit();
      const pages = await startPages({ conduit: fake });
      const person = await pages.signIn("a");
      const page = await request(pages.base).get("/").set("Cookie", person.cookie);
      const out = await request(pages.base)
        .post("/session/sign-out")
        .set("Cookie", person.cookie)
        .type("form")
        .send({ _csrf: csrfFromPage(page.text) });
      expect(out.status).toBe(303);
      expect(await upgrade(pages.port, { cookie: person.cookie })).toEqual({ refused: 401 });
      expect(fake.tcp).toBe(0);
    });

    it("a session store that cannot be read: refused 503, and still no connection", async () => {
      const fake = await conduit();
      let broken = false;
      const pages = await startPages({
        conduit: fake,
        wrapStore: (inner) => ({
          get: (key) => (broken ? Promise.reject(new Error("the store is down")) : inner.get(key)),
          set: (key, value, ttl) => inner.set(key, value, ttl),
          expire: (key, ttl) => inner.expire(key, ttl),
          del: (key) => inner.del(key),
          take: (key) => inner.take(key),
          listKeys: (prefix) => inner.listKeys(prefix),
          claim: (key, value, ttl) => inner.claim(key, value, ttl),
        }),
      });
      const person = await pages.signIn("a");
      broken = true;
      expect(await upgrade(pages.port, { cookie: person.cookie })).toEqual({ refused: 503 });
      expect(fake.tcp).toBe(0);
    });
  });
});

describe("test_an_upgrade_from_another_origin_is_refused_by_pages", () => {
  const refused: Array<[string, string | null]> = [
    ["another origin", "https://evil.test"],
    ["the same host on another port", "https://osprey.test:8443"],
    ["another scheme", "http://osprey.test"],
    ["a trailing slash", "https://osprey.test/"],
    ["a trailing path", "https://osprey.test/stream"],
    ["a longer host that begins with ours", "https://osprey.test.evil.test"],
    ["a subdomain", "https://www.osprey.test"],
    ["a different case", "https://OSPREY.test"],
    ["the opaque origin", "null"],
    ["an empty origin", ""],
    ["no Origin header at all", null],
  ];

  it.each(refused)("%s: 403 before upgrading, and the Conduit sees no connection", async (_name, origin) => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a"); // a valid session: only the origin is wrong
    expect(await upgrade(pages.port, { cookie: person.cookie, origin })).toEqual({ refused: 403 });
    expect(fake.tcp).toBe(0);
    expect(fake.seen).toHaveLength(0);
  });

  it("the deployment's own origin is upgraded (the control)", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie, origin: ORIGIN }));
    sockets.push(browser);
    await connected(fake, 1);
    expect(fake.seen).toHaveLength(1);
  });
});

describe("test_a_bearer_in_the_url_is_still_refused_through_pages", () => {
  it.each(["token", "access_token", "ticket"])("?%s= with no session: 401, and no upstream connection", async (name) => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const signed = mintToken();
    fake.tokens.add(signed); // a proxy that forwarded the URL would be served, so this is a plant, not a formality
    fake.tickets.add(signed);
    expect(await upgrade(pages.port, { path: `${STREAM_PATH}?${name}=${signed}` })).toEqual({ refused: 401 });
    expect(await upgrade(pages.port, { path: `${STREAM_PATH}?${name}=${signed}`, cookie: "theme=dark" })).toEqual({ refused: 401 });
    expect(fake.tcp).toBe(0);
  });

  it("with a session: upgraded, the recorded URL has no query, and the URL's token is nowhere in what the Conduit received", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const urlToken = mintToken();
    const urlTicket = generateSecret(32);
    fake.tokens.add(urlToken);
    fake.tickets.add(urlTicket);
    const browser = opened(
      await upgrade(pages.port, {
        path: `${STREAM_PATH}?token=${urlToken}&access_token=${urlToken}&ticket=${urlTicket}`,
        cookie: person.cookie,
      }),
    );
    sockets.push(browser);
    await connected(fake, 1);
    await settle();
    const seen = fake.seen[0] as Seen;
    expect(seen.url).toBe(STREAM_PATH);
    expect(seen.url).not.toContain("?");
    expect(seen.headers["authorization"]).toBe(`Bearer ${person.accessToken}`);
    const everything = fake.everythingSeen();
    expect(everything).not.toContain(urlToken);
    expect(everything).not.toContain(urlToken.split(".")[1] as string);
    expect(everything).not.toContain(urlTicket);
    expect(browser.closed).toBeUndefined(); // served by the person's own bearer
  });
});

describe("the path, and whether the proxy is there at all", () => {
  it.each([
    ["/", "the root"],
    ["/v1/investigations/inv-1", "no /stream"],
    ["/v1/investigations/inv-1/stream/extra", "a longer path"],
    ["/v1/investigations//stream", "an empty identifier"],
    ["/v1/investigations/inv-1/other", "another leaf"],
    ["/v1/investigations/../stream", "a dot segment"],
    ["/v1/investigations/%2e%2e/stream", "an encoded dot segment"],
    ["/v1/investigations/a%2fb/stream", "an encoded slash"],
    ["/v1/ws-ticket", "the ticket route"],
    ["/healthz", "a page"],
    ["/_test/echo", "a route behind the session"],
  ])("an upgrade on %s (%s): 404 before upgrading", async (path) => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    expect(await upgrade(pages.port, { path, cookie: person.cookie })).toEqual({ refused: 404 });
    expect(fake.tcp).toBe(0);
  });

  it.each(["/v1/investigations/./stream", "/v1/investigations/../stream", "/v1/investigations/.../stream", "/v1/investigations/%2e%2e/stream"])(
    "a raw upgrade request for %s (a client that does not tidy the path): 404, nothing contacted",
    async (path) => {
      const fake = await conduit();
      const pages = await startPages({ conduit: fake });
      const person = await pages.signIn("a");
      expect(await rawUpgrade(pages.port, path, person.cookie)).toBe(404);
      expect(fake.tcp).toBe(0);
    },
  );

  it("the same raw request for an ordinary identifier is upgraded (the control)", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    expect(await rawUpgrade(pages.port, STREAM_PATH, person.cookie)).toBe("upgraded");
    await connected(fake, 1);
    expect(fake.seen[0]?.url).toBe(STREAM_PATH);
  });

  it("a plain GET of the stream path (no upgrade) is not proxied", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    const res = await request(pages.base).get(STREAM_PATH).set("Cookie", person.cookie);
    expect(res.status).toBe(404);
    expect(fake.tcp).toBe(0);
  });

  it("with OSPREY_PAGES_CONDUIT_URL unset the proxy is absent: the stream path answers 404 and nothing is contacted", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: null, env: { OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN } });
    const person = await pages.signIn("a");
    expect(await upgrade(pages.port, { cookie: person.cookie })).toEqual({ refused: 404 });
    expect(fake.tcp).toBe(0);
    expect(pages.io.errors).toEqual([]);
  });
});

describe("idle time and the end of a session close both sides 1008", () => {
  async function open(env: NodeJS.ProcessEnv = {}) {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake, env });
    const person = await pages.signIn("a");
    const browser = opened(await upgrade(pages.port, { cookie: person.cookie }));
    sockets.push(browser);
    await connected(fake, 1);
    return { fake, pages, person, browser };
  }

  async function bothClosed(fake: FakeConduit, browser: Browser) {
    await until("the browser's socket to close", () => browser.closed !== undefined);
    await until("the Conduit's socket to close", () => fake.seen[0]?.closed !== undefined);
    expect(browser.closed?.code).toBe(1008);
    expect(fake.seen[0]?.closed?.code).toBe(1008);
  }

  it("a socket with no frame either way closes after OSPREY_PAGES_STREAM_IDLE_SECONDS; a frame either way starts the time again", async () => {
    const { fake, pages, browser } = await open({ OSPREY_PAGES_STREAM_IDLE_SECONDS: "120" });
    pages.clock.advance(100);
    browser.socket.send("still here");
    await until("the frame at the Conduit", () => (fake.seen[0]?.frames.length ?? 0) === 1);
    pages.clock.advance(100); // 100 s since the browser's frame
    await settle();
    expect(browser.closed).toBeUndefined();
    fake.push(0, "from the Conduit");
    await until("the frame at the browser", () => browser.frames.length === 1);
    pages.clock.advance(100); // 100 s since the Conduit's frame
    await settle();
    expect(browser.closed).toBeUndefined();
    expect(fake.seen[0]?.closed).toBeUndefined();
    pages.clock.advance(30); // 130 s with no frame
    await bothClosed(fake, browser);
  });

  it("the default is an hour", async () => {
    expect(loadConfig({ [SECRET_NAME]: TEST_SESSION_SECRET, OSPREY_PAGES_CONDUIT_URL: "http://api:8000", OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN }).stream?.idleSeconds).toBe(3600);
    const { fake, pages, person, browser } = await open();
    pages.clock.advance(3000);
    await request(pages.base).get("/").set("Cookie", person.cookie); // the session is renewed by the person's own page
    pages.clock.advance(599); // 3599 s with no frame
    await settle();
    expect(browser.closed).toBeUndefined();
    pages.clock.advance(2); // 3601 s
    await bothClosed(fake, browser);
  });

  it("the person's session ending (its idle hour) closes both sides", async () => {
    const { fake, pages, browser } = await open();
    pages.clock.advance(1800);
    fake.push(0, "keeps the socket from idling");
    await until("the frame", () => browser.frames.length === 1);
    pages.clock.advance(1801); // the session is 3601 s old with no page request to renew it
    await bothClosed(fake, browser);
    expect(browser.closed?.reason).not.toBe("");
  });

  it("signing out ends the stream", async () => {
    const { fake, pages, person, browser } = await open();
    const page = await request(pages.base).get("/").set("Cookie", person.cookie);
    const out = await request(pages.base)
      .post("/session/sign-out")
      .set("Cookie", person.cookie)
      .type("form")
      .send({ _csrf: csrfFromPage(page.text) });
    expect(out.status).toBe(303);
    await bothClosed(fake, browser);
  });

  it("the absolute eight hours ends it, however often the session is renewed", async () => {
    const { fake, pages, person, browser } = await open({ OSPREY_PAGES_STREAM_IDLE_SECONDS: "86400" });
    for (let hour = 0; hour < 9; hour += 1) {
      pages.clock.advance(3000);
      await request(pages.base).get("/").set("Cookie", person.cookie);
    }
    await settle();
    expect(browser.closed).toBeUndefined(); // 27 000 s: inside the eight hours
    pages.clock.advance(3000); // 30 000 s: past 28 800
    await bothClosed(fake, browser);
  });

  it("stopping the service closes its open sockets rather than waiting on them", async () => {
    const { fake, pages, browser } = await open();
    await pages.stop();
    await until("the browser's socket to close", () => browser.closed !== undefined);
    await until("the Conduit's socket to close", () => fake.seen[0]?.closed !== undefined);
  });
});

describe("the service refuses to start, in words", () => {
  it("with the Conduit's address set and no public origin", async () => {
    const said = await startRefused({ OSPREY_PAGES_CONDUIT_URL: "http://api:8000" });
    expect(said.result).toBeUndefined();
    expect(said.exits).toEqual([1]);
    const words = said.errors.join("\n");
    expect(words).toContain("OSPREY_PAGES_PUBLIC_ORIGIN");
    expect(words).toContain("OSPREY_PAGES_CONDUIT_URL");
    expect(said.logs.join("\n")).not.toMatch(/listening/);
  });

  it.each([
    ["a trailing slash", "https://osprey.test/"],
    ["a path", "https://osprey.test/pages"],
    ["no scheme", "osprey.test"],
    ["a scheme that is not http or https", "ftp://osprey.test"],
    ["a query", "https://osprey.test?x=1"],
    ["credentials", `https://user:${CREDENTIAL}@osprey.test`],
    ["an empty value", ""],
  ])("with a public origin that has %s", async (_name, origin) => {
    const said = await startRefused({ OSPREY_PAGES_CONDUIT_URL: "http://api:8000", OSPREY_PAGES_PUBLIC_ORIGIN: origin });
    expect(said.result).toBeUndefined();
    expect(said.exits).toEqual([1]);
    expect(said.errors.join("\n")).toContain("OSPREY_PAGES_PUBLIC_ORIGIN");
  });

  it.each([
    ["not an address", "api"],
    ["not http or https", "ftp://api:8000"],
    ["credentials", `http://user:${CREDENTIAL}@api:8000`],
    ["a path", "http://api:8000/v1"],
  ])("with a Conduit address that is %s", async (_name, address) => {
    const said = await startRefused({ OSPREY_PAGES_CONDUIT_URL: address, OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN });
    expect(said.result).toBeUndefined();
    expect(said.exits).toEqual([1]);
    expect(said.errors.join("\n")).toContain("OSPREY_PAGES_CONDUIT_URL");
    expect(said.errors.join("\n")).not.toContain(CREDENTIAL); // never the credential it was given
  });

  it.each(["0", "-5", "abc", "1.5", "99999999"])("with an idle time of %s", async (seconds) => {
    const said = await startRefused({
      OSPREY_PAGES_CONDUIT_URL: "http://api:8000",
      OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN,
      OSPREY_PAGES_STREAM_IDLE_SECONDS: seconds,
    });
    expect(said.result).toBeUndefined();
    expect(said.exits).toEqual([1]);
    expect(said.errors.join("\n")).toContain("OSPREY_PAGES_STREAM_IDLE_SECONDS");
  });

  it("with the public origin set and no Conduit address it starts, and the proxy is absent", async () => {
    const said = await startRefused({ OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN });
    expect(said.exits).toEqual([]);
    expect(said.result).toBeDefined();
  });
});

describe("the access token is in no log, stdout or stderr of the service", () => {
  it("through a served stream, an upstream refusal, an unreachable Conduit, a refused upgrade and a session that ends", async () => {
    const captured = captureOutput();
    let pagesIo: Pages["io"] | undefined;
    const leaked: string[] = [];
    let text = "";
    let tokens: string[] = [];
    try {
      const fake = await conduit();
      const pages = await startPages({ conduit: fake });
      pagesIo = pages.io;
      const a = await pages.signIn("a");
      const b = await pages.signIn("b");
      tokens = [a.accessToken, b.accessToken];

      const served = opened(await upgrade(pages.port, { cookie: a.cookie }));
      sockets.push(served);
      await connected(fake, 1);
      served.socket.send(`a frame that mentions nothing secret`);
      fake.push(0, "and so does this one");
      await until("the frame", () => served.frames.length === 1);

      fake.tokens.delete(b.accessToken); // the Conduit refuses b's token
      const refusedUpstream = opened(await upgrade(pages.port, { cookie: b.cookie }));
      sockets.push(refusedUpstream);
      await until("the close", () => refusedUpstream.closed !== undefined);

      await upgrade(pages.port, { cookie: a.cookie, origin: "https://evil.test" });
      await upgrade(pages.port, { path: `${STREAM_PATH}?token=${a.accessToken}` });
      await upgrade(pages.port, { path: "/nowhere", cookie: a.cookie });

      pages.clock.advance(3601); // the session ends under the open stream
      await until("the close", () => served.closed !== undefined);

      // Then the Conduit goes away altogether.
      const c = await pages.signIn("c");
      tokens.push(c.accessToken);
      await fake.stop();
      fakes.splice(fakes.indexOf(fake), 1);
      const unreachable = opened(await upgrade(pages.port, { cookie: c.cookie }));
      sockets.push(unreachable);
      await until("the close", () => unreachable.closed !== undefined);
      await pages.stop();
    } finally {
      captured.restore();
    }
    text = `${captured.text()}\n${(pagesIo?.logs ?? []).join("\n")}\n${(pagesIo?.errors ?? []).join("\n")}`;
    expect(tokens).toHaveLength(3);
    for (const token of tokens) {
      for (const part of [token, ...token.split(".")]) {
        if (text.includes(part)) leaked.push(`${part.slice(0, 8)}…`);
      }
    }
    expect(leaked).toEqual([]);
    expect(text).not.toContain(TEST_SESSION_SECRET);
  });
});

// ==================================================================================================================
// Renewal reaches the stream (slice PL9b, round 2). The browser's upgrade is handled outside Express, so the app's renewal
// middleware does not run for it: a person whose access token has ended, and whose only request is a reconnect of the stream,
// must still be served with a renewed token, and a refusal by the provider must end the session and not send the old token.

describe("the stream carries a renewed access token, not the one the session was signed in with", () => {
  const LIFE = 300;
  const MARGIN = 60;
  const secrets: Array<{ fake: FakeKeycloak; clientSecret: string }> = [];

  afterEach(async () => {
    while (secrets.length) await secrets.pop()?.fake.stop();
  });

  /** A browser's upgrade from the origin the sign-in's own redirect address is on (the fake provider's client is registered with it). */
  const reconnect = (port: number, options: UpgradeOptions): Promise<Outcome> => upgrade(port, { origin: RIG_ORIGIN, ...options });

  function expOf(token: string): number {
    const payload = JSON.parse(Buffer.from(token.split(".")[1] as string, "base64url").toString("utf8")) as { exp: number };
    return payload.exp;
  }

  /** The real `main` with the real sign-in flow against a fake Keycloak that refuses what Keycloak refuses, and a Conduit that refuses an ended token. */
  async function world() {
    const clientSecret = generateSecret();
    const keycloak = await startFakeKeycloak({ clientId: CLIENT_ID, clientSecret, redirectUri: REDIRECT_URI });
    const held = { fake: keycloak, clientSecret };
    secrets.push(held);
    const upstream = await conduit();
    // The Conduit accepts what the provider issued and has not ended by the provider's clock.
    upstream.tokenLive = (token) => keycloak.issued.some((i) => i.accessToken === token) && expOf(token) > keycloak.nowSeconds();
    const clock = testClock(Date.now());
    const store = new MemorySessionStore({ clock });
    const io = { logs: [] as string[], errors: [] as string[], exits: [] as number[] };
    const running = await main(
      {
        OSPREY_PAGES_PORT: "0",
        [SECRET_NAME]: TEST_SESSION_SECRET,
        OSPREY_PAGES_CONDUIT_URL: upstream.httpUrl,
        OSPREY_PAGES_PUBLIC_ORIGIN: RIG_ORIGIN,
      },
      { log: (m) => void io.logs.push(m), error: (m) => void io.errors.push(m), exit: (c) => void io.exits.push(c) },
      {
        store,
        host: "127.0.0.1",
        clock,
        streamCheckMs: CHECK_MS,
        sessionEvents: noSessionEvents,
        codeFlow: createOidcFlow(
          { issuer: keycloak.issuer, clientId: CLIENT_ID, clientSecret: new Secret(clientSecret), publicOrigin: RIG_ORIGIN },
          { now: clock },
        ),
      },
    );
    if (!running) throw new Error(`the service did not start: ${io.errors.join(" / ")}`);
    everyone.push(running);
    const base = `http://127.0.0.1:${running.port}`;
    return {
      keycloak,
      upstream,
      store,
      io,
      port: running.port,
      base,
      held,
      advance(seconds: number): void {
        clock.advance(seconds);
        keycloak.advance(seconds);
      },
      signIn: () => signInAs({ app: base, fake: keycloak }),
    };
  }

  it("a stream opened after the token's end, with no page request before it, connects with the new token", async () => {
    const w = await world();
    const person = await w.signIn();
    const first = w.keycloak.issued[0]!;
    w.advance(LIFE + 30); // the access token has ended, and the browser has asked the service for nothing since

    const browser = opened(await reconnect(w.port, { cookie: person.cookie }));
    sockets.push(browser);
    await connected(w.upstream, 1);
    await settle();
    expect(w.keycloak.refreshes, "one exchange, with the refresh token held").toEqual([{ refreshToken: first.refreshToken, status: 200 }]);
    const renewed = w.keycloak.issued[1]!;
    expect(w.upstream.seen[0]?.headers["authorization"]).toBe(`Bearer ${renewed.accessToken}`);
    expect(w.upstream.everythingSeen(), "the ended token was never sent").not.toContain(first.accessToken);
    expect(w.upstream.refused, "the Conduit refused nothing").toHaveLength(0);
    expect(browser.closed, "and the stream stays open").toBeUndefined();

    // The session holds the renewed tokens: the next page request is not another exchange.
    const raw = JSON.parse((await w.store.get(`pages-session:${person.id}`)) as string) as { auth: Record<string, unknown> };
    expect(raw.auth["accessToken"]).toBe(renewed.accessToken);
    expect(raw.auth["refreshToken"]).toBe(renewed.refreshToken);
    expect((await request(w.base).get("/").set("Cookie", person.cookie)).status).toBe(200);
    expect(w.keycloak.refreshCalls).toBe(1);
  });

  it("at the margin it renews, and with more than the margin left it does not", async () => {
    const w = await world();
    const person = await w.signIn();
    w.advance(LIFE - MARGIN - 1);
    sockets.push(opened(await reconnect(w.port, { cookie: person.cookie })));
    await connected(w.upstream, 1);
    expect(w.keycloak.refreshCalls).toBe(0);
    expect(w.upstream.seen[0]?.headers["authorization"]).toBe(`Bearer ${w.keycloak.issued[0]!.accessToken}`);
    w.advance(1);
    sockets.push(opened(await reconnect(w.port, { cookie: person.cookie })));
    await connected(w.upstream, 2);
    expect(w.keycloak.refreshCalls).toBe(1);
    expect(w.upstream.seen[1]?.headers["authorization"]).toBe(`Bearer ${w.keycloak.issued[1]!.accessToken}`);
  });

  it("two reconnects and a page request at once after the token's end make one exchange, and the provider keeps the session", async () => {
    const w = await world();
    const person = await w.signIn();
    w.advance(LIFE + 30);
    const [one, two, page] = await Promise.all([
      reconnect(w.port, { cookie: person.cookie }),
      reconnect(w.port, { cookie: person.cookie }),
      request(w.base).get("/").set("Cookie", person.cookie),
    ]);
    sockets.push(opened(one), opened(two));
    expect(page.status).toBe(200);
    await connected(w.upstream, 2);
    expect(w.keycloak.refreshes.map((x) => x.status), "one exchange, never two with one refresh token").toEqual([200]);
    expect(w.keycloak.sessions.get(person.sid)?.ended).toBe(false);
    const renewed = w.keycloak.issued[1]!.accessToken;
    expect(w.upstream.seen.map((s) => s.headers["authorization"])).toEqual([`Bearer ${renewed}`, `Bearer ${renewed}`]);
  });

  it.each([
    ["the provider no longer has the session", (w: Awaited<ReturnType<typeof world>>, sid: string): Promise<void> => Promise.resolve(w.keycloak.endSession(sid))],
    [
      "the provider refuses the client's secret",
      (w: Awaited<ReturnType<typeof world>>): Promise<void> => {
        w.keycloak.clientSecret = generateSecret();
        return Promise.resolve();
      },
    ],
    ["the provider cannot be reached", (w: Awaited<ReturnType<typeof world>>): Promise<void> => w.keycloak.stop()],
  ])("when %s and the token has ended, the socket is closed in the sign-in's words, the session ends and the old token is never sent", async (_name, cause) => {
    const w = await world();
    const person = await w.signIn();
    await cause(w, person.sid);
    w.advance(LIFE + 30);

    const browser = opened(await reconnect(w.port, { cookie: person.cookie }));
    sockets.push(browser);
    await until("the browser's socket to close", () => browser.closed !== undefined);
    expect(browser.closed).toEqual({ code: 1008, reason: SIGNED_OUT_WORDS });
    expect(w.upstream.tcp, "the Conduit was never contacted").toBe(0);
    expect(w.upstream.everythingSeen()).not.toContain(w.keycloak.issued[0]!.accessToken);
    expect(w.store.keys().filter((key) => key.startsWith("pages-session:")), "the session is ended").toEqual([]);

    // The same cookie again: no session, so a plain 401 before anything is opened, and no exchange is made for it.
    const exchanges = w.keycloak.refreshCalls;
    expect(await reconnect(w.port, { cookie: person.cookie })).toEqual({ refused: 401 });
    expect(w.keycloak.refreshCalls).toBe(exchanges);
    expect(w.upstream.tcp).toBe(0);

    // Nothing of a token, the refresh token or the secret in what was said or logged.
    const said = `${browser.closed?.reason ?? ""}\n${w.io.logs.join("\n")}\n${w.io.errors.join("\n")}`;
    expectNoSecret({ fake: w.keycloak, clientSecret: w.held.clientSecret }, said, "the close and the log");
    expect(w.io.errors.filter((line) => line.startsWith("pages: session ended: "))).toHaveLength(1);
  });

  it("an unreachable provider is not an ended session while the token held is good: the stream connects with it", async () => {
    const w = await world();
    const person = await w.signIn();
    await w.keycloak.stop();
    w.advance(LIFE - MARGIN); // inside the margin, not yet ended
    const browser = opened(await reconnect(w.port, { cookie: person.cookie }));
    sockets.push(browser);
    await connected(w.upstream, 1);
    expect(w.upstream.seen[0]?.headers["authorization"]).toBe(`Bearer ${w.keycloak.issued[0]!.accessToken}`);
    await settle();
    expect(browser.closed).toBeUndefined();
    expect(w.store.keys().filter((key) => key.startsWith("pages-session:"))).toEqual([`pages-session:${person.id}`]);
  });

  it("a stream upgrade does not renew for a session it did not authenticate: no cookie, a forged cookie, a wrong origin", async () => {
    const w = await world();
    const person = await w.signIn();
    w.advance(LIFE + 30);
    expect(await reconnect(w.port, {})).toEqual({ refused: 401 });
    expect(await reconnect(w.port, { cookie: signedCookie("A".repeat(43), "not-the-secret-not-the-secret-0000") })).toEqual({ refused: 401 });
    expect(await reconnect(w.port, { cookie: person.cookie, origin: "https://evil.test" })).toEqual({ refused: 403 });
    expect(w.keycloak.refreshCalls, "no exchange was made for any of them").toBe(0);
    expect(w.upstream.tcp).toBe(0);
  });
});
