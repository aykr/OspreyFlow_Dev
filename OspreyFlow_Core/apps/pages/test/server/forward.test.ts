/**
 * The page service forwards `/v1` over HTTP, with the person's token kept on the server, uploads included
 * (ADR-152 decision 5; slice PL10). Every case is a real HTTP request through the service's own server,
 * started as `main.ts` starts it (a Node client with a signed session cookie, nothing tidied on the way:
 * a path is written to the socket exactly as given). The Conduit is a fake HTTP server that RECORDS every
 * request (method, raw path, query, every header and raw header, the body's length and hash, whether the
 * body arrived whole or was cut) and COUNTS connections, so a refusal by the page service shows as none.
 *
 * WHICH TEST FAILS IF THE FORWARDER LEAKS A HEADER OR BUFFERS AN UPLOAD (rule 12).
 *  - A forwarder that copies the browser's headers: "reaches the Conduit with the person's bearer and
 *    nothing else the browser sent" (it reads the NAMES the fake received against an allow-list, and
 *    counts raw `Authorization` lines, because Node's own parsing drops a second one).
 *  - A forwarder that leaks a cookie, a token or a session id into a response or a log: "the token, the
 *    cookie and the session id are in no response, no header, no log and no output".
 *  - A forwarder that buffers an upload whole: "a raw upload streams: the Conduit sees bytes before the
 *    browser has finished", which waits for the fake to hold bytes while the client has not yet ended.
 *  - A forwarder that sends a multipart envelope on: "a browser's form post to a raw upload route arrives
 *    as raw bytes", which hashes what the fake received against the file part alone.
 *
 * HOW THE REAL CONDUIT REFUSES (rule 15; `services/api/app.py`). The fake refuses what it refuses:
 *  - no `Authorization: Bearer`, or one it does not know: 401 `{"detail": ...}`; a token in the URL
 *    (`token=`, `access_token=`) is ignored, so refused as missing;
 *  - on a raw upload route: a declared `Content-Length` over its limit is 413 `{"detail": "That file is
 *    larger than the upload limit."}` before the body is read; a body that streams past it is the same 413;
 *    a missing `name` is 422 (FastAPI's own body, `detail` a list); and it checks NO content type on those
 *    routes (a fake stricter than the real one would mislead).
 * What these cases cannot prove (a real Conduit through the forwarder: a real 401, a real 413 at the default
 * cap, an upload under the cap, the 1 MB question in the front proxy's own configuration) is OWED to a live
 * stack, and is a backlog row.
 *
 * NOT CARRIED, and said so: the Conduit's one multipart route, `/v1/investigations/{id}/sites`, answers 415
 * here (the owner's ruling is needed: "multipart in, raw out" does not fit a route that takes multipart).
 * Nor is `/rules/import`: it takes JSON (the two files' text), not a raw file, so a browser's form post to it
 * is 415 too.
 */
import { createHash, randomBytes } from "node:crypto";
import { createServer, request as httpRequest } from "node:http";
import type { IncomingHttpHeaders, IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it, vi } from "vitest";

import { loadConfig } from "../../server/config.js";
import { refusedTarget } from "../../server/forward.js";
import type { IdentityProvider } from "../../server/identity.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { captureOutput } from "../support/capture.js";
import { noSessionEvents } from "../support/noSessionEvents.js";
import { testClock } from "../support/clock.js";
import type { TestClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request as pageRequest, TEST_SESSION_SECRET } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

vi.setConfig({ testTimeout: 30_000 });

const SECRET_NAME = "OSPREY_PAGES_SESSION_SECRET";
const ORIGIN = "https://osprey.test";
const REFUSED_FILE = "That file is larger than the upload limit.";

// --- helpers ----------------------------------------------------------------------------------------------

async function until(what: string, condition: () => boolean, ms = 4000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (data: Buffer | string): string => createHash("sha256").update(data).digest("hex");

/** Shaped like a signed access token; made now, at random, written nowhere (rule 15). */
function mintToken(): string {
  return `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`;
}

/** The deterministic body `/v1/large` sends, so a test can hash what it should have received. */
const LARGE_CHUNK = 64 * 1024;
const LARGE_CHUNKS = 128; // 8 MiB
function largeChunk(index: number): Buffer {
  return Buffer.alloc(LARGE_CHUNK, index % 251);
}
function largeHash(): string {
  const hash = createHash("sha256");
  for (let i = 0; i < LARGE_CHUNKS; i += 1) hash.update(largeChunk(i));
  return hash.digest("hex");
}

// --- the fake Conduit --------------------------------------------------------------------------------------

interface Seen {
  method: string;
  /** The request target as it reached the fake: path and query, exactly. */
  url: string;
  path: string;
  query: string;
  headers: IncomingHttpHeaders;
  rawHeaders: string[];
  received: number;
  sha256?: string;
  /** The body, kept only while it is small (64 KiB), so a test can read what was sent on. */
  bodyText: string;
  /** The whole body arrived. */
  complete: boolean;
  /** The connection went before the body or the response was finished. */
  aborted: boolean;
  finishedAt?: number;
  /** The browser (the page service's client) went while the response was still being written. */
  clientGone: boolean;
}

/** The raw upload routes the real Conduit has (`app.py`): the body is the file's bytes, the name is in the query. */
const RAW_ROUTES = [
  { label: "an ingest source file", method: "POST", path: "/v1/investigations/inv-1/ingest/source-files", extra: {} },
  {
    label: "a board node's picture",
    method: "PUT",
    path: "/v1/investigations/inv-1/boards/b-1/nodes/n-1/picture",
    extra: { marking: "OFFICIAL", source_note: "a synthetic note" },
  },
  {
    label: "a node's picture",
    method: "PUT",
    path: "/v1/investigations/inv-1/nodes/n-1/picture",
    extra: { classification: "OFFICIAL", legal_basis: "synthetic" },
  },
  {
    label: "a document",
    method: "POST",
    path: "/v1/investigations/inv-1/documents",
    extra: { classification: "OFFICIAL", legal_basis: "synthetic" },
  },
] as const;

function isRawRoute(method: string, path: string): boolean {
  return RAW_ROUTES.some((r) => r.method === method && r.path === path);
}

class FakeConduit {
  /** TCP connections of any kind: a refusal by the page service must show here as none at all. */
  tcp = 0;
  readonly seen: Seen[] = [];
  readonly tokens = new Set<string>();
  /** The real Conduit's limit (`OSPREY_INGEST_MAX_UPLOAD_BYTES`), here a small one a test can set. */
  uploadCap = 512 * 1024 * 1024;
  port = 0;
  private readonly http: Server;

  constructor() {
    this.http = createServer((req, res) => this.onRequest(req, res));
    this.http.on("connection", () => {
      this.tcp += 1;
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

  /** Requests that reached a route (every one, in order). */
  get last(): Seen {
    const seen = this.seen[this.seen.length - 1];
    if (!seen) throw new Error("the fake Conduit saw no request");
    return seen;
  }

  /** The whole of what the fake received, as one string to search. */
  everythingSeen(): string {
    return JSON.stringify(this.seen.map((s) => ({ url: s.url, headers: s.headers, body: s.bodyText })));
  }

  private json(res: ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}): void {
    const text = JSON.stringify(body);
    res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(text), ...headers });
    res.end(text);
  }

  private onRequest(req: IncomingMessage, res: ServerResponse): void {
    const url = req.url ?? "";
    const [path = "", ...rest] = url.split("?");
    const query = rest.join("?");
    const seen: Seen = {
      method: req.method ?? "",
      url,
      path,
      query,
      headers: req.headers,
      rawHeaders: req.rawHeaders,
      received: 0,
      bodyText: "",
      complete: false,
      aborted: false,
      clientGone: false,
    };
    this.seen.push(seen);
    const hash = createHash("sha256");
    let answered = false;
    const answer = (status: number, body: unknown, headers: Record<string, string> = {}): void => {
      if (answered) return;
      answered = true;
      this.json(res, status, body, headers);
    };

    res.on("close", () => {
      if (!res.writableEnded) seen.clientGone = true;
    });
    req.on("error", () => {
      seen.aborted = true;
    });
    req.on("aborted", () => {
      seen.aborted = true;
    });

    // The credential: a bearer in the header or nothing. A `token` in the URL is ignored.
    const header = req.headers["authorization"] ?? "";
    const bearer = header.toLowerCase().startsWith("bearer ") ? header.slice("bearer ".length) : "";
    const known = bearer !== "" && this.tokens.has(bearer);
    if (!known) {
      answer(401, { detail: "Could not validate credentials" });
      req.resume();
      return;
    }

    const raw = isRawRoute(seen.method, path);
    if (raw) {
      // Before the body is read: a declared length over the limit (`app.py`, the first lines of each route).
      const declared = req.headers["content-length"];
      if (declared !== undefined && /^\d+$/.test(declared) && Number(declared) > this.uploadCap) {
        answer(413, { detail: REFUSED_FILE });
        req.resume();
        return;
      }
    }

    req.on("data", (chunk: Buffer) => {
      seen.received += chunk.length;
      if (seen.received <= 64 * 1024) seen.bodyText += chunk.toString("latin1");
      hash.update(chunk);
      if (raw && seen.received > this.uploadCap) answer(413, { detail: REFUSED_FILE });
    });
    req.on("end", () => {
      seen.complete = true;
      seen.sha256 = hash.digest("hex");
      if (!answered) this.route(req, res, seen, answer);
    });
  }

  private route(
    req: IncomingMessage,
    res: ServerResponse,
    seen: Seen,
    answer: (status: number, body: unknown, headers?: Record<string, string>) => void,
  ): void {
    const { path } = seen;
    const params = new URLSearchParams(seen.query);
    const finish = (): void => {
      seen.finishedAt = Date.now();
      res.end();
    };

    if (isRawRoute(seen.method, path)) {
      // The real routes: `name` is required (422, FastAPI's list-shaped `detail`); no content type is checked.
      if (!params.get("name")) {
        answer(422, { detail: [{ type: "missing", loc: ["query", "name"], msg: "Field required" }] });
        return;
      }
      answer(201, { name: params.get("name"), size: seen.received, sha256: seen.sha256, query: seen.query });
      return;
    }
    if (path.startsWith("/v1/echo")) {
      answer(200, { method: seen.method, url: seen.url, headers: seen.headers, length: seen.received, sha256: seen.sha256 });
      return;
    }
    if (path === "/v1/ok") {
      answer(200, { ok: true });
      return;
    }
    if (path === "/v1/json") {
      res.writeHead(200, { "Content-Type": seen.headers["content-type"] ?? "application/json" });
      // Echo the body back by hash and length; the body itself comes from the client's own copy.
      res.end(JSON.stringify({ length: seen.received, sha256: seen.sha256, contentLength: seen.headers["content-length"] ?? null }));
      return;
    }
    const status = /^\/v1\/status\/(\d{3})$/.exec(path);
    if (status) {
      answer(Number(status[1]), { detail: `The Conduit's own words for ${status[1]}.` });
      return;
    }
    if (path === "/v1/redirect") {
      res.writeHead(302, { Location: "/v1/echo/after-the-redirect", "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "moved" }));
      return;
    }
    if (path === "/v1/located") {
      res.writeHead(200, { Location: "http://elsewhere.test/", "Content-Type": "application/json" });
      res.end("{}");
      return;
    }
    if (path === "/v1/headers") {
      res.writeHead(200, {
        "Content-Type": "application/pdf",
        "Content-Disposition": 'attachment; filename="rule.pdf"',
        "X-Guide-Version": "0.6.2",
        "Set-Cookie": "conduit_cookie=conduit_cookie_value; Path=/",
        "X-Conduit-Internal": "an internal header",
        "WWW-Authenticate": "Bearer realm=conduit",
        "Cache-Control": "public, max-age=999",
        "X-Powered-By": "the fake",
      });
      res.end("%PDF-synthetic");
      return;
    }
    if (path === "/v1/empty") {
      res.writeHead(204);
      res.end();
      return;
    }
    if (path === "/v1/large") {
      res.writeHead(200, { "Content-Type": "application/octet-stream" });
      let i = 0;
      const next = (): void => {
        while (i < LARGE_CHUNKS) {
          if (!res.write(largeChunk(i++))) {
            res.once("drain", next);
            return;
          }
        }
        finish();
      };
      next();
      return;
    }
    if (path === "/v1/pieces" || path === "/v1/events" || path === "/v1/trickle") {
      const sse = path === "/v1/events";
      const gap = path === "/v1/trickle" ? 400 : 150;
      res.writeHead(200, { "Content-Type": sse ? "text/event-stream" : "application/octet-stream" });
      let n = 0;
      const tick = (): void => {
        if (n === 5 || (path === "/v1/trickle" && n === 4)) {
          finish();
          return;
        }
        res.write(sse ? `data: ${n}\n\n` : Buffer.alloc(1024, n));
        n += 1;
        setTimeout(tick, gap);
      };
      tick();
      return;
    }
    if (path === "/v1/forever") {
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      const timer = setInterval(() => res.write(": keep-alive\n\n"), 30);
      res.on("close", () => clearInterval(timer));
      return;
    }
    if (path === "/v1/hang") return; // never answers
    if (path === "/v1/reset") {
      req.socket.destroy();
      return;
    }
    answer(404, { detail: "Not Found" });
  }

  async stop(): Promise<void> {
    await new Promise<void>((resolve) => {
      this.http.close(() => resolve());
      this.http.closeAllConnections();
    });
  }
}

// --- the browser: a Node client that writes the request exactly as given -------------------------------------

interface Reply {
  status: number;
  headers: IncomingHttpHeaders;
  rawHeaders: string[];
  body: Buffer;
  text: string;
  /** When each piece of the body arrived, and how long it was. */
  chunks: Array<{ at: number; length: number }>;
  json(): Record<string, unknown>;
}

interface Call {
  req: ReturnType<typeof httpRequest>;
  reply: Promise<Reply>;
  write(data: Buffer | string): Promise<void>;
  end(): void;
}

const clientRequests: Array<ReturnType<typeof httpRequest>> = [];

function open(port: number, options: { method?: string; path: string; headers?: Record<string, string> }): Call {
  const req = httpRequest({ host: "127.0.0.1", port, method: options.method ?? "GET", path: options.path, headers: options.headers, agent: false });
  clientRequests.push(req);
  let got = false;
  const reply = new Promise<Reply>((resolve, reject) => {
    req.on("response", (res) => {
      got = true;
      const parts: Buffer[] = [];
      const chunks: Reply["chunks"] = [];
      const done = (): void => {
        const body = Buffer.concat(parts);
        resolve({
          status: res.statusCode ?? 0,
          headers: res.headers,
          rawHeaders: res.rawHeaders,
          body,
          text: body.toString("utf8"),
          chunks,
          json: () => JSON.parse(body.toString("utf8")) as Record<string, unknown>,
        });
      };
      res.on("data", (chunk: Buffer) => {
        parts.push(chunk);
        chunks.push({ at: Date.now(), length: chunk.length });
      });
      res.on("end", done);
      res.on("error", done);
      res.on("close", done);
    });
    req.on("error", (error) => {
      // Once the answer is in, a reset of the connection behind it (a refusal that did not read the rest) is not news.
      if (!got) reject(error);
    });
  });
  // An unhandled rejection from a reply nobody awaited (a request the test destroyed) must not fail the run.
  reply.catch(() => undefined);
  req.flushHeaders();
  return {
    req,
    reply,
    write: (data) =>
      new Promise<void>((resolve) => {
        req.write(data, () => resolve());
      }),
    end: () => req.end(),
  };
}

/** A whole request in one go. A string or buffer body is written and ended. */
function call(
  port: number,
  options: { method?: string; path: string; headers?: Record<string, string>; body?: Buffer | string },
): Promise<Reply> {
  // Node's client sends a body with no length as chunked only for some methods; a whole body here has its length.
  const headers = { ...options.headers };
  if (options.body !== undefined && !Object.keys(headers).some((h) => h.toLowerCase() === "content-length")) {
    headers["Content-Length"] = String(Buffer.byteLength(options.body));
  }
  const c = open(port, { ...options, headers });
  if (options.body !== undefined) c.req.write(options.body);
  c.end();
  return c.reply;
}

// --- the page service, started as `main.ts` starts it --------------------------------------------------------

interface Person {
  who: string;
  accessToken: string;
  cookie: string;
  csrf: string;
}

interface Pages {
  port: number;
  clock: TestClock;
  store: MemorySessionStore;
  running: Running;
  base: string;
  io: { logs: string[]; errors: string[]; exits: number[] };
  signIn(who: string): Promise<Person>;
  /** The headers a browser sends with this person's session. `csrf` adds the anti-forgery header. */
  browser(person: Person, extra?: Record<string, string>, csrf?: boolean): Record<string, string>;
  stop(): Promise<void>;
}

interface StartOptions {
  env?: NodeJS.ProcessEnv;
  /** Left out, the fake Conduit's address is set. `null`: no Conduit address at all. */
  conduit?: FakeConduit | null;
}

const everyone: Running[] = [];
const fakes: FakeConduit[] = [];

afterEach(async () => {
  for (const req of clientRequests.splice(0)) req.destroy();
  while (everyone.length) await everyone.pop()?.stop();
  while (fakes.length) await fakes.pop()?.stop();
});

async function conduit(): Promise<FakeConduit> {
  const fake = await FakeConduit.start();
  fakes.push(fake);
  return fake;
}

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
    { store: memory, identityProvider: provider, host: "127.0.0.1", clock, sessionEvents: noSessionEvents },
  );
  if (!running) throw new Error(`the service did not start: ${io.errors.join(" / ")}`);
  everyone.push(running);
  const base = `http://127.0.0.1:${running.port}`;
  return {
    port: running.port,
    clock,
    store: memory,
    running,
    base,
    io,
    stop: () => running.stop(),
    browser: (person, extra = {}, csrf = false) => ({
      Cookie: person.cookie,
      "X-Forwarded-Proto": "https",
      ...(csrf ? { "X-CSRF-Token": person.csrf } : {}),
      ...extra,
    }),
    async signIn(who) {
      const res = await pageRequest(base).get(`/session/sign-in?who=${who}`);
      if (res.status !== 302) throw new Error(`sign-in answered ${res.status}`);
      const accessToken = tokens.get(who);
      if (accessToken === undefined) throw new Error("the provider was not asked");
      const cookie = cookieFrom(res);
      const page = await pageRequest(base).get("/").set("Cookie", cookie);
      return { who, accessToken, cookie, csrf: csrfFromPage(page.text) };
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

/** One person, one fake, one service: the common start. */
async function started(env: NodeJS.ProcessEnv = {}) {
  const fake = await conduit();
  const pages = await startPages({ conduit: fake, env });
  const person = await pages.signIn("a");
  return { fake, pages, person };
}

const JSON_HEADERS = { "Content-Type": "application/json" };

// --- multipart, built by hand ---------------------------------------------------------------------------------

interface Part {
  name: string;
  value?: string;
  filename?: string;
  data?: Buffer;
  contentType?: string;
}

function multipart(parts: Part[]): { contentType: string; body: Buffer; boundary: string } {
  const boundary = `----Osprey${generateSecret(24).replace(/[^A-Za-z0-9]/g, "x")}`;
  const pieces: Buffer[] = [];
  for (const part of parts) {
    let head = `--${boundary}\r\nContent-Disposition: form-data; name="${part.name}"`;
    if (part.filename !== undefined) head += `; filename="${part.filename}"`;
    head += "\r\n";
    if (part.contentType) head += `Content-Type: ${part.contentType}\r\n`;
    head += "\r\n";
    pieces.push(Buffer.from(head, "utf8"), part.data ?? Buffer.from(part.value ?? "", "utf8"), Buffer.from("\r\n"));
  }
  pieces.push(Buffer.from(`--${boundary}--\r\n`));
  return { contentType: `multipart/form-data; boundary=${boundary}`, body: Buffer.concat(pieces), boundary };
}

/** A file's bytes with things in them that look like a boundary without being the boundary. */
function trickyFile(size: number): Buffer {
  return Buffer.concat([
    randomBytes(size),
    Buffer.from("\r\n--not-the-boundary\r\n--\r\n\r\n--"),
    randomBytes(size),
    Buffer.from("\r\n"),
  ]);
}

async function sendInPieces(c: Call, body: Buffer, size: number): Promise<void> {
  for (let at = 0; at < body.length; at += size) await c.write(body.subarray(at, at + size));
  c.end();
}

function authorizationLines(rawHeaders: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < rawHeaders.length; i += 2) {
    if ((rawHeaders[i] ?? "").toLowerCase() === "authorization") out.push(rawHeaders[i + 1] ?? "");
  }
  return out;
}

// ==================================================================================================================

describe("the fake Conduit refuses what the real Conduit refuses (rule 15)", () => {
  async function direct(fake: FakeConduit, options: Parameters<typeof call>[1]) {
    return call(fake.port, options);
  }

  it("no bearer, or one it does not know: 401 with a `detail`; a bearer in the URL is ignored", async () => {
    const fake = await conduit();
    const good = mintToken();
    fake.tokens.add(good);
    for (const path of ["/v1/ok", `/v1/ok?token=${good}`, `/v1/ok?access_token=${good}`]) {
      const res = await direct(fake, { path });
      expect(res.status, path).toBe(401);
      expect(res.json()).toHaveProperty("detail");
    }
    expect((await direct(fake, { path: "/v1/ok", headers: { Authorization: `Bearer ${mintToken()}` } })).status).toBe(401);
    // The control: the same token in the header is served.
    expect((await direct(fake, { path: "/v1/ok", headers: { Authorization: `Bearer ${good}` } })).status).toBe(200);
  });

  it("a raw upload route: a declared length over its limit is 413 before the body is read, a stream past it is 413, a missing name is 422, and no content type is checked", async () => {
    const fake = await conduit();
    fake.uploadCap = 100;
    const good = mintToken();
    fake.tokens.add(good);
    const headers = { Authorization: `Bearer ${good}` };
    const route = "/v1/investigations/inv-1/documents";

    // Declared over the limit, and not a byte sent: answered at once.
    const early = open(fake.port, { method: "POST", path: `${route}?name=a.txt`, headers: { ...headers, "Content-Length": "101" } });
    const refused = await early.reply;
    expect(refused.status).toBe(413);
    expect(refused.json()).toEqual({ detail: REFUSED_FILE });

    // A stream past it with no declared length.
    const streamed = open(fake.port, { method: "POST", path: `${route}?name=a.txt`, headers });
    for (let i = 0; i < 4; i += 1) await streamed.write(Buffer.alloc(40, 1));
    streamed.end();
    const cut = await streamed.reply;
    expect(cut.status).toBe(413);
    expect(cut.json()).toEqual({ detail: REFUSED_FILE });

    // No name: 422 in FastAPI's own shape.
    const noName = await direct(fake, { method: "POST", path: route, headers, body: Buffer.alloc(10) });
    expect(noName.status).toBe(422);
    expect(Array.isArray(noName.json()["detail"])).toBe(true);

    // The real route checks no content type: raw bytes with none, and with a strange one, are both kept.
    const bare = await direct(fake, { method: "POST", path: `${route}?name=a.txt`, headers, body: Buffer.alloc(10) });
    expect(bare.status).toBe(201);
    const strange = await direct(fake, {
      method: "POST",
      path: `${route}?name=a.txt`,
      headers: { ...headers, "Content-Type": "application/x-nothing-at-all" },
      body: Buffer.alloc(10),
    });
    expect(strange.status).toBe(201);
  });
});

describe("a request with a session reaches the Conduit as the person, and as nothing else the browser sent", () => {
  it("carries exactly one Authorization: Bearer with this session's token, and none of the browser's other headers", async () => {
    const { fake, pages, person } = await started();
    const planted = mintToken();
    const res = await call(pages.port, {
      path: "/v1/echo/one?name=a%20b&k=%C3%A9&k=2&empty=",
      headers: pages.browser(person, {
        Authorization: `Bearer ${planted}`,
        Origin: ORIGIN,
        "X-Forwarded-Host": "evil.test",
        "X-Forwarded-Port": "4443",
        "X-Forwarded-Prefix": "/prefix",
        "X-Real-IP": "203.0.113.9",
        "X-CSRF-Token": person.csrf,
        "User-Agent": "a browser",
        "Accept-Language": "en-GB",
        "Accept-Encoding": "gzip, br",
        Referer: `${ORIGIN}/somewhere`,
        Accept: "application/json",
        "X-Request-Id": "req-1234",
      }),
    });
    expect(res.status).toBe(200);
    const seen = fake.last;
    // Exactly one Authorization line (Node's parsing would hide a second), and it is this person's.
    expect(authorizationLines(seen.rawHeaders)).toEqual([`Bearer ${person.accessToken}`]);
    expect(fake.everythingSeen()).not.toContain(planted);
    // The names the Conduit received are an allow-list: anything the browser sent that is not here was copied.
    const allowed = new Set([
      "host",
      "connection",
      "authorization",
      "accept",
      "content-type",
      "content-length",
      "transfer-encoding",
      "x-request-id",
      "x-forwarded-proto",
      "x-forwarded-for",
    ]);
    const extra = Object.keys(seen.headers).filter((h) => !allowed.has(h));
    expect(extra).toEqual([]);
    expect(seen.headers["cookie"]).toBeUndefined();
    expect(seen.headers["origin"]).toBeUndefined();
    expect(seen.headers["x-csrf-token"]).toBeUndefined();
    // The ones that were meant to go.
    expect(seen.headers["accept"]).toBe("application/json");
    expect(seen.headers["x-request-id"]).toBe("req-1234");
    expect(seen.headers["x-forwarded-proto"]).toBe("https");
    expect(seen.rawHeaders.filter((h) => h.toLowerCase() === "x-forwarded-for")).toHaveLength(1);
    expect(seen.rawHeaders.filter((h) => h.toLowerCase() === "x-forwarded-proto")).toHaveLength(1);
    // The host is the Conduit's, never the browser's.
    expect(seen.headers["host"]).toBe(`127.0.0.1:${fake.port}`);
    // The path and the query string arrive as sent, byte for byte.
    expect(seen.url).toBe("/v1/echo/one?name=a%20b&k=%C3%A9&k=2&empty=");
  });

  it("an X-Request-Id that is not a reasonable one is not sent on", async () => {
    const { fake, pages, person } = await started();
    for (const bad of ["x".repeat(300), "has space and \"quotes\"", "a<script>"]) {
      const res = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person, { "X-Request-Id": bad }) });
      expect(res.status).toBe(200);
      expect(fake.last.headers["x-request-id"]).toBeUndefined();
    }
  });

  it("two people's sessions reach their own tokens, never each other's", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const a = await pages.signIn("a");
    const b = await pages.signIn("b");
    expect(a.accessToken).not.toBe(b.accessToken);
    const replies = await Promise.all(
      [a, b, a, b, b, a].map((person) => call(pages.port, { path: `/v1/echo/${person.who}`, headers: pages.browser(person) })),
    );
    expect(replies.every((r) => r.status === 200)).toBe(true);
    for (const seen of fake.seen) {
      const who = seen.path.slice("/v1/echo/".length);
      const person = who === "a" ? a : b;
      expect(authorizationLines(seen.rawHeaders), seen.path).toEqual([`Bearer ${person.accessToken}`]);
    }
    expect(fake.seen).toHaveLength(6);
  });

  it("no session, a forged cookie, a signed-out session and an expired one: 401 in the Conduit's shape, and the Conduit is not contacted", async () => {
    const { fake, pages, person } = await started();
    const noSession = await call(pages.port, { path: "/v1/ok", headers: { "X-Forwarded-Proto": "https" } });
    expect(noSession.status).toBe(401);
    expect(typeof noSession.json()["detail"]).toBe("string");
    expect(String(noSession.json()["detail"]).length).toBeGreaterThan(10);

    const forged = await call(pages.port, {
      path: "/v1/ok",
      headers: { Cookie: `${person.cookie.split("=")[0]}=s%3A${generateSecret(43)}.${generateSecret(43)}`, "X-Forwarded-Proto": "https" },
    });
    expect(forged.status).toBe(401);

    // A state-changing call with no session at all is 401 as well: there is nobody to forward as.
    const post = await call(pages.port, { method: "POST", path: "/v1/ok", headers: { "X-Forwarded-Proto": "https", ...JSON_HEADERS }, body: "{}" });
    expect(post.status).toBe(401);

    // Signed out.
    const out = await pageRequest(pages.base).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: person.csrf });
    expect(out.status).toBe(303);
    const after = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) });
    expect(after.status).toBe(401);

    // An ended one (the idle hour passes with no request).
    const other = await pages.signIn("b");
    pages.clock.advance(3601);
    const ended = await call(pages.port, { path: "/v1/ok", headers: pages.browser(other) });
    expect(ended.status).toBe(401);

    expect(fake.tcp).toBe(0);
    // The control, so that none of the above is "the forwarder is absent": a live session is served.
    const live = await pages.signIn("c");
    expect((await call(pages.port, { path: "/v1/ok", headers: pages.browser(live) })).status).toBe(200);
    expect(fake.tcp).toBe(1);
  });
});

describe("anti-forgery on /v1", () => {
  it("every state-changing method needs the header: 403 as JSON, the Conduit untouched; GET and HEAD need none", async () => {
    const { fake, pages, person } = await started();
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      const none = await call(pages.port, { method, path: "/v1/ok", headers: pages.browser(person, JSON_HEADERS), body: "{}" });
      expect(none.status, method).toBe(403);
      expect(none.headers["content-type"], method).toMatch(/application\/json/);
      expect(typeof none.json()["detail"], method).toBe("string");
      const wrong = await call(pages.port, {
        method,
        path: "/v1/ok",
        headers: pages.browser(person, { ...JSON_HEADERS, "X-CSRF-Token": generateSecret(43) }),
        body: "{}",
      });
      expect(wrong.status, method).toBe(403);
      // A urlencoded form carries the token as `_csrf`; a wrong one is refused like a wrong header.
      const inForm = await call(pages.port, {
        method,
        path: "/v1/ok",
        headers: pages.browser(person, { "Content-Type": "application/x-www-form-urlencoded" }),
        body: `_csrf=${encodeURIComponent(generateSecret(43))}`,
      });
      expect(inForm.status, method).toBe(403);
      // No token at all in a form is refused too.
      const bare = await call(pages.port, {
        method,
        path: "/v1/ok",
        headers: pages.browser(person, { "Content-Type": "application/x-www-form-urlencoded" }),
        body: "a=1",
      });
      expect(bare.status, method).toBe(403);
      // A wrong header is not rescued by a right form field.
      const mixed = await call(pages.port, {
        method,
        path: "/v1/ok",
        headers: pages.browser(person, { "Content-Type": "application/x-www-form-urlencoded", "X-CSRF-Token": generateSecret(43) }),
        body: `_csrf=${encodeURIComponent(person.csrf)}`,
      });
      expect(mixed.status, method).toBe(403);
    }
    expect(fake.tcp).toBe(0);
    // The page routes keep their own HTML refusal.
    const page = await pageRequest(pages.base).post("/session/sign-out").set("Cookie", person.cookie);
    expect(page.status).toBe(403);
    expect(page.headers["content-type"]).toMatch(/text\/html/);

    // With the header, each goes through; GET and HEAD need none.
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      const ok = await call(pages.port, { method, path: "/v1/ok", headers: pages.browser(person, JSON_HEADERS, true), body: "{}" });
      expect(ok.status, method).toBe(200);
      expect(fake.last.method).toBe(method);
    }
    expect((await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) })).status).toBe(200);
    expect((await call(pages.port, { method: "HEAD", path: "/v1/ok", headers: pages.browser(person) })).status).toBe(200);
  });

  it("the token reaches a script through a meta tag in the page, and it is the session's own", async () => {
    const { pages, person } = await started();
    const page = await pageRequest(pages.base).get("/").set("Cookie", person.cookie);
    const meta = /<meta name="csrf-token" content="([^"]+)"/.exec(page.text);
    expect(meta?.[1]).toBe(person.csrf);
    // It works as the header, so a script that reads the tag can call /v1.
    const ok = await call(pages.port, { method: "POST", path: "/v1/ok", headers: pages.browser(person, JSON_HEADERS, true), body: "{}" });
    expect(ok.status).toBe(200);
    // The page with no session says nothing of it, and no /v1 route returns it.
    const none = await pageRequest(pages.base).get("/session/sign-in?who=zz");
    expect(none.text).not.toContain("csrf-token");
    const echoed = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) });
    expect(echoed.text).not.toContain(person.csrf);
  });

  it("a multipart post carries the token as its first part, or in the header", async () => {
    const { fake, pages, person } = await started();
    const route = "/v1/investigations/inv-1/documents";
    const parts = (first: Part[]): Part[] => [
      ...first,
      { name: "classification", value: "OFFICIAL" },
      { name: "legal_basis", value: "synthetic" },
      { name: "file", filename: "a.txt", data: Buffer.from("hello"), contentType: "text/plain" },
    ];
    const post = (form: { contentType: string; body: Buffer }, csrf: boolean) =>
      call(pages.port, { method: "POST", path: route, headers: pages.browser(person, { "Content-Type": form.contentType }, csrf), body: form.body });

    // The first part, no header: the way a scripts-off form can send it.
    const inField = multipart(parts([{ name: "_csrf", value: person.csrf }]));
    expect((await post(inField, false)).status).toBe(201);
    expect(fake.tcp).toBe(1);
    // The header, no field.
    expect((await post(multipart(parts([])), true)).status).toBe(201);
    expect(fake.tcp).toBe(2);
    // Neither, a wrong field, a field that is not the first part, and a wrong header with a right field: all 403, the Conduit untouched.
    const refused: Array<[string, { contentType: string; body: Buffer }, boolean]> = [
      ["no token", multipart(parts([])), false],
      ["a wrong token", multipart(parts([{ name: "_csrf", value: generateSecret(43) }])), false],
      ["an empty token", multipart(parts([{ name: "_csrf", value: "" }])), false],
      ["the token as the second part", multipart([{ name: "classification", value: "OFFICIAL" }, { name: "_csrf", value: person.csrf }, ...parts([]).slice(1)]), false],
      ["the token after the file", multipart([...parts([]).slice(1), { name: "_csrf", value: person.csrf }]), false],
    ];
    for (const [what, form, csrf] of refused) {
      const res = await post(form, csrf);
      expect(res.status, what).toBe(403);
      expect(typeof res.json()["detail"], what).toBe("string");
    }
    const wrongHeader = await call(pages.port, {
      method: "POST",
      path: route,
      headers: pages.browser(person, { "Content-Type": inField.contentType, "X-CSRF-Token": generateSecret(43) }),
      body: inField.body,
    });
    expect(wrongHeader.status).toBe(403);
    expect(fake.tcp).toBe(2);
  });

  it("a multipart post with a wrong or missing token is refused before any byte of the file is read", async () => {
    const { fake, pages, person } = await started();
    const headOf = (form: { body: Buffer }): Buffer =>
      form.body.subarray(0, form.body.indexOf(Buffer.from("\r\n\r\n", "latin1"), form.body.indexOf("filename=")) + 4);
    const file = { name: "file", filename: "big.bin", data: randomBytes(4096) };
    // The control: with the right token as the first part, the call goes on and waits for the file's bytes.
    const good = multipart([{ name: "_csrf", value: person.csrf }, file]);
    const waiting = open(pages.port, { method: "POST", path: RAW_ROUTES[3].path, headers: pages.browser(person, { "Content-Type": good.contentType }) });
    await waiting.write(good.body.subarray(0, headOf(good).length + 200));
    await until("the call to be begun at the Conduit", () => fake.seen.length === 1);
    waiting.req.destroy();

    // A wrong token first, another field first, and the file itself first (no token at all).
    for (const lead of [[{ name: "_csrf", value: generateSecret(43) }], [{ name: "classification", value: "OFFICIAL" }], []]) {
      const form = multipart([...lead, file]);
      const c = open(pages.port, { method: "POST", path: RAW_ROUTES[3].path, headers: pages.browser(person, { "Content-Type": form.contentType }) });
      // Everything up to the file's first byte is sent; the file's bytes and the end of the form never are.
      await c.write(headOf(form));
      expect((await c.reply).status).toBe(403);
    }
    expect(fake.seen).toHaveLength(1);
  });

  it("a urlencoded form: `_csrf` is the token, and it is removed from what is forwarded; the rest of the body is unchanged", async () => {
    const { fake, pages, person } = await started();
    const rest = "a=1&b=%C3%A9+x&empty=&a=2";
    const bodies = [
      `_csrf=${encodeURIComponent(person.csrf)}&${rest}`,
      `a=1&b=%C3%A9+x&_csrf=${encodeURIComponent(person.csrf)}&empty=&a=2`,
      `${rest}&%5Fcsrf=${encodeURIComponent(person.csrf)}`,
    ];
    for (const body of bodies) {
      for (const csrf of [false, true]) {
        const res = await call(pages.port, {
          method: "POST",
          path: "/v1/echo/form",
          headers: pages.browser(person, { "Content-Type": "application/x-www-form-urlencoded" }, csrf),
          body,
        });
        expect(res.status, body).toBe(200);
        expect(fake.last.bodyText, body).toBe(rest);
        expect(fake.last.headers["content-length"], body).toBe(String(rest.length));
        expect(fake.everythingSeen(), body).not.toContain(person.csrf);
        expect(fake.everythingSeen(), body).not.toContain(encodeURIComponent(person.csrf));
      }
    }
  });

  it("the token is never forwarded: not in a header, a body, or the query, whichever way it arrived", async () => {
    const { fake, pages, person } = await started();
    const form = multipart([
      { name: "_csrf", value: person.csrf },
      { name: "classification", value: "OFFICIAL" },
      { name: "file", filename: "a.txt", data: Buffer.from("hello") },
    ]);
    for (const csrf of [false, true]) {
      const res = await call(pages.port, { method: "POST", path: RAW_ROUTES[3].path, headers: pages.browser(person, { "Content-Type": form.contentType }, csrf), body: form.body });
      expect(res.status).toBe(201);
      const params = new URLSearchParams(fake.last.query);
      expect([...params.keys()].sort()).toEqual(["classification", "name"]);
      expect(fake.last.bodyText).toBe("hello");
    }
    // A header, on a JSON call.
    await call(pages.port, { method: "POST", path: "/v1/echo/json", headers: pages.browser(person, JSON_HEADERS, true), body: "{}" });
    expect(fake.everythingSeen()).not.toContain(person.csrf);
    expect(fake.everythingSeen()).not.toContain(encodeURIComponent(person.csrf));
    expect(fake.seen.every((s) => s.headers["x-csrf-token"] === undefined)).toBe(true);
  });
});

describe("path hygiene: the path is decoded once, made canonical, checked, and forwarded as checked", () => {
  const refused = [
    ["an encoded dot segment", "/v1/investigations/%2e%2e/x"],
    ["an encoded dot segment in capitals", "/v1/investigations/%2E%2E/x"],
    ["an encoded slash", "/v1/investigations/a%2fb"],
    ["an encoded slash in capitals", "/v1/investigations/a%2Fb"],
    ["an encoded backslash", "/v1/investigations/a%5cb"],
    ["an encoded backslash in capitals", "/v1/investigations/a%5Cb"],
    ["a backslash", "/v1/investigations/a\\b"],
    ["a dot segment", "/v1/investigations/../healthz"],
    ["a single dot segment", "/v1/investigations/./x"],
    ["a double slash", "/v1/investigations//x"],
    ["an encoded NUL", "/v1/investigations/a%00b"],
    ["an encoded CR", "/v1/investigations/a%0db"],
    ["an encoded LF", "/v1/investigations/a%0Ab"],
    ["a path parameter", "/v1/investigations/a;b/x"],
    ["a path parameter at the end", "/v1/ok;jsessionid=1"],
    ["an encoded path parameter", "/v1/investigations/a%3Bb/x"],
    ["a letter encoded in the ticket route's name", "/v1/ws-t%69cket"],
    ["a letter encoded in the ticket route, with a trailing slash", "/v1/ws-t%69cket/"],
    ["a capital encoded in the ticket route's name", "/v1/ws-%54icket"],
    ["a double-encoded letter in the ticket route", "/v1/ws-t%2569cket"],
    ["a double-encoded letter anywhere", "/v1/echo/%2569"],
    ["a double-encoded percent", "/v1/echo/%2541"],
    ["a letter encoded in the stream's path", "/v1/investigations/inv-1/str%65am"],
    ["a letter encoded in /v1 under the stream's id", "/v1/investigations/%69nv-1/stream/"],
    ["the ticket route in mixed case", "/v1/Ws-Ticket"],
    ["the ticket route in capitals with a trailing slash", "/v1/WS-TICKET/"],
    ["the stream's path in capitals", "/v1/investigations/inv-1/STREAM"],
    ["the stream's path in mixed case with a trailing slash", "/v1/Investigations/inv-1/Stream/"],
    ["a malformed escape", "/v1/echo/%zz"],
    ["a malformed escape at the end", "/v1/echo/a%"],
    ["a byte sequence that is not UTF-8", "/v1/echo/%ff%fe"],
    ["a path parameter after the stream's name", "/v1/investigations/inv-1/stream;x=1"],
    ["a dot segment, encoded, in the ticket route", "/v1/%2e/ws-ticket"],
    ["the stream's path, which CO3 owns", "/v1/investigations/inv-1/stream"],
    ["the stream's path with a trailing slash", "/v1/investigations/inv-1/stream/"],
    ["the ticket route, pointless once the page service holds the bearer", "/v1/ws-ticket"],
    ["the ticket route with a trailing slash", "/v1/ws-ticket/"],
    ["the session-events route, which only the page service's own report may use (SE8c)", "/v1/session-events"],
    ["the session-events route with a trailing slash", "/v1/session-events/"],
    ["the session-events route in mixed case", "/v1/Session-Events"],
    ["the session-events route in capitals with a trailing slash", "/v1/SESSION-EVENTS/"],
    ["a letter encoded in the session-events route's name", "/v1/session-ev%65nts"],
    ["a capital encoded in the session-events route's name", "/v1/%53ession-events"],
    ["a double-encoded letter in the session-events route", "/v1/session-ev%2565nts"],
    ["a dot segment, encoded, in the session-events route", "/v1/%2e/session-events"],
    ["a path parameter after the session-events route's name", "/v1/session-events;x=1"],
    ["a path that only begins like /v1", "/v1x/ok"],
    ["a path in capitals", "/V1/ok"],
    ["a path off /v1", "/api/v1/ok"],
    ["a path that begins with a double slash", "//v1/ok"],
    ["the bare /v1", "/v1"],
  ] as const;

  it.each(refused)("refuses %s with 404 and never contacts the Conduit", async (_name, path) => {
    const { fake, pages, person } = await started();
    // The control, in the same test: a plain /v1 path is forwarded, so a 404 below is the forwarder's, not its absence.
    const control = await call(pages.port, { path: "/v1/echo/a%20b", headers: pages.browser(person) });
    expect(control.status).toBe(200);
    expect(fake.seen).toHaveLength(1);

    for (const method of ["GET", "POST"]) {
      const res = await call(pages.port, {
        method,
        path,
        headers: pages.browser(person, method === "POST" ? JSON_HEADERS : {}, true),
        ...(method === "POST" ? { body: "{}" } : {}),
      });
      expect(res.status, `${method} ${path}`).toBe(404);
    }
    expect(fake.seen).toHaveLength(1);
    expect(fake.tcp).toBe(1);
  });

  it("says so in words, in the Conduit's shape, for a path under /v1", async () => {
    const { pages, person } = await started();
    const res = await call(pages.port, { path: "/v1/investigations/%2e%2e/x", headers: pages.browser(person) });
    expect(res.status).toBe(404);
    expect(res.headers["content-type"]).toMatch(/application\/json/);
    expect(String(res.json()["detail"]).length).toBeGreaterThan(10);
  });

  it("hex in any case is decoded once: what is checked is what the Conduit is sent", async () => {
    const { fake, pages, person } = await started();
    const cases: Array<[string, string]> = [
      ["/v1/echo/f%6Fo", "/v1/echo/foo"],
      ["/v1/echo/f%6fo", "/v1/echo/foo"],
      ["/v1/echo/%41", "/v1/echo/A"],
      ["/v1/echo/a%20b", "/v1/echo/a%20b"],
      ["/v1/echo/caf%C3%A9", "/v1/echo/caf%C3%A9"],
      ["/v1/echo/caf%c3%a9", "/v1/echo/caf%C3%A9"],
      ["/v1/echo/50%25", "/v1/echo/50%25"],
      ["/v1/echo/a%3Fb%23c", "/v1/echo/a%3Fb%23c"],
      ["/v1/echo/a%3ab%40c", "/v1/echo/a:b@c"],
      ["/v1/echo/", "/v1/echo/"],
      ["/v1/ws-ticket-not", "/v1/ws-ticket-not"],
      ["/v1/session-events-not", "/v1/session-events-not"],
      ["/v1/session-events/x", "/v1/session-events/x"],
      ["/v1/investigations/inv-1/streams", "/v1/investigations/inv-1/streams"],
    ];
    for (const [sent, expected] of cases) {
      const res = await call(pages.port, { path: sent, headers: pages.browser(person) });
      // The fake answers its own 404 for a route it has not got: what matters is that the call reached it, as checked.
      expect([200, 404], sent).toContain(res.status);
      expect(fake.last.path, sent).toBe(expected);
      expect(fake.seen.length, sent).toBe(cases.findIndex(([s]) => s === sent) + 1);
    }
    // The neighbours of the deny-listed names are carried: only the names themselves were refused.
    expect(fake.seen).toHaveLength(cases.length);
  });

  it("the query string is not path: it arrives as sent, an encoded slash, dot, backslash or NUL included", async () => {
    const { fake, pages, person } = await started();
    const sent = "/v1/investigations/inv-1/documents?name=a.txt&classification=OFFICIAL&legal_basis=IPA%202016%20s.61%2F62";
    const res = await call(pages.port, { method: "POST", path: sent, headers: pages.browser(person, { "Content-Type": "application/octet-stream" }, true), body: "hello" });
    expect(res.status).toBe(201);
    expect(fake.last.url).toBe(sent);
    expect(new URLSearchParams(fake.last.query).get("legal_basis")).toBe("IPA 2016 s.61/62");
    for (const query of ["who=a%5Cb", "dir=%2e%2e%2fx", "p=%2E", "x=a%00b", "y=%252f"]) {
      const got = await call(pages.port, { path: `/v1/echo/q?${query}`, headers: pages.browser(person) });
      expect(got.status, query).toBe(200);
      expect(fake.last.url, query).toBe(`/v1/echo/q?${query}`);
    }
  });

  it("refuses a raw NUL, CR or LF in the query, and nothing else of it (the function, since Node's parser stops these first)", () => {
    for (const bad of ["a\0b", "a\rb", "a\nb"]) {
      expect(refusedTarget(`/v1/ok?x=${bad}`), JSON.stringify(bad)).toBeDefined();
    }
    expect(refusedTarget("/v1/ok?x=a%2Fb%5Cc%2e%00")).toBeUndefined();
    expect(refusedTarget("/v1/ok?")).toBeUndefined();
    expect(refusedTarget("/v1/ok?x=1?y=2")).toBeUndefined();
  });

  it("answers 405 for a method it does not carry, and never contacts the Conduit", async () => {
    const { fake, pages, person } = await started();
    const control = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) });
    expect(control.status).toBe(200);
    const res = await call(pages.port, { method: "TRACE", path: "/v1/ok", headers: pages.browser(person, {}, true) });
    expect(res.status).toBe(405);
    expect(fake.seen).toHaveLength(1);
  });
});

describe("JSON, and what the Conduit says back", () => {
  it("a JSON body arrives whole with its length recomputed, and the answer comes back", async () => {
    const { fake, pages, person } = await started();
    const body = JSON.stringify({ name: "café", n: [1, 2, 3], pad: "x".repeat(5000) });
    // The browser sends it chunked (no Content-Length): the Conduit is told the real length.
    const c = open(pages.port, { method: "POST", path: "/v1/json", headers: pages.browser(person, JSON_HEADERS, true) });
    const bytes = Buffer.from(body, "utf8");
    await c.write(bytes.subarray(0, 1000));
    await c.write(bytes.subarray(1000));
    c.end();
    const res = await c.reply;
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toMatch(/application\/json/);
    expect(res.json()).toEqual({ length: bytes.length, sha256: sha256(bytes), contentLength: String(bytes.length) });
    expect(fake.last.headers["content-type"]).toBe("application/json");
    expect(fake.last.headers["transfer-encoding"]).toBeUndefined();
  });

  it("a body past OSPREY_PAGES_BODY_MAX_BYTES is 413, declared or not, and the Conduit is not contacted", async () => {
    const { fake, pages, person } = await started({ OSPREY_PAGES_BODY_MAX_BYTES: "2000" });
    const declared = await call(pages.port, { method: "POST", path: "/v1/json", headers: pages.browser(person, JSON_HEADERS, true), body: "x".repeat(2001) });
    expect(declared.status).toBe(413);
    expect(typeof declared.json()["detail"]).toBe("string");
    const c = open(pages.port, { method: "POST", path: "/v1/json", headers: pages.browser(person, JSON_HEADERS, true) });
    for (let i = 0; i < 5; i += 1) await c.write("y".repeat(500));
    c.end();
    expect((await c.reply).status).toBe(413);
    expect(fake.tcp).toBe(0);
    // At the cap it is served.
    const ok = await call(pages.port, { method: "POST", path: "/v1/json", headers: pages.browser(person, JSON_HEADERS, true), body: "z".repeat(2000) });
    expect(ok.status).toBe(200);
  });

  it("the Conduit's 401, 403, 413, 422 and 500 pass through unchanged, body included, and a 401 does not end the session", async () => {
    const { fake, pages, person } = await started();
    for (const status of [401, 403, 413, 422, 500]) {
      const res = await call(pages.port, { path: `/v1/status/${status}`, headers: pages.browser(person) });
      expect(res.status).toBe(status);
      expect(res.json()).toEqual({ detail: `The Conduit's own words for ${status}.` });
    }
    // The Conduit's 401 did not end the person's session here (renewal is PL9's).
    const again = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) });
    expect(again.status).toBe(200);
    const page = await pageRequest(pages.base).get("/").set("Cookie", person.cookie);
    expect(page.status).toBe(200);
    expect(fake.seen).toHaveLength(6);
  });

  it("the Conduit's own 401 for a token it does not know passes through, with its `detail`", async () => {
    const { fake, pages, person } = await started();
    fake.tokens.delete(person.accessToken);
    const res = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) });
    expect(res.status).toBe(401);
    expect(res.json()).toEqual({ detail: "Could not validate credentials" });
    expect(fake.tcp).toBe(1);
  });

  it("a redirect is not followed, and a Location header is never passed", async () => {
    const { fake, pages, person } = await started();
    const redirected = await call(pages.port, { path: "/v1/redirect", headers: pages.browser(person) });
    expect(redirected.status).toBe(302);
    expect(redirected.headers["location"]).toBeUndefined();
    expect(fake.seen.map((s) => s.path)).toEqual(["/v1/redirect"]);
    const located = await call(pages.port, { path: "/v1/located", headers: pages.browser(person) });
    expect(located.status).toBe(200);
    expect(located.headers["location"]).toBeUndefined();
  });

  it("only Content-Type, Content-Disposition and X-Guide-Version are copied back; everything is no-store", async () => {
    const { pages, person } = await started();
    const res = await call(pages.port, { path: "/v1/headers", headers: pages.browser(person) });
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toBe("application/pdf");
    expect(res.headers["content-disposition"]).toBe('attachment; filename="rule.pdf"');
    expect(res.headers["x-guide-version"]).toBe("0.6.2");
    expect(res.headers["cache-control"]).toBe("no-store");
    expect(res.headers["x-conduit-internal"]).toBeUndefined();
    expect(res.headers["www-authenticate"]).toBeUndefined();
    expect(res.headers["x-powered-by"]).toBeUndefined();
    // The Conduit's cookie is not the browser's to hold; the only cookie is the session's own.
    const cookies = [res.headers["set-cookie"] ?? []].flat();
    expect(cookies.join("\n")).not.toContain("conduit_cookie");
    for (const cookie of cookies) expect(cookie.startsWith("osprey_pages=")).toBe(true);
    expect(res.text).toBe("%PDF-synthetic");
  });

  it("a 204 and a HEAD are carried without a body", async () => {
    const { pages, person } = await started();
    const empty = await call(pages.port, { path: "/v1/empty", headers: pages.browser(person) });
    expect(empty.status).toBe(204);
    expect(empty.body).toHaveLength(0);
    const head = await call(pages.port, { method: "HEAD", path: "/v1/ok", headers: pages.browser(person) });
    expect(head.status).toBe(200);
    expect(head.body).toHaveLength(0);
  });
});

describe("a raw upload streams, and is capped as it goes", () => {
  const route = RAW_ROUTES[3];
  const query = "name=report.txt&classification=OFFICIAL&legal_basis=synthetic";

  it("bytes arrive intact, with the browser's own Content-Length and the name in the query", async () => {
    const { fake, pages, person } = await started();
    const data = randomBytes(3 * 1024 * 1024);
    const res = await call(pages.port, {
      method: "POST",
      path: `${route.path}?${query}`,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream", "Content-Length": String(data.length) }, true),
      body: data,
    });
    expect(res.status).toBe(201);
    expect(res.json()).toMatchObject({ name: "report.txt", size: data.length, sha256: sha256(data) });
    expect(fake.last.headers["content-length"]).toBe(String(data.length));
    expect(fake.last.url).toBe(`${route.path}?${query}`);
    expect(authorizationLines(fake.last.rawHeaders)).toEqual([`Bearer ${person.accessToken}`]);
  });

  it("streams: the Conduit sees bytes before the browser has finished sending", async () => {
    const { fake, pages, person } = await started();
    const total = 2 * 1024 * 1024;
    const data = randomBytes(total);
    const c = open(pages.port, {
      method: "POST",
      path: `${route.path}?${query}`,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream", "Content-Length": String(total) }, true),
    });
    await c.write(data.subarray(0, 600 * 1024));
    // The browser has NOT finished; a forwarder that buffers has sent nothing yet.
    await until("bytes at the Conduit while the browser is still sending", () => fake.seen.length === 1 && fake.last.received >= 256 * 1024);
    expect(fake.last.complete).toBe(false);
    await c.write(data.subarray(600 * 1024));
    c.end();
    const res = await c.reply;
    expect(res.status).toBe(201);
    expect(res.json()["sha256"]).toBe(sha256(data));
  });

  it("a declared length over OSPREY_PAGES_UPLOAD_MAX_BYTES is 413 before a byte is read, in the Conduit's words", async () => {
    const { fake, pages, person } = await started({ OSPREY_PAGES_UPLOAD_MAX_BYTES: "1000" });
    // Headers only: nothing of the body is ever sent, so an answer can only be a refusal made before reading.
    const c = open(pages.port, {
      method: "POST",
      path: `${route.path}?${query}`,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream", "Content-Length": "1001" }, true),
    });
    const res = await c.reply;
    expect(res.status).toBe(413);
    expect(res.json()).toEqual({ detail: REFUSED_FILE });
    expect(fake.tcp).toBe(0);
  });

  it("a stream that runs past the cap is cut with 413, and what the Conduit got is not a whole upload", async () => {
    const { fake, pages, person } = await started({ OSPREY_PAGES_UPLOAD_MAX_BYTES: "1000" });
    const c = open(pages.port, {
      method: "POST",
      path: `${route.path}?${query}`,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream" }, true),
    });
    for (let i = 0; i < 5; i += 1) await c.write(Buffer.alloc(400, i));
    c.end();
    const res = await c.reply;
    expect(res.status).toBe(413);
    expect(res.json()).toEqual({ detail: REFUSED_FILE });
    // Cut at once, the Conduit may not even have been asked; if it was, it did not get a whole upload past the cap.
    await sleep(150);
    expect(fake.seen.some((s) => s.complete)).toBe(false);
    expect(fake.seen.every((s) => s.received <= 1000)).toBe(true);
    // At the cap exactly, it is served.
    const exact = await call(pages.port, {
      method: "POST",
      path: `${route.path}?${query}`,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream" }, true),
      body: Buffer.alloc(1000, 7),
    });
    expect(exact.status).toBe(201);
  });

  it("the Conduit's own 413 and 422 pass through unchanged", async () => {
    const { fake, pages, person } = await started();
    fake.uploadCap = 500;
    const big = await call(pages.port, {
      method: "POST",
      path: `${route.path}?${query}`,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream" }, true),
      body: Buffer.alloc(900, 1),
    });
    expect(big.status).toBe(413);
    expect(big.json()).toEqual({ detail: REFUSED_FILE });
    const noName = await call(pages.port, {
      method: "POST",
      path: route.path,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream" }, true),
      body: Buffer.alloc(10),
    });
    expect(noName.status).toBe(422);
    expect(Array.isArray(noName.json()["detail"])).toBe(true);
  });

  it("every raw route is carried with its own method", async () => {
    const { fake, pages, person } = await started();
    for (const r of RAW_ROUTES) {
      const data = randomBytes(2048);
      const res = await call(pages.port, {
        method: r.method,
        path: `${r.path}?name=pic.png`,
        headers: pages.browser(person, { "Content-Type": "image/png" }, true),
        body: data,
      });
      expect(res.status, r.label).toBe(201);
      expect(fake.last.method, r.label).toBe(r.method);
      expect(fake.last.sha256, r.label).toBe(sha256(data));
    }
  });
});

describe("a browser's form upload, scripts off: a multipart post to a raw upload route arrives as raw bytes", () => {
  it.each(RAW_ROUTES)("$label: the file part's bytes, its name as ?name=, the other fields as query fields", async (r) => {
    const { fake, pages, person } = await started();
    const data = trickyFile(20_000);
    const form = multipart([
      ...Object.entries(r.extra).map(([name, value]) => ({ name, value })),
      { name: "file", filename: "rapport été.txt", data, contentType: "text/plain" },
    ]);
    // Sent in small pieces, so that a boundary can fall across two of them.
    const c = open(pages.port, {
      method: "POST",
      path: r.path,
      headers: pages.browser(person, { "Content-Type": form.contentType }, true),
    });
    await sendInPieces(c, form.body, 13);
    const res = await c.reply;
    expect(res.status).toBe(201);
    const seen = fake.last;
    expect(seen.method).toBe(r.method);
    expect(seen.path).toBe(r.path);
    expect(seen.sha256).toBe(sha256(data));
    expect(seen.received).toBe(data.length);
    expect(seen.headers["content-type"] ?? "").not.toMatch(/multipart/i);
    const params = new URLSearchParams(seen.query);
    expect(params.get("name")).toBe("rapport été.txt");
    for (const [name, value] of Object.entries(r.extra)) expect(params.get(name), name).toBe(value);
    expect([...params.keys()].sort()).toEqual(["name", ...Object.keys(r.extra)].sort());
    expect(authorizationLines(seen.rawHeaders)).toEqual([`Bearer ${person.accessToken}`]);
  });

  it("an empty file is a file", async () => {
    const { fake, pages, person } = await started();
    const form = multipart([{ name: "file", filename: "empty.txt", data: Buffer.alloc(0) }]);
    const res = await call(pages.port, {
      method: "POST",
      path: RAW_ROUTES[0].path,
      headers: pages.browser(person, { "Content-Type": form.contentType }, true),
      body: form.body,
    });
    expect(res.status).toBe(201);
    expect(fake.last.received).toBe(0);
    expect(new URLSearchParams(fake.last.query).get("name")).toBe("empty.txt");
  });

  it("multipart to any other route is 415, in words, and the Conduit is not contacted", async () => {
    const { fake, pages, person } = await started();
    const control = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) });
    expect(control.status).toBe(200);
    const form = multipart([{ name: "image", filename: "a.png", data: Buffer.from("x"), contentType: "image/png" }]);
    for (const path of [
      "/v1/investigations/inv-1/sites", // the Conduit's own multipart route: not carried in this slice
      "/v1/investigations/inv-1/rules/import", // JSON, not a raw file
      "/v1/investigations/inv-1/documents/extra",
      "/v1/json",
    ]) {
      for (const method of ["POST", "PUT"]) {
        const res = await call(pages.port, { method, path, headers: pages.browser(person, { "Content-Type": form.contentType }, true), body: form.body });
        expect(res.status, `${method} ${path}`).toBe(415);
        expect(String(res.json()["detail"]).length).toBeGreaterThan(10);
      }
    }
    expect(fake.seen).toHaveLength(1);
  });

  it("a form it cannot translate is refused in words and never leaves a whole upload at the Conduit", async () => {
    const { fake, pages, person } = await started();
    const route = RAW_ROUTES[3].path;
    const headers = (form: { contentType: string }) => pages.browser(person, { "Content-Type": form.contentType }, true);
    const file = { name: "file", filename: "a.txt", data: Buffer.from("some bytes") };
    const cases: Array<[string, { contentType: string; body: Buffer }]> = [
      ["no file part", multipart([{ name: "classification", value: "OFFICIAL" }])],
      ["two file parts", multipart([file, { ...file, name: "second" }])],
      ["a field after the file (the query must be known before the bytes go)", multipart([file, { name: "classification", value: "OFFICIAL" }])],
      ["a file with no name", multipart([{ name: "file", filename: "", data: Buffer.from("x") }])],
    ];
    for (const [what, form] of cases) {
      const res = await call(pages.port, { method: "POST", path: route, headers: headers(form), body: form.body });
      expect(res.status, what).toBe(422);
      expect(String(res.json()["detail"]).length, what).toBeGreaterThan(10);
    }
    // A body that is not a multipart body at all, and one with no boundary.
    const junk = await call(pages.port, { method: "POST", path: route, headers: pages.browser(person, { "Content-Type": "multipart/form-data; boundary=zzz" }, true), body: "nothing like it" });
    expect(junk.status).toBe(422);
    const noBoundary = await call(pages.port, { method: "POST", path: route, headers: pages.browser(person, { "Content-Type": "multipart/form-data" }, true), body: "x" });
    expect(noBoundary.status).toBe(422);
    expect(fake.seen.filter((s) => s.complete && s.received > 0 && s.method === "POST" && s.path === route)).toEqual([]);
  });

  it("a file past OSPREY_PAGES_UPLOAD_MAX_BYTES is 413 as it streams", async () => {
    const { fake, pages, person } = await started({ OSPREY_PAGES_UPLOAD_MAX_BYTES: "1000" });
    const form = multipart([{ name: "file", filename: "big.bin", data: randomBytes(5000) }]);
    const c = open(pages.port, { method: "POST", path: RAW_ROUTES[3].path, headers: pages.browser(person, { "Content-Type": form.contentType }, true) });
    await sendInPieces(c, form.body, 500);
    const res = await c.reply;
    expect(res.status).toBe(413);
    expect(res.json()).toEqual({ detail: REFUSED_FILE });
    if (fake.seen.length > 0) expect(fake.last.complete).toBe(false);
  });
});

describe("responses stream through, never buffered", () => {
  it("a large body arrives intact and in pieces", async () => {
    const { pages, person } = await started();
    const res = await call(pages.port, { path: "/v1/large", headers: pages.browser(person) });
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(LARGE_CHUNK * LARGE_CHUNKS);
    expect(sha256(res.body)).toBe(largeHash());
    expect(res.chunks.length).toBeGreaterThan(4);
  });

  it.each(["/v1/pieces", "/v1/events"])("%s: the first piece reaches the browser long before the Conduit has finished", async (path) => {
    const { fake, pages, person } = await started();
    const res = await call(pages.port, { path, headers: pages.browser(person) });
    expect(res.status).toBe(200);
    expect(res.chunks.length).toBeGreaterThanOrEqual(3);
    const finishedAt = fake.last.finishedAt;
    expect(finishedAt).toBeDefined();
    // A forwarder that holds the body until it is whole delivers its first piece only after the Conduit has finished.
    expect(res.chunks[0]?.at ?? Infinity).toBeLessThan((finishedAt ?? 0) - 200);
    if (path === "/v1/events") expect(res.headers["content-type"]).toBe("text/event-stream");
  });

  it("the browser going away ends the Conduit's response", async () => {
    const { fake, pages, person } = await started();
    const c = open(pages.port, { path: "/v1/forever", headers: pages.browser(person) });
    c.req.end();
    await until("the Conduit to be asked", () => fake.seen.length === 1);
    await sleep(100);
    c.req.destroy();
    await until("the Conduit's response to be dropped", () => fake.last.clientGone);
  });
});

describe("when the Conduit cannot answer", () => {
  it("a Conduit that cannot be reached is 502, in words, and the person's token is not in them", async () => {
    const fake = await conduit();
    const pages = await startPages({ conduit: fake });
    const person = await pages.signIn("a");
    await fake.stop();
    fakes.splice(fakes.indexOf(fake), 1);
    const res = await call(pages.port, { path: "/v1/ok", headers: pages.browser(person) });
    expect(res.status).toBe(502);
    expect(String(res.json()["detail"]).length).toBeGreaterThan(10);
    expect(res.text).not.toContain(person.accessToken);
  });

  it("a Conduit that drops the connection is 502", async () => {
    const { pages, person } = await started();
    const res = await call(pages.port, { path: "/v1/reset", headers: pages.browser(person) });
    expect(res.status).toBe(502);
  });

  it("a Conduit that gives no answer within OSPREY_PAGES_UPSTREAM_TIMEOUT_SECONDS is 504", async () => {
    const { fake, pages, person } = await started({ OSPREY_PAGES_UPSTREAM_TIMEOUT_SECONDS: "1" });
    const began = Date.now();
    const res = await call(pages.port, { path: "/v1/hang", headers: pages.browser(person) });
    expect(res.status).toBe(504);
    expect(String(res.json()["detail"]).length).toBeGreaterThan(10);
    expect(Date.now() - began).toBeGreaterThanOrEqual(900);
    expect(Date.now() - began).toBeLessThan(5000);
    await until("the abandoned request to be dropped", () => fake.last.clientGone);
  });

  it("a long slow body is not cut by a timeout: the time is the silence, not the whole", async () => {
    const { fake, pages, person } = await started({ OSPREY_PAGES_UPSTREAM_TIMEOUT_SECONDS: "1" });
    // An upload sent in four pieces 400 ms apart (1.2 s in all, over the 1 s), answered after the last.
    const c = open(pages.port, {
      method: "POST",
      path: `${RAW_ROUTES[3].path}?name=slow.bin`,
      headers: pages.browser(person, { "Content-Type": "application/octet-stream" }, true),
    });
    for (let i = 0; i < 4; i += 1) {
      await c.write(Buffer.alloc(1024, i));
      await sleep(400);
    }
    c.end();
    const res = await c.reply;
    expect(res.status).toBe(201);
    expect(fake.last.received).toBe(4096);
    // And a slow read: four pieces 400 ms apart.
    const slow = await call(pages.port, { path: "/v1/trickle", headers: pages.browser(person) });
    expect(slow.status).toBe(200);
    expect(slow.body).toHaveLength(4096);
  });

  it("Node's own server timeouts are set so that they cannot cut a long upload or a long read short", async () => {
    const { pages } = await started();
    const server = pages.running.server;
    expect(server.requestTimeout).toBe(0);
    expect(server.timeout).toBe(0);
    expect(server.headersTimeout).toBeGreaterThanOrEqual(60_000);
    expect(server.keepAliveTimeout).toBeGreaterThan(5000);
    expect(server.headersTimeout).toBeGreaterThan(server.keepAliveTimeout);
  });
});

describe("the token, the cookie and the session id are in no response, no header, no log and no output", () => {
  it("through a served call, a Conduit refusal, an unreachable Conduit, a timeout, a refusal of ours and an upload", async () => {
    const captured = captureOutput();
    const seen: string[] = [];
    let pagesIo: Pages["io"] | undefined;
    let secrets: string[] = [];
    try {
      const fake = await conduit();
      const pages = await startPages({ conduit: fake, env: { OSPREY_PAGES_UPSTREAM_TIMEOUT_SECONDS: "1" } });
      pagesIo = pages.io;
      const a = await pages.signIn("a");
      const b = await pages.signIn("b");
      const [cookieValue = ""] = a.cookie.slice(a.cookie.indexOf("=") + 1).split(";");
      const sessionId = decodeURIComponent(cookieValue).slice(2).split(".")[0] ?? "";
      secrets = [a.accessToken, b.accessToken, a.csrf, cookieValue, decodeURIComponent(cookieValue), sessionId, TEST_SESSION_SECRET];
      expect(sessionId).toHaveLength(43);

      // The session cookie the service itself re-issues on a response (a rolling session, PL3) is the one thing
      // allowed to carry the identifier, and only in `Set-Cookie`: that one header line is left out of the scan.
      // Every other header, and every body, is read whole.
      const note = (res: Reply): void => {
        const lines: string[] = [];
        for (let i = 0; i < res.rawHeaders.length; i += 2) {
          const name = res.rawHeaders[i] ?? "";
          const value = res.rawHeaders[i + 1] ?? "";
          if (name.toLowerCase() === "set-cookie" && value.startsWith("osprey_pages=")) continue;
          lines.push(`${name}: ${value}`);
        }
        seen.push(`${lines.join("\n")}\n\n${res.text}`);
      };
      const as = (p: Person, csrf = false) => pages.browser(p, {}, csrf);
      note(await call(pages.port, { path: "/v1/ok", headers: as(a) }));
      note(await call(pages.port, { path: "/v1/headers", headers: as(a) }));
      note(await call(pages.port, { path: "/v1/status/401", headers: as(a) }));
      fake.tokens.delete(b.accessToken);
      note(await call(pages.port, { path: "/v1/ok", headers: as(b) }));
      note(await call(pages.port, { path: "/v1/investigations/%2e%2e/x", headers: as(a) }));
      note(await call(pages.port, { path: "/v1/ok", headers: { "X-Forwarded-Proto": "https" } }));
      note(await call(pages.port, { method: "POST", path: "/v1/ok", headers: { ...as(a), ...JSON_HEADERS }, body: "{}" }));
      note(await call(pages.port, { path: "/v1/hang", headers: as(a) }));
      note(await call(pages.port, { path: "/v1/reset", headers: as(a) }));
      note(await call(pages.port, { method: "POST", path: `${RAW_ROUTES[3].path}?name=a.txt`, headers: as(a, true), body: Buffer.alloc(100) }));
      const form = multipart([{ name: "file", filename: "a.txt", data: Buffer.from("x") }]);
      note(await call(pages.port, { method: "POST", path: "/v1/investigations/inv-1/sites", headers: { ...as(a, true), "Content-Type": form.contentType }, body: form.body }));
      // The anti-forgery token as a form carries it: a urlencoded field, a multipart first part, right and wrong.
      const urlencoded = { ...as(a), "Content-Type": "application/x-www-form-urlencoded" };
      note(await call(pages.port, { method: "POST", path: "/v1/ok", headers: urlencoded, body: `_csrf=${encodeURIComponent(a.csrf)}&k=1` }));
      note(await call(pages.port, { method: "POST", path: "/v1/ok", headers: urlencoded, body: `_csrf=${encodeURIComponent(b.csrf)}&k=1` }));
      const tokenForm = (token: string) =>
        multipart([{ name: "_csrf", value: token }, { name: "file", filename: "a.txt", data: Buffer.from("x") }]);
      for (const token of [a.csrf, b.csrf]) {
        const f = tokenForm(token);
        note(await call(pages.port, { method: "POST", path: RAW_ROUTES[3].path, headers: { ...as(a), "Content-Type": f.contentType }, body: f.body }));
      }
      await fake.stop();
      fakes.splice(fakes.indexOf(fake), 1);
      note(await call(pages.port, { path: "/v1/ok", headers: as(a) }));
      await pages.stop();
    } finally {
      captured.restore();
    }
    const everything = `${seen.join("\n")}\n${captured.text()}\n${(pagesIo?.logs ?? []).join("\n")}\n${(pagesIo?.errors ?? []).join("\n")}`;
    expect(seen.length).toBeGreaterThanOrEqual(16);
    const found: string[] = [];
    for (const secret of secrets) {
      for (const form of [secret, encodeURIComponent(secret), Buffer.from(secret).toString("base64"), Buffer.from(secret).toString("base64url")]) {
        if (form.length >= 12 && everything.includes(form)) found.push(`${form.slice(0, 8)}…`);
      }
      for (const part of secret.split(".").filter((p) => p.length >= 12)) if (everything.includes(part)) found.push(`${part.slice(0, 8)}…`);
    }
    expect(found).toEqual([]);
    // The service did say something of the failures (a fixed phrase and a status), so that the scan above had text to read.
    expect(everything).toMatch(/forward/i);
  });
});

describe("the settings, and the service that refuses to start in words", () => {
  it("the defaults: 32 MiB for a body, 512 MiB for an upload, an hour for the Conduit", () => {
    const config = loadConfig({
      [SECRET_NAME]: TEST_SESSION_SECRET,
      OSPREY_PAGES_CONDUIT_URL: "http://api:8000",
      OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN,
    });
    expect(config.forward).toEqual({
      conduitUrl: "http://api:8000",
      bodyMaxBytes: 32 * 1024 * 1024,
      uploadMaxBytes: 512 * 1024 * 1024,
      upstreamTimeoutSeconds: 3600,
    });
  });

  it.each([
    ["OSPREY_PAGES_BODY_MAX_BYTES", ["0", "-5", "abc", "1.5", "1e3", "99999999999999999999"]],
    ["OSPREY_PAGES_UPLOAD_MAX_BYTES", ["0", "-5", "abc", "1.5", "1e3", "99999999999999999999"]],
    ["OSPREY_PAGES_UPSTREAM_TIMEOUT_SECONDS", ["0", "-5", "abc", "1.5", "1e3", "99999999999"]],
  ])("%s that is not a whole number of at least 1 stops the service, naming the setting", async (name, values) => {
    for (const value of values) {
      const said = await startRefused({ OSPREY_PAGES_CONDUIT_URL: "http://api:8000", OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN, [name]: value });
      expect(said.result, `${name}=${value}`).toBeUndefined();
      expect(said.exits, `${name}=${value}`).toEqual([1]);
      expect(said.errors.join("\n")).toContain(name);
      expect(said.logs.join("\n")).not.toMatch(/listening/);
    }
    // At 1 it starts.
    const ok = await startRefused({ OSPREY_PAGES_CONDUIT_URL: "http://api:8000", OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN, [name]: "1" });
    expect(ok.exits).toEqual([]);
    expect(ok.result).toBeDefined();
  });

  it("with the Conduit's address set and no public origin the service refuses to start, in words (CO3's refusal stays; the forwarder itself reads no origin)", async () => {
    const said = await startRefused({ OSPREY_PAGES_CONDUIT_URL: "http://api:9" });
    expect(said.result).toBeUndefined();
    expect(said.exits).toEqual([1]);
    expect(said.errors.join("\n")).toContain("OSPREY_PAGES_PUBLIC_ORIGIN");
    expect(said.logs.join("\n")).not.toMatch(/listening/);
    // With the address unset the origin is not asked for.
    const ok = await startRefused({});
    expect(ok.exits).toEqual([]);
    expect(ok.result).toBeDefined();
  });

  it("with OSPREY_PAGES_CONDUIT_URL unset the forwarder is absent: every /v1 path answers 404 and nothing is contacted", async () => {
    const fake = await conduit();
    // The control: with the address set, /v1 is served.
    const withIt = await startPages({ conduit: fake });
    const live = await withIt.signIn("a");
    expect((await call(withIt.port, { path: "/v1/ok", headers: withIt.browser(live) })).status).toBe(200);
    const before = fake.tcp;

    const pages = await startPages({ conduit: null, env: { OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN } });
    const person = await pages.signIn("a");
    for (const path of ["/v1/ok", "/v1/echo/x", RAW_ROUTES[3].path, "/v1/investigations/inv-1/stream"]) {
      for (const method of ["GET", "POST"]) {
        const res = await call(pages.port, { method, path, headers: pages.browser(person, JSON_HEADERS, true), ...(method === "POST" ? { body: "{}" } : {}) });
        expect(res.status, `${method} ${path}`).toBe(404);
      }
      // And with no session at all: still 404, not 401: there is nothing here to sign in for.
      const bare = await call(pages.port, { path, headers: { "X-Forwarded-Proto": "https" } });
      expect(bare.status, path).toBe(404);
    }
    expect(fake.tcp).toBe(before);
    expect(pages.io.errors).toEqual([]);
  });
});
