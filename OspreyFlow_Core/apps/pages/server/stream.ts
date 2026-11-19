/**
 * Live updates through the page service (ADR-152 decision 5; X2 of decision 11; slice CO3).
 *
 * The Glass's live stream is a WebSocket to the Conduit, `GET /v1/investigations/{id}/stream`. The page
 * service holds the person's tokens on the server (their session), so it is the one that opens that socket:
 * the browser's upgrade carries only the page service's session cookie, and the service opens its own
 * socket to the Conduit with the person's access token in an `Authorization: Bearer` header (the Conduit
 * tries the header first, so no ticket is minted). Frames, text and binary, pass both ways unchanged.
 *
 * What is refused, and where, always before the browser's socket is upgraded and before the Conduit is
 * contacted:
 *   - any upgrade on a path but the stream's: 404;
 *   - an `Origin` that is not exactly the deployment's own, or none: 403 (a cookie authenticates the
 *     browser, and CORS does not gate a WebSocket, so this check is the cross-site guard);
 *   - no session, or one that has ended: 401; a session store that cannot be read: 503.
 *
 * What is never forwarded: anything the browser sent. Not its Cookie, not its Authorization, not its Origin,
 * not its subprotocols, not its query string (the forwarded URL is the path alone). The only header the
 * Conduit receives, beyond the ones the WebSocket handshake itself needs, is the person's bearer.
 *
 * Access control stays in the Conduit's adapters (rule 3): the proxy filters nothing and counts nothing;
 * the Conduit shows the person's own principal only what that person may read.
 *
 * An open socket is closed 1008 when no frame has crossed it in either direction for the idle time
 * (`OSPREY_PAGES_STREAM_IDLE_SECONDS`, an hour by default), and when the person's session ends (its idle
 * hour or its absolute eight hours, or a sign-out). The service's clock decides both, so a test moves it by hand.
 */
import { createHmac, timingSafeEqual } from "node:crypto";
import type { IncomingMessage, Server } from "node:http";
import type { Duplex } from "node:stream";

import { WebSocket, WebSocketServer } from "ws";
import type { RawData } from "ws";

import type { StreamSettings } from "./config.js";
import { PagesSessionStore } from "./expressStore.js";
import { COOKIE_NAME } from "./sessionPolicy.js";
import type { SessionRecord } from "./sessionPolicy.js";
import type { SessionStore } from "./sessionStore.js";

export interface StreamDeps {
  /** Absent when `OSPREY_PAGES_CONDUIT_URL` is unset: every upgrade is then answered 404. */
  settings: StreamSettings | undefined;
  store: SessionStore;
  /** The cookie-signing secret: the session cookie is verified exactly as `express-session` signed it. */
  sessionSecret: string;
  /** Milliseconds since the epoch. */
  clock?: () => number;
  /** How often open sockets are looked at, in milliseconds. */
  checkMs?: number;
  /** Where the proxy says what went wrong. It never receives a token, a cookie or an address with a credential. */
  log?: (message: string) => void;
}

export interface StreamProxy {
  /** Closes every open socket (1001) and stops looking at them. */
  close(): void;
}

const STREAM_PATH = /^\/v1\/investigations\/([A-Za-z0-9._~:-]{1,200})\/stream$/;
const DEFAULT_CHECK_MS = 5000;
/** What a browser may send up the socket: `{"last_acknowledged_seq": n}` and the like. */
const MAX_BROWSER_FRAME_BYTES = 1024 * 1024;
/** What may wait for the Conduit's socket to open. */
const MAX_QUEUED_BYTES = 1024 * 1024;
const UPSTREAM_HANDSHAKE_MS = 10_000;
const SESSION_ID = /^[A-Za-z0-9_-]{43}$/;

/** A status line and nothing else: no body, so nothing to say what the service holds. */
function refuse(socket: Duplex, status: number, text: string): void {
  socket.on("error", () => undefined);
  socket.end(`HTTP/1.1 ${status} ${text}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
}

function toBuffer(data: RawData): Buffer {
  if (Buffer.isBuffer(data)) return data;
  if (Array.isArray(data)) return Buffer.concat(data);
  return Buffer.from(data);
}

/** The session cookie's identifier, when the cookie is `express-session`'s signed form (`s:<id>.<signature>`) and the signature is ours. */
function sessionIdFrom(cookieHeader: string | undefined, secret: string): string | undefined {
  if (!cookieHeader) return undefined;
  for (const pair of cookieHeader.split(";")) {
    const at = pair.indexOf("=");
    if (at < 0 || pair.slice(0, at).trim() !== COOKIE_NAME) continue;
    // The first cookie of the name wins, as `cookie.parse` has it.
    let value: string;
    try {
      value = decodeURIComponent(pair.slice(at + 1).trim());
    } catch {
      return undefined;
    }
    if (!value.startsWith("s:")) return undefined;
    const dot = value.lastIndexOf(".");
    if (dot < 0) return undefined;
    const id = value.slice(2, dot);
    const signature = Buffer.from(value.slice(dot + 1));
    const expected = Buffer.from(createHmac("sha256", secret).update(id).digest("base64").replace(/=+$/, ""));
    if (signature.length !== expected.length || !timingSafeEqual(signature, expected)) return undefined;
    return SESSION_ID.test(id) ? id : undefined;
  }
  return undefined;
}

/** A close code that may be sent on the wire; 1005, 1006 and 1015 are reports of a state, never codes to send. */
function sendableCode(code: number): boolean {
  return (code >= 1000 && code <= 1003) || (code >= 1007 && code <= 1014) || (code >= 3000 && code <= 4999);
}

/** A close reason is at most 123 bytes of UTF-8. */
function fitReason(reason: string): string {
  let out = reason;
  while (Buffer.byteLength(out, "utf8") > 123) out = out.slice(0, -1);
  return out;
}

function closeSocket(socket: WebSocket, code: number | undefined, reason: string): void {
  if (socket.readyState === WebSocket.CONNECTING) {
    socket.terminate();
  } else if (socket.readyState === WebSocket.OPEN) {
    if (code === undefined) socket.close();
    else socket.close(code, fitReason(reason));
  }
}

interface Live {
  sid: string;
  lastFrame: number;
  checking: boolean;
  end(code: number | undefined, reason: string): void;
}

export function attachStreamProxy(server: Server, deps: StreamDeps): StreamProxy {
  const clock = deps.clock ?? Date.now;
  const sessions = new PagesSessionStore(deps.store, clock);
  const settings = deps.settings;
  const idleMs = (settings?.idleSeconds ?? 0) * 1000;
  const upstreamBase = settings?.conduitUrl.replace(/^http/, "ws");
  const log = deps.log ?? (() => undefined);
  const live = new Set<Live>();

  const browsers = new WebSocketServer({
    noServer: true,
    maxPayload: MAX_BROWSER_FRAME_BYTES,
    perMessageDeflate: false,
    // The browser's subprotocols are not ours to pick: none is selected, and none is forwarded.
    handleProtocols: () => false,
  });

  /** The session the cookie names, or undefined when there is none, it is not ours or it has ended. */
  function readSession(sid: string): Promise<SessionRecord | undefined> {
    return new Promise((resolve, reject) => {
      sessions.get(sid, (error, session) => {
        if (error) reject(error instanceof Error ? error : new Error("the session store failed"));
        else resolve(session?.auth);
      });
    });
  }

  function bridge(browser: WebSocket, record: SessionRecord, sid: string, id: string): void {
    const connection: Live = {
      sid,
      lastFrame: clock(),
      checking: false,
      end: (code, reason) => {
        finish(code, reason, code);
      },
    };
    let done = false;
    let upstreamOpen = false;
    const queue: Array<{ data: Buffer; binary: boolean }> = [];
    let queued = 0;

    let upstream: WebSocket;
    try {
      upstream = new WebSocket(`${upstreamBase ?? ""}/v1/investigations/${id}/stream`, {
        headers: { Authorization: `Bearer ${record.accessToken}` },
        perMessageDeflate: false,
        handshakeTimeout: UPSTREAM_HANDSHAKE_MS,
        followRedirects: false,
      });
    } catch {
      log("pages: stream: the connection to the Conduit could not be made");
      browser.close(1013, "try again later");
      return;
    }

    /** Ends both sides, once: `browserCode` to the browser, `upstreamCode` to the Conduit. */
    function finish(browserCode: number | undefined, reason: string, upstreamCode: number | undefined): void {
      if (done) return;
      done = true;
      live.delete(connection);
      queue.length = 0;
      closeSocket(browser, browserCode, reason);
      closeSocket(upstream, upstreamCode, reason);
    }

    const touch = (): void => {
      connection.lastFrame = clock();
    };
    live.add(connection);

    upstream.on("open", () => {
      if (done) return;
      upstreamOpen = true;
      for (const frame of queue.splice(0)) upstream.send(frame.data, { binary: frame.binary });
      queued = 0;
    });
    upstream.on("message", (data, binary) => {
      touch();
      if (!done && browser.readyState === WebSocket.OPEN) browser.send(toBuffer(data), { binary });
    });
    upstream.on("ping", touch);
    upstream.on("pong", touch);
    upstream.on("close", (code, reason) => {
      // What the Conduit said is what the browser is told. A close that is only a report of a state (the
      // connection dropped: 1006, or no code: 1005) is a Conduit that went away, so "try again later".
      if (sendableCode(code)) finish(code, reason.toString("utf8"), undefined);
      else finish(1013, "try again later", undefined);
    });
    upstream.on("unexpected-response", (_request, response) => {
      response.resume();
      // The Conduit refuses a connection it will not serve before it accepts (HTTP 401 or 403): the
      // credential was refused. Anything else is the Conduit being unwell.
      if (response.statusCode === 401 || response.statusCode === 403) finish(1008, "the Conduit refused the connection", undefined);
      else finish(1013, "try again later", undefined);
    });
    upstream.on("error", (error: Error & { code?: string }) => {
      if (done) return;
      // The code (ECONNREFUSED, ETIMEDOUT) and nothing else: the message of a socket error can carry an address.
      log(`pages: stream: the Conduit could not be reached (${error.code ?? "error"})`);
      finish(1013, "try again later", undefined);
    });

    browser.on("message", (data, binary) => {
      touch();
      const bytes = toBuffer(data);
      if (upstreamOpen) {
        upstream.send(bytes, { binary });
        return;
      }
      queued += bytes.length;
      if (queued > MAX_QUEUED_BYTES) {
        finish(1009, "too much sent before the connection was ready", 1009);
        return;
      }
      queue.push({ data: bytes, binary });
    });
    browser.on("ping", touch);
    browser.on("pong", touch);
    browser.on("close", (code, reason) => {
      // The browser went: the Conduit's side is closed with the browser's own code and reason.
      finish(undefined, reason.toString("utf8"), sendableCode(code) ? code : undefined);
    });
    browser.on("error", () => {
      finish(undefined, "", undefined);
      upstream.terminate();
    });
  }

  async function onUpgrade(req: IncomingMessage, socket: Duplex, head: Buffer): Promise<void> {
    socket.on("error", () => undefined);
    const target = req.url ?? "";
    const pathname = target.split("?", 1)[0] ?? "";
    const match = STREAM_PATH.exec(pathname);
    const id = match?.[1];
    if (settings === undefined || req.method !== "GET" || id === undefined || /^\.+$/.test(id)) {
      refuse(socket, 404, "Not Found");
      return;
    }
    if ((req.headers.upgrade ?? "").toLowerCase() !== "websocket") {
      refuse(socket, 400, "Bad Request");
      return;
    }
    // Exactly the deployment's own origin: no other, no near miss, and a browser always sends one.
    if (req.headers.origin !== settings.publicOrigin) {
      refuse(socket, 403, "Forbidden");
      return;
    }
    const sid = sessionIdFrom(req.headers.cookie, deps.sessionSecret);
    if (sid === undefined) {
      refuse(socket, 401, "Unauthorized");
      return;
    }
    let record: SessionRecord | undefined;
    try {
      record = await readSession(sid);
    } catch {
      log("pages: stream: the session store could not be read");
      refuse(socket, 503, "Service Unavailable");
      return;
    }
    if (record === undefined) {
      refuse(socket, 401, "Unauthorized");
      return;
    }
    if (socket.destroyed) return;
    browsers.handleUpgrade(req, socket, head, (browser) => {
      bridge(browser, record, sid, id);
    });
  }

  server.on("upgrade", (req: IncomingMessage, socket: Duplex, head: Buffer) => {
    onUpgrade(req, socket, head).catch(() => {
      log("pages: stream: an upgrade failed");
      if (!socket.destroyed) refuse(socket, 500, "Internal Server Error");
    });
  });

  async function look(connection: Live): Promise<void> {
    if (clock() - connection.lastFrame >= idleMs) {
      connection.end(1008, "no activity for too long");
      return;
    }
    if (connection.checking) return;
    connection.checking = true;
    try {
      const record = await readSession(connection.sid);
      if (record === undefined) connection.end(1008, "your session has ended");
    } catch {
      // The session cannot be shown to be alive: not served on trust. The browser tries again.
      connection.end(1013, "try again later");
    } finally {
      connection.checking = false;
    }
  }

  const timer = setInterval(() => {
    for (const connection of live) void look(connection);
  }, deps.checkMs ?? DEFAULT_CHECK_MS);
  timer.unref();

  return {
    close() {
      clearInterval(timer);
      for (const connection of [...live]) connection.end(1001, "going away");
      browsers.close();
    },
  };
}
