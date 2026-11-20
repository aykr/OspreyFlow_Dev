/**
 * The security policy on every response (ADR-152 decision 8). Scripts and styles from the page's own
 * address or this response's nonce; nothing from another address; no `unsafe-inline`, no
 * `unsafe-eval`, no exception for a framed Superset. No HSTS: the front proxy ends TLS and owns it.
 */
import { randomBytes } from "node:crypto";
import type { RequestHandler, Response } from "express";
import helmet from "helmet";
import type { ServerResponse } from "node:http";

function nonceOf(res: ServerResponse): string {
  return (res as Response).locals["cspNonce"] as string;
}

const nonceDirective = (_req: unknown, res: ServerResponse): string => `'nonce-${nonceOf(res)}'`;

/** A fresh nonce for each response, kept in `res.locals.cspNonce` for the template's script tags. */
const freshNonce: RequestHandler = (_req, res, next) => {
  res.locals["cspNonce"] = randomBytes(16).toString("base64");
  next();
};

/** Nothing here is a shared page: a person's page is not stored by a browser or a proxy. */
const noStore: RequestHandler = (_req, res, next) => {
  res.set("Cache-Control", "no-store");
  next();
};

export function securityHeaders(): RequestHandler[] {
  return [
    freshNonce,
    helmet({
      contentSecurityPolicy: {
        useDefaults: false,
        directives: {
          "default-src": ["'self'"],
          "script-src": ["'self'", nonceDirective],
          "style-src": ["'self'", nonceDirective],
          "img-src": ["'self'", "data:"],
          "worker-src": ["'self'"],
          "connect-src": ["'self'"],
          "frame-src": ["'none'"],
          "frame-ancestors": ["'none'"],
          "object-src": ["'none'"],
          "base-uri": ["'self'"],
          "form-action": ["'self'"],
        },
      },
      strictTransportSecurity: false,
      referrerPolicy: { policy: "same-origin" },
      crossOriginOpenerPolicy: { policy: "same-origin" },
      frameguard: { action: "deny" },
      xContentTypeOptions: true,
    }),
    noStore,
  ];
}
