/**
 * Ordinary `/v1` calls through the page service, with the person's token kept on the server (ADR-152 decision 5;
 * X1 and F1 of decision 11; slice PL10). Today the workspace's nginx does this (`location /v1/`); a server-rendered
 * page has no nginx of its own, so the page service does it, behind the same headers, session and anti-forgery
 * check as its pages. The live stream is `stream.ts`'s and is not carried here.
 *
 * WHICH PATHS. Every path under `/v1/` but a deny-list: the stream's path (CO3 owns it), `/v1/ws-ticket` (pointless
 * once this service holds the bearer) and anything not under `/v1/`. The Conduit authorises every route (rules 3 and
 * 4); this adds no access rule of its own. Why a deny-list: nginx's `location /v1/` passes every route today and the
 * Conduit authorises each itself, so this adds no exposure; the only two routes that must never be carried are the two
 * that put a credential in the browser (the stream and `ws-ticket`); an allow-list would make every page build edit one
 * shared list (the owner accepted this, 20 November 2026).
 * THE PATH, CANONICALLY. The path (the part before `?`) is percent-decoded exactly ONCE and made one canonical form.
 * Refused 404, in words, with the Conduit not contacted: anything still encoded after that pass (a double-encoded
 * character), an encoded slash, backslash or dot (`%2f`, `%5c`, `%2e`, in any case of hex), a dot segment, a path
 * parameter (`;`), a double slash, a control character (NUL, CR and LF among them), a malformed escape, bytes that are
 * not UTF-8, and any path that does not start with exactly `/v1/`. The deny-list is matched on the canonical form, in
 * any case (the Conduit is case-sensitive; the two names are refused whatever their case), and the canonical form is
 * what is forwarded (re-encoded by one fixed rule: `encodePath`), so what was checked is exactly what the Conduit gets.
 * THE QUERY IS NOT PATH. It arrives as sent (an encoded `/`, `.` or `\` in a value is legitimate); only a raw NUL, CR
 * or LF in it is refused. A redirect is never followed, and the upstream host is the setting's and nothing else's.
 *
 * WHAT IS SENT. The method, the path and the query string, a body, and exactly these headers: `Authorization: Bearer`
 * (the person's, from `accessTokenFor`), `Content-Type`, `Accept`, a recomputed `Content-Length` (or the browser's own
 * declared one for a streamed upload), `X-Request-Id` when the browser's is of reasonable length and plain, and
 * `X-Forwarded-Proto` and `X-Forwarded-For` as nginx sets them. Nothing else the browser sent: not its `Cookie`,
 * `Authorization`, `Origin`, `X-Forwarded-*`, `X-CSRF-Token`, `Host`. The headers are built, never copied.
 *
 * WHAT COMES BACK. The status; the body streamed through, never buffered; `Content-Type`, `Content-Disposition` and
 * `X-Guide-Version` and no other header, and never a `Location`. A Conduit 401, 403, 413, 422 and the like pass through
 * unchanged, body included; a Conduit 401 does not end the session here (renewal is `accessTokenFor`'s, PL9).
 * A Conduit that cannot be reached is 502; one that is silent for `OSPREY_PAGES_UPSTREAM_TIMEOUT_SECONDS` is 504.
 * Silent means no byte either way on the connection, so a slow upload or a long read is never cut for its length.
 *
 * ANTI-FORGERY. `csrf.ts` covers every method but GET, HEAD and OPTIONS. A script sends `X-CSRF-Token`. A scripts-off
 * form cannot, so a url-encoded form carries `_csrf` as a field and a multipart form as its FIRST part, and this module
 * checks it (the request is "deferred" to it): a multipart one before any byte of a file is read, a url-encoded one
 * before anything is sent. `_csrf` is NEVER forwarded and never in a URL or a log: it is removed from a url-encoded
 * body (the rest unchanged) and is not copied into the query of a translated form. There is no `Origin` check on HTTP:
 * the anti-forgery token is the guard here (the Conduit checks no `Origin` on HTTP, and a server-to-server call sends
 * none).
 *
 * BODIES. A JSON or other small body is read whole under `OSPREY_PAGES_BODY_MAX_BYTES`. A raw upload route's body
 * (the four the Conduit has: an ingest source file, a board node's picture, a node's picture, a document) streams
 * upstream and is never held, under `OSPREY_PAGES_UPLOAD_MAX_BYTES`: a declared length over the cap is refused before
 * a byte is read, a stream past it is cut, both 413 in the Conduit's own words.
 *
 * A BROWSER'S FORM UPLOAD, SCRIPTS OFF. A `multipart/form-data` post to one of those four routes is read here: the
 * form's fields come first and become the route's query fields, the file part's name becomes `?name=`, and the file's
 * bytes are sent raw. The Conduit is unchanged. A multipart post to any other route is 415; that includes the
 * Conduit's one multipart route, `/v1/investigations/{id}/sites` (not carried: the owner's ruling is needed), and
 * `/rules/import` (it takes JSON). The route table below is the allow-list for this translation only.
 *
 * Nothing secret is written down: a log line is a fixed phrase and a status, and no error's own message is passed on.
 */
import { request as httpRequest } from "node:http";
import type { ClientRequest, IncomingMessage } from "node:http";
import { request as httpsRequest } from "node:https";
import { pipeline } from "node:stream";

import type { NextFunction, Request, RequestHandler, Response } from "express";

import { accessTokenFor } from "./accessToken.js";
import { BodyStalled, DEFAULT_BODY_STALL_MS, untilStalled } from "./bodyStall.js";
import type { ForwardSettings } from "./config.js";
import { CSRF_REFUSED, csrfDeferred, formKind, tokensMatch } from "./csrf.js";
import { MultipartRefusal, boundaryOf, readMultipart } from "./multipart.js";
import type { FileSink } from "./multipart.js";
import { isV1Path, rawPathOf, refuseJson } from "./v1.js";

const SAFE_WORDS = {
  notFound: "That address is not served here.",
  method: "That method is not carried here.",
  signedOut: "You are not signed in, or your session has ended. Sign in again.",
  fileTooLarge: "That file is larger than the upload limit.",
  bodyTooLarge: "That request is larger than the limit.",
  notAFileRoute:
    "That address does not take a file sent as a form. Choose the file from the page that offers it, or send it without a form.",
  unreachable: "The service could not be reached just now. Nothing was changed. Try again in a few minutes.",
  timedOut: "The service took too long to answer. It may still be working. Try again in a few minutes.",
  access: "Your access could not be prepared just now. Try again in a few minutes.",
  stalled: "The request stopped arriving, so it was ended. Nothing was changed. Go back and send it again.",
} as const;

const CARRIED_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);
const BODYLESS_METHODS = new Set(["GET", "HEAD"]);

/** Headers copied back from the Conduit, and no others. */
const COPIED_BACK = ["content-type", "content-disposition", "x-guide-version"] as const;

/** The stream is `stream.ts`'s; a ticket is pointless once this service holds the bearer. Matched on the canonical path, in any case. */
const DENIED = [/^\/v1\/investigations\/[^/]+\/stream\/?$/i, /^\/v1\/ws-ticket\/?$/i];

/**
 * The raw-body upload routes of the Conduit (`services/api/app.py`): the body is the file's bytes and its name is in
 * the query. This table is the allow-list for the form translation, and for the streamed (never held) body.
 */
const UPLOAD_ROUTES: ReadonlyArray<{ method: "POST" | "PUT"; path: RegExp }> = [
  { method: "POST", path: /^\/v1\/investigations\/[^/]+\/ingest\/source-files$/ },
  { method: "PUT", path: /^\/v1\/investigations\/[^/]+\/boards\/[^/]+\/nodes\/[^/]+\/picture$/ },
  { method: "PUT", path: /^\/v1\/investigations\/[^/]+\/nodes\/[^/]+\/picture$/ },
  { method: "POST", path: /^\/v1\/investigations\/[^/]+\/documents$/ },
];

/** What a form's boundaries and headers add to a file's bytes. */
const FORM_ENVELOPE_ALLOWANCE = 1024 * 1024;
/** What is read and thrown away after a refusal, so that the browser can be answered, and no more. */
const DRAIN_MAX_BYTES = 1024 * 1024;
const DRAIN_MAX_MS = 5000;
const REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/;

/** What a request target comes to once it has been checked: the canonical path, as the Conduit routes on it and as it is sent. */
export interface Target {
  /** The decoded, canonical path: what the route table and the deny-list are matched on. */
  path: string;
  /** The same path re-encoded by one fixed rule: what is sent upstream. */
  encoded: string;
  /** The query string as sent, without its `?`. */
  query: string;
}

/** Kept as they are in a path: the unreserved characters, the sub-delimiters but `;` (refused), `:` and `@`. Everything else is `%XX`. */
const PATH_KEEP = /^[A-Za-z0-9\-._~!$&'()*+,=:@]$/;

/** The fixed rule by which a decoded path is written for the Conduit: each character outside `PATH_KEEP` and `/` as its UTF-8 bytes in `%XX`, upper case. */
function encodePath(decoded: string): string {
  let out = "";
  for (const ch of decoded) {
    if (ch === "/" || PATH_KEEP.test(ch)) out += ch;
    else for (const byte of Buffer.from(ch, "utf8")) out += `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
  }
  return out;
}

/**
 * The checked target, or why it is not served. The path is decoded once, resolved to one canonical form and checked in
 * that form; the query is not path and is only checked for a raw NUL, CR or LF.
 */
export function checkTarget(rawTarget: string): { ok: true; target: Target } | { ok: false; why: string } {
  const at = rawTarget.indexOf("?");
  const rawPath = at < 0 ? rawTarget : rawTarget.slice(0, at);
  const query = at < 0 ? "" : rawTarget.slice(at + 1);
  const no = (why: string): { ok: false; why: string } => ({ ok: false, why });
  if (!rawPath.startsWith("/v1/") || rawPath === "/v1/") return no("not a path under /v1/");
  if (/[\0\r\n]/.test(query)) return no("a raw NUL, CR or LF in the query");
  if (/[\u0000-\u001f\u007f]/.test(rawPath)) return no("a control character");
  if (rawPath.includes("\\")) return no("a backslash");
  if (rawPath.includes(";")) return no("a path parameter");
  if (rawPath.includes("//")) return no("a double slash");
  if (/%(2e|2f|5c)/i.test(rawPath)) return no("an encoded dot, slash or backslash");
  if (/%(?![0-9A-Fa-f]{2})/.test(rawPath)) return no("a malformed escape");
  let decoded: string;
  try {
    decoded = decodeURIComponent(rawPath);
  } catch {
    return no("bytes that are not UTF-8");
  }
  if (/%[0-9A-Fa-f]{2}/.test(decoded)) return no("a character encoded twice");
  if (/[\u0000-\u001f\u007f]/.test(decoded)) return no("a control character");
  if (decoded.includes(";")) return no("a path parameter");
  if (decoded.includes("\\") || decoded.includes("//")) return no("a backslash or a double slash");
  if (decoded.split("/").some((segment) => segment === "." || segment === "..")) return no("a dot segment");
  if (DENIED.some((denied) => denied.test(decoded))) return no("a path another part of the service owns");
  return { ok: true, target: { path: decoded, encoded: encodePath(decoded), query } };
}

/** Why a request target is not served, or undefined when it is. */
export function refusedTarget(rawTarget: string): string | undefined {
  const checked = checkTarget(rawTarget);
  return checked.ok ? undefined : checked.why;
}

/**
 * Mounted before the session is read. With no forwarder (`OSPREY_PAGES_CONDUIT_URL` unset) every `/v1` path is 404;
 * with one, a path it will not carry is 404 and a method it will not carry is 405, and in neither case has the
 * session store, or the Conduit, been touched.
 */
export function v1Gate(forwarding: boolean): RequestHandler {
  return (req, res, next) => {
    const path = rawPathOf(req);
    if (!isV1Path(path)) {
      next();
      return;
    }
    if (!forwarding || refusedTarget(req.originalUrl) !== undefined) {
      refuseJson(res, 404, SAFE_WORDS.notFound);
      return;
    }
    if (!CARRIED_METHODS.has(req.method)) {
      res.set("Allow", [...CARRIED_METHODS].join(", "));
      refuseJson(res, 405, SAFE_WORDS.method);
      return;
    }
    next();
  };
}

/**
 * A url-encoded body without its `_csrf` field(s), every other byte unchanged, and the token's value (the first one). The
 * key is compared decoded (`%5Fcsrf` is `_csrf`). The body is handled as bytes (latin1), never as text, so nothing else moves.
 */
function withoutCsrf(body: Buffer): { body: Buffer; token: string | undefined } {
  const kept: string[] = [];
  let token: string | undefined;
  const decode = (text: string): string | undefined => {
    try {
      return decodeURIComponent(text.replace(/\+/g, " "));
    } catch {
      return undefined;
    }
  };
  for (const pair of body.toString("latin1").split("&")) {
    const eq = pair.indexOf("=");
    const key = decode(eq < 0 ? pair : pair.slice(0, eq));
    if (key === "_csrf") {
      if (token === undefined) token = decode(eq < 0 ? "" : pair.slice(eq + 1));
      continue;
    }
    kept.push(pair);
  }
  return { body: Buffer.from(kept.join("&"), "latin1"), token };
}

function uploadRouteFor(path: string) {
  return UPLOAD_ROUTES.find((route) => route.path.test(path));
}

/** Waits until a stream can take more, or can take no more. */
function drained(target: ClientRequest): Promise<void> {
  return new Promise((resolve) => {
    const done = (): void => {
      target.off("drain", done);
      target.off("close", done);
      target.off("error", done);
      resolve();
    };
    target.once("drain", done);
    target.once("close", done);
    target.once("error", done);
  });
}

/** After a refusal: take what the browser is still sending, up to a limit and a time, so that it can read the answer. */
function drain(req: Request): void {
  let seen = 0;
  req.on("data", (chunk: Buffer) => {
    seen += chunk.length;
    if (seen > DRAIN_MAX_BYTES) req.destroy();
  });
  req.resume();
  const timer = setTimeout(() => req.destroy(), DRAIN_MAX_MS);
  timer.unref();
  req.once("close", () => clearTimeout(timer));
}

class UpstreamTimeout extends Error {}

export interface ForwarderDeps {
  settings: ForwardSettings;
  /** Where the forwarder says what went wrong: a fixed phrase and a status, never a token, a cookie or an address. */
  log?: (message: string) => void;
  /** How long a browser may send nothing while its body is being read before the call is ended (`bodyStall.ts`). */
  bodyStallMs?: number;
}

export function forwarder(deps: ForwarderDeps): RequestHandler {
  const { settings } = deps;
  const log = deps.log ?? (() => undefined);
  const base = new URL(settings.conduitUrl);
  const transport = base.protocol === "https:" ? httpsRequest : httpRequest;
  const hostname = base.hostname.replace(/^\[|\]$/g, "");
  const timeoutMs = settings.upstreamTimeoutSeconds * 1000;
  const stallMs = deps.bodyStallMs ?? DEFAULT_BODY_STALL_MS;

  return (req: Request, res: Response, next: NextFunction): void => {
    if (!isV1Path(rawPathOf(req))) {
      next();
      return;
    }
    // The gate has already refused what is not served; the same check is made here, so that this module never forwards what it did not check.
    const checked = checkTarget(req.originalUrl);
    if (!checked.ok) {
      refuseJson(res, 404, SAFE_WORDS.notFound);
      return;
    }
    run(req, res, checked.target).catch(() => {
      log("pages: forward: a call failed (500)");
      if (!res.headersSent) refuseJson(res, 500, "Something went wrong on our side. Try again in a few minutes.");
      else res.destroy();
    });
  };

  async function run(req: Request, res: Response, target: Target): Promise<void> {
    const { path, query } = target;
    // The session is the person's: with none, or one that has ended, nobody is forwarded as and the Conduit is not contacted.
    const auth = req.session?.auth;
    if (!auth) {
      refuseJson(res, 401, SAFE_WORDS.signedOut);
      return;
    }
    let token: string | undefined;
    try {
      token = await accessTokenFor(auth);
    } catch {
      log("pages: forward: the person's access could not be prepared (502)");
      refuseJson(res, 502, SAFE_WORDS.access);
      return;
    }
    if (!token) {
      refuseJson(res, 401, SAFE_WORDS.signedOut);
      return;
    }

    /** What is sent upstream for this path: the canonical path, and the query exactly as the browser sent it. */
    const upstreamTarget = (extraQuery = ""): string => {
      const joined = [query, extraQuery].filter((part) => part !== "").join("&");
      return joined === "" ? target.encoded : `${target.encoded}?${joined}`;
    };
    // A form with scripts off carries the anti-forgery token in its body: it is checked here, before anything is sent on.
    const pending = csrfDeferred(req);
    const method = req.method;
    const route = uploadRouteFor(path);
    const contentType = req.headers["content-type"];
    const declaredRaw = req.headers["content-length"];
    const declared = declaredRaw !== undefined && /^\d+$/.test(declaredRaw) ? Number(declaredRaw) : undefined;
    const hasBody = !BODYLESS_METHODS.has(method) && (declared !== undefined ? declared > 0 : req.headers["transfer-encoding"] !== undefined);
    const kind = formKind(contentType);
    const isForm = hasBody && kind === "multipart";

    /** The headers the Conduit is sent: built here, one by one. Nothing is copied from the browser as a whole. */
    const headersFor = (extra: Record<string, string>): Record<string, string> => {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${token}`,
        "X-Forwarded-Proto": req.protocol,
        "X-Forwarded-For": req.ip ?? req.socket.remoteAddress ?? "",
        ...extra,
      };
      const accept = req.headers["accept"];
      if (typeof accept === "string" && accept !== "") headers["Accept"] = accept;
      const requestId = req.headers["x-request-id"];
      if (typeof requestId === "string" && REQUEST_ID.test(requestId)) headers["X-Request-Id"] = requestId;
      return headers;
    };

    // ---- the exchange: one call upstream, one answer to the browser ----
    let settled = false; // an answer has begun to go to the browser
    let upstream: ClientRequest | undefined;

    const answer = (status: number, detail: string): void => {
      if (settled) return;
      settled = true;
      refuseJson(res, status, detail);
    };
    /** The browser's own mistake or limit: answered, and the Conduit's call (if one was begun) is abandoned. */
    const refuse = (status: number, detail: string): void => {
      const began = settled;
      answer(status, detail);
      upstream?.destroy();
      if (!began) drain(req);
    };

    const relay = (up: IncomingMessage): void => {
      if (settled) {
        up.resume();
        return;
      }
      settled = true;
      res.status(up.statusCode ?? 502);
      for (const name of COPIED_BACK) {
        const value = up.headers[name];
        if (value !== undefined) res.setHeader(name, value);
      }
      pipeline(up, res, () => undefined);
    };

    const open = (target: string, headers: Record<string, string>): ClientRequest => {
      const created = transport({
        hostname,
        port: base.port || undefined,
        method: route !== undefined && isForm ? route.method : method,
        path: target,
        headers,
        agent: false,
        timeout: timeoutMs,
        // A redirect is never followed: `http.request` does not, and the answer's `Location` is never passed on.
      });
      created.on("timeout", () => created.destroy(new UpstreamTimeout()));
      created.on("error", (error) => {
        if (settled) return;
        if (error instanceof UpstreamTimeout) {
          log("pages: forward: the Conduit gave no answer in time (504)");
          answer(504, SAFE_WORDS.timedOut);
        } else {
          log("pages: forward: the Conduit could not be reached (502)");
          answer(502, SAFE_WORDS.unreachable);
        }
        drain(req);
      });
      created.on("response", relay);
      upstream = created;
      return created;
    };
    res.on("close", () => {
      if (!res.writableFinished) upstream?.destroy();
    });

    // Node's whole-request timeout is off (`start.ts`), so a browser that stops sending is ended here: 408, the call to
    // the Conduit abandoned, and the browser's connection closed once the answer is out.
    const stream = (): AsyncIterable<Buffer> =>
      untilStalled(req.iterator({ destroyOnReturn: false }) as AsyncIterable<Buffer>, stallMs);
    const stalled = (): void => {
      log("pages: forward: the browser stopped sending its body (408)");
      refuse(408, SAFE_WORDS.stalled);
      if (res.writableFinished) req.destroy();
      else res.once("finish", () => req.destroy());
    };

    // ---- a browser's form upload to a raw route: the file's bytes, raw, with the fields in the query ----
    if (isForm) {
      if (route === undefined || (method !== "POST" && method !== route.method)) {
        // Anti-forgery before anything else is said about the request.
        if (pending) refuse(403, CSRF_REFUSED);
        else refuse(415, SAFE_WORDS.notAFileRoute);
        return;
      }
      const boundary = boundaryOf(contentType);
      if (boundary === undefined) {
        refuse(422, "The form could not be read. Go back and send it again.");
        return;
      }
      if (declared !== undefined && declared > settings.uploadMaxBytes + FORM_ENVELOPE_ALLOWANCE) {
        refuse(413, SAFE_WORDS.fileTooLarge);
        return;
      }
      const fields = new URLSearchParams();
      let fileSeen = false;
      let size = 0;
      let parts = 0;
      let verified = !pending;
      try {
        await readMultipart(stream(), boundary, {
          field(name, value) {
            const first = parts === 0;
            parts += 1;
            if (name === "_csrf") {
              // Never copied into the query or the body. Where the token is the form's only proof, it must be the first part and right.
              if (!verified) {
                if (!first || !tokensMatch(value, auth.csrfToken)) throw new MultipartRefusal(403, CSRF_REFUSED);
                verified = true;
              }
              return;
            }
            if (!verified) throw new MultipartRefusal(403, CSRF_REFUSED);
            // The query goes before the bytes, so every field must come before the file.
            if (fileSeen) throw new MultipartRefusal(422, "The form's fields must come before its file. Go back and send it again.");
            fields.append(name, value);
          },
          file(_name, filename): FileSink {
            // Before a byte of the file is read: no proof, no upload.
            if (!verified) throw new MultipartRefusal(403, CSRF_REFUSED);
            if (fileSeen) throw new MultipartRefusal(422, "Send one file at a time.");
            if (filename === "") throw new MultipartRefusal(422, "No file was chosen. Go back and choose one.");
            fileSeen = true;
            fields.set("name", filename);
            const up = open(upstreamTarget(fields.toString()), headersFor({ "Content-Type": "application/octet-stream" }));
            return {
              async write(chunk) {
                size += chunk.length;
                if (size > settings.uploadMaxBytes) throw new MultipartRefusal(413, SAFE_WORDS.fileTooLarge);
                if (settled || up.destroyed) return;
                if (!up.write(chunk)) await drained(up);
              },
            };
          },
          fileEnd() {
            // Not ended here: a field after the file is still to be refused, and a call the Conduit has not been told
            // is finished is one it does not act on. It ends when the whole form has been read.
          },
        });
      } catch (error) {
        if (error instanceof MultipartRefusal) {
          refuse(error.status, error.detail);
          return;
        }
        if (error instanceof BodyStalled) {
          stalled();
          return;
        }
        // The browser went away mid-form: what the Conduit has is not a whole upload, so it is abandoned, not ended.
        settled = true;
        upstream?.destroy();
        return;
      }
      if (!fileSeen) refuse(422, "No file was sent. Go back and choose one.");
      else if (!settled) upstream?.end();
      return;
    }

    // ---- a raw upload: streamed, never held ----
    if (route !== undefined && method === route.method && hasBody) {
      // A raw body is never read here, so a token in it cannot be: the header is the only proof for a raw upload.
      if (pending) {
        refuse(403, CSRF_REFUSED);
        return;
      }
      if (declared !== undefined && declared > settings.uploadMaxBytes) {
        refuse(413, SAFE_WORDS.fileTooLarge);
        return;
      }
      const up = open(
        upstreamTarget(),
        headersFor({
          ...(typeof contentType === "string" ? { "Content-Type": contentType } : {}),
          ...(declared !== undefined ? { "Content-Length": String(declared) } : {}),
        }),
      );
      let size = 0;
      try {
        for await (const chunk of stream()) {
          size += chunk.length;
          if (size > settings.uploadMaxBytes) {
            refuse(413, SAFE_WORDS.fileTooLarge);
            return;
          }
          if (settled || up.destroyed) continue; // the Conduit has already answered: the rest is read and dropped
          if (!up.write(chunk)) await drained(up);
        }
      } catch (error) {
        if (error instanceof BodyStalled) {
          stalled();
          return;
        }
        settled = true;
        up.destroy();
        return;
      }
      if (!settled) up.end();
      return;
    }

    // ---- everything else: a small body, read whole under its cap, or none ----
    let body: Buffer | undefined;
    if (hasBody) {
      if (declared !== undefined && declared > settings.bodyMaxBytes) {
        refuse(413, SAFE_WORDS.bodyTooLarge);
        return;
      }
      const parts: Buffer[] = [];
      let size = 0;
      try {
        for await (const chunk of stream()) {
          size += chunk.length;
          if (size > settings.bodyMaxBytes) {
            refuse(413, SAFE_WORDS.bodyTooLarge);
            return;
          }
          parts.push(chunk);
        }
      } catch (error) {
        if (error instanceof BodyStalled) stalled();
        return; // otherwise the browser went away: nobody to answer
      }
      body = Buffer.concat(parts);
      if (kind === "urlencoded") {
        // `_csrf` is the form's proof and is not the Conduit's: it is checked if it is the only proof, and removed in every case.
        const form = withoutCsrf(body);
        if (pending && !tokensMatch(form.token, auth.csrfToken)) {
          answer(403, CSRF_REFUSED);
          return;
        }
        body = form.body;
      }
    }
    if (pending && (body === undefined || kind !== "urlencoded")) {
      answer(403, CSRF_REFUSED); // a form with no body, or one that is not a form we can read: nothing to check it by
      return;
    }
    const up = open(
      upstreamTarget(),
      headersFor({
        ...(typeof contentType === "string" && body !== undefined ? { "Content-Type": contentType } : {}),
        ...(body !== undefined ? { "Content-Length": String(body.length) } : {}),
      }),
    );
    if (body !== undefined) up.end(body);
    else up.end();
  }
}
