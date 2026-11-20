/**
 * Anti-forgery (ADR-152 decision 5). A cookie authenticates the browser's calls, so a state-changing
 * request needs a token that only a page of ours could have read: the synchroniser token held in the
 * session, sent in the `_csrf` form field or the `X-CSRF-Token` header, compared in constant time. On a `/v1` path a refusal
 * is JSON, and the body is the forwarder's to read (it may be a file): a script sends the header; a scripts-off form cannot
 * set one, so a url-encoded form carries `_csrf` as a field and a multipart form as its FIRST part, and the forwarder
 * checks it (`csrfDeferred`) before anything is sent on, and before any byte of a file is read. A header that is sent must be
 * right: a wrong one is not rescued by a form field.
 * Default-deny: every method but GET, HEAD and OPTIONS needs it.
 */
import { createHash, timingSafeEqual } from "node:crypto";
import type { RequestHandler } from "express";

import { isV1Path, rawPathOf, refuseJson } from "./v1.js";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export const CSRF_REFUSED = "This request could not be checked, so it was not carried out. Reload the page and try again.";

/** The kind of form a `Content-Type` names, or undefined for anything else. */
export function formKind(contentType: string | undefined): "multipart" | "urlencoded" | undefined {
  if (contentType === undefined) return undefined;
  if (/^\s*multipart\/form-data\s*(;|$)/i.test(contentType)) return "multipart";
  if (/^\s*application\/x-www-form-urlencoded\s*(;|$)/i.test(contentType)) return "urlencoded";
  return undefined;
}

/** Requests on a `/v1` path whose token is in the form body: the forwarder reads it, and must check it before sending anything on. */
const deferred = new WeakSet<object>();
export function csrfDeferred(req: object): boolean {
  return deferred.has(req);
}

/** True only for two equal, non-empty strings. Both are hashed first, so the comparison takes the same time whatever their lengths. */
export function tokensMatch(supplied: unknown, expected: unknown): boolean {
  if (typeof supplied !== "string" || typeof expected !== "string") return false;
  if (supplied.length === 0 || expected.length === 0) return false;
  const a = createHash("sha256").update(supplied).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}

function headerToken(req: Parameters<RequestHandler>[0]): string | undefined {
  const header = req.headers["x-csrf-token"];
  return typeof header === "string" && header.length > 0 ? header : undefined;
}

function bodyToken(req: Parameters<RequestHandler>[0]): unknown {
  const body: unknown = req.body;
  if (typeof body === "object" && body !== null) return (body as Record<string, unknown>)["_csrf"];
  return undefined;
}

export function csrfProtection(): RequestHandler {
  return (req, res, next) => {
    if (SAFE_METHODS.has(req.method)) {
      next();
      return;
    }
    const auth = req.session?.auth;
    const v1 = isV1Path(rawPathOf(req));
    const header = headerToken(req);
    if (auth && v1) {
      if (header !== undefined) {
        if (tokensMatch(header, auth.csrfToken)) {
          next();
          return;
        }
      } else if (formKind(req.headers["content-type"]) !== undefined) {
        // A scripts-off form cannot set a header. Its token is in the body, which only the forwarder reads (it may hold a
        // file): the forwarder checks it before it sends anything on, and refuses without it.
        deferred.add(req);
        next();
        return;
      }
    } else if (auth && tokensMatch(header ?? bodyToken(req), auth.csrfToken)) {
      next();
      return;
    }
    if (v1) {
      // A `/v1` call is a script's or a form's, and the Glass reads `detail`: the Conduit's own shape, in words.
      if (auth) {
        refuseJson(res, 403, CSRF_REFUSED);
      } else {
        refuseJson(res, 401, "You are not signed in, or your session has ended. Sign in again.");
      }
      return;
    }
    res.status(403).render("error", {
      title: "Request not carried out",
      message:
        "This request could not be checked, so it was not carried out. Go back, reload the page and try again.",
    });
  };
}
