/**
 * The pages service's Express application: sign-in, session, security headers, anti-forgery, and the
 * one page that says who is signed in. Built by a factory so that a test drives the real thing with an
 * in-memory store and a fake identity provider; `main.ts` builds it with Valkey.
 */
import { parse as parseCookies } from "cookie";
import express from "express";
import type { ErrorRequestHandler, Express, Request, RequestHandler, Router } from "express";
import nunjucks from "nunjucks";
import { fileURLToPath } from "node:url";

import { csrfProtection } from "./csrf.js";
import { securityHeaders } from "./headers.js";
import { IdentityProviderUnavailable } from "./identity.js";
import type { IdentityProvider } from "./identity.js";
import { COOKIE_NAME, SessionService, isSessionId } from "./sessionPolicy.js";
import type { ActiveSession } from "./sessionPolicy.js";
import type { SessionStore } from "./sessionStore.js";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      /** The live session for the request's cookie, or null. Set by the session middleware, after `/healthz`. */
      pagesSession?: ActiveSession | null;
    }
  }
}

export interface AppDeps {
  store: SessionStore;
  identityProvider: IdentityProvider;
  /** Milliseconds since the epoch. A test moves it by hand. */
  clock?: () => number;
  /** Routes a later slice adds, after the core routes and behind the same session, headers and anti-forgery. */
  extraRoutes?: (router: Router) => void;
}

const VIEWS = fileURLToPath(new URL("./views", import.meta.url));

/** `Secure` and `HttpOnly` always, `SameSite=Lax`, no `Domain`: the cookie holds one opaque identifier. */
const COOKIE_OPTIONS = { httpOnly: true, secure: true, sameSite: "lax", path: "/" } as const;

function readSessionId(req: Request): string | null {
  const header = req.headers.cookie;
  if (!header) return null;
  const value = parseCookies(header)[COOKIE_NAME];
  return isSessionId(value) ? value : null;
}

export function createApp(deps: AppDeps): Express {
  const clock = deps.clock ?? Date.now;
  const sessions = new SessionService(deps.store, clock);
  const app = express();

  app.disable("x-powered-by");
  app.disable("etag");
  nunjucks.configure(VIEWS, { autoescape: true, express: app, noCache: false });
  app.set("view engine", "njk");

  app.use(securityHeaders());

  // No session, no secret and no call to the store or the identity provider: a probe must answer
  // when either is down.
  app.get("/healthz", (_req, res) => {
    res.json({ status: "ok" });
  });

  const loadSession: RequestHandler = async (req, _res, next) => {
    const id = readSessionId(req);
    req.pagesSession = id ? await sessions.load(id) : null;
    next();
  };
  app.use(loadSession);
  app.use(express.urlencoded({ extended: false, limit: "16kb" }));
  app.use(csrfProtection());

  app.get("/", (req, res) => {
    const session = req.pagesSession;
    if (!session) {
      res.redirect(302, "/session/sign-in");
      return;
    }
    // The person's name and the anti-forgery token for the sign-out form: nothing else of the session.
    res.render("home", { displayName: session.record.displayName, csrfToken: session.record.csrfToken });
  });

  app.get("/session/sign-in", async (req, res) => {
    let provided;
    try {
      provided = await deps.identityProvider.signIn({ query: req.query });
    } catch (error) {
      if (error instanceof IdentityProviderUnavailable) {
        res.status(503).render("error", {
          title: "Sign-in not available",
          message:
            "Sign-in is not available just now. Nothing about your access has changed. Try again in a few minutes.",
        });
        return;
      }
      throw error;
    }
    // A new identifier at every sign-in, never one the browser brought; the one it had is ended.
    if (req.pagesSession) await sessions.destroy(req.pagesSession.id);
    const created = await sessions.create(provided);
    res.cookie(COOKIE_NAME, created.id, COOKIE_OPTIONS);
    res.redirect(302, "/");
  });

  app.post("/session/sign-out", async (req, res) => {
    // The anti-forgery check has already run, so there is a session here.
    if (req.pagesSession) await sessions.destroy(req.pagesSession.id);
    res.clearCookie(COOKIE_NAME, COOKIE_OPTIONS);
    res.redirect(303, "/");
  });

  if (deps.extraRoutes) {
    const router = express.Router();
    deps.extraRoutes(router);
    app.use(router);
  }

  app.use((req, res, next) => {
    // An OPTIONS request for a route there is gets Express's own answer (its Allow list) once the stack
    // is spent; one for no route at all falls to the same 404.
    if (req.method === "OPTIONS") {
      next();
      return;
    }
    res.status(404).render("error", { title: "Page not found", message: "That page could not be found." });
  });

  const onError: ErrorRequestHandler = (error: unknown, _req, res, _next) => {
    const status = (error as { status?: number; statusCode?: number }).status ?? (error as { statusCode?: number }).statusCode;
    if (status !== undefined && status >= 400 && status < 500) {
      res.status(status).render("error", { title: "Request not understood", message: "That request was not understood." });
      return;
    }
    // The cause goes to the log, never to the page.
    console.error("pages: unhandled error:", error instanceof Error ? error.message : String(error));
    res.status(500).render("error", {
      title: "Something went wrong",
      message: "Something went wrong on our side. Try again in a few minutes.",
    });
  };
  app.use(onError);

  return app;
}
