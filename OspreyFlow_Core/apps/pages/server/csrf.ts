/**
 * Anti-forgery (ADR-152 decision 5). A cookie authenticates the browser's calls, so a state-changing
 * request needs a token that only a page of ours could have read: the synchroniser token held in the
 * session, sent in the `_csrf` form field or the `X-CSRF-Token` header (the header alone on a `/v1` path, where a refusal
 * is JSON), compared in constant time.
 * Default-deny: every method but GET, HEAD and OPTIONS needs it.
 */
import { createHash, timingSafeEqual } from "node:crypto";
import type { RequestHandler } from "express";

import { isV1Path, rawPathOf, refuseJson } from "./v1.js";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** True only for two equal, non-empty strings. Both are hashed first, so the comparison takes the same time whatever their lengths. */
export function tokensMatch(supplied: unknown, expected: unknown): boolean {
  if (typeof supplied !== "string" || typeof expected !== "string") return false;
  if (supplied.length === 0 || expected.length === 0) return false;
  const a = createHash("sha256").update(supplied).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}

function suppliedToken(req: Parameters<RequestHandler>[0], headerOnly: boolean): unknown {
  const header = req.headers["x-csrf-token"];
  if (typeof header === "string" && header.length > 0) return header;
  // A `/v1` body is the forwarder's to read, and a multipart body's field cannot be read here: the header alone counts.
  if (headerOnly) return undefined;
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
    if (auth && tokensMatch(suppliedToken(req, v1), auth.csrfToken)) {
      next();
      return;
    }
    if (v1) {
      // A `/v1` call is a script's or a form's, and the Glass reads `detail`: the Conduit's own shape, in words.
      if (auth) {
        refuseJson(res, 403, "This request could not be checked, so it was not carried out. Reload the page and try again.");
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
