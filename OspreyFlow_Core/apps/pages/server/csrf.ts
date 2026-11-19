/**
 * Anti-forgery (ADR-152 decision 5). A cookie authenticates the browser's calls, so a state-changing
 * request needs a token that only a page of ours could have read: the synchroniser token held in the
 * session, sent in the `_csrf` form field or the `X-CSRF-Token` header, compared in constant time.
 * Default-deny: every method but GET, HEAD and OPTIONS needs it.
 */
import { createHash, timingSafeEqual } from "node:crypto";
import type { RequestHandler } from "express";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** True only for two equal, non-empty strings. Both are hashed first, so the comparison takes the same time whatever their lengths. */
export function tokensMatch(supplied: unknown, expected: unknown): boolean {
  if (typeof supplied !== "string" || typeof expected !== "string") return false;
  if (supplied.length === 0 || expected.length === 0) return false;
  const a = createHash("sha256").update(supplied).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}

function suppliedToken(req: Parameters<RequestHandler>[0]): unknown {
  const header = req.headers["x-csrf-token"];
  if (typeof header === "string" && header.length > 0) return header;
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
    if (auth && tokensMatch(suppliedToken(req), auth.csrfToken)) {
      next();
      return;
    }
    res.status(403).render("error", {
      title: "Request not carried out",
      message:
        "This request could not be checked, so it was not carried out. Go back, reload the page and try again.",
    });
  };
}
