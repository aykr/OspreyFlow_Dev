/**
 * The pages service's Express application: sign-in, session, security headers, anti-forgery, and the
 * one page that says who is signed in. Built by a factory so that a test drives the real thing with an
 * in-memory store and a fake identity provider; `main.ts` builds it with Valkey.
 */
import express from "express";
import type { ErrorRequestHandler, Express, Request, Router } from "express";
import session from "express-session";
import nunjucks from "nunjucks";
import { fileURLToPath } from "node:url";

import type { ForwardSettings } from "./config.js";
import { csrfProtection } from "./csrf.js";
import { forwarder, v1Gate } from "./forward.js";
import { PagesSessionStore } from "./expressStore.js";
import { securityHeaders } from "./headers.js";
import { IdentityProviderUnavailable } from "./identity.js";
import type { IdentityProvider } from "./identity.js";
import { COOKIE_NAME, IDLE_SECONDS, MIN_SECRET_LENGTH, newRecord, randomToken } from "./sessionPolicy.js";
import type { SessionStore } from "./sessionStore.js";
import { isV1Path, rawPathOf } from "./v1.js";

export interface AppDeps {
  store: SessionStore;
  identityProvider: IdentityProvider;
  /** Signs the session cookie (`OSPREY_PAGES_SESSION_SECRET`). At least 32 characters; never logged. */
  sessionSecret: string;
  /** Milliseconds since the epoch. A test moves it by hand. */
  clock?: () => number;
  /** Routes a later slice adds, after the core routes and behind the same session, headers and anti-forgery. */
  extraRoutes?: (router: Router) => void;
  /** The `/v1` forwarder's settings (slice PL10). Absent: there is no forwarder, and every `/v1` path answers 404. */
  forward?: ForwardSettings;
  /** Where the forwarder says what went wrong: a fixed phrase and a status. */
  log?: (message: string) => void;
}

const VIEWS = fileURLToPath(new URL("./views", import.meta.url));

/** `Secure` and `HttpOnly` always, `SameSite=Lax`, no `Domain`: the cookie holds one signed, opaque identifier. */
const COOKIE_OPTIONS = { httpOnly: true, secure: true, sameSite: "lax", path: "/" } as const;

/** Wraps a callback-style `express-session` method as a promise. */
function callback(run: (done: (error?: unknown) => void) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    run((error) => {
      if (error) reject(error instanceof Error ? error : new Error(String(error)));
      else resolve();
    });
  });
}

export function createApp(deps: AppDeps): Express {
  if (typeof deps.sessionSecret !== "string" || deps.sessionSecret.length < MIN_SECRET_LENGTH) {
    throw new Error(`the session secret must be at least ${MIN_SECRET_LENGTH} characters`);
  }
  const clock = deps.clock ?? Date.now;
  const app = express();

  app.disable("x-powered-by");
  app.disable("etag");
  // The front proxy terminates TLS and says so in `X-Forwarded-Proto`; `express-session` sends a `Secure`
  // cookie only on a request it believes arrived over TLS. Only a hop on a private address is believed.
  app.set("trust proxy", "loopback, linklocal, uniquelocal");
  nunjucks.configure(VIEWS, { autoescape: true, express: app, noCache: false });
  app.set("view engine", "njk");

  app.use(securityHeaders());

  // No session, no secret and no call to the store or the identity provider: a probe must answer
  // when either is down. It is mounted before the session middleware so that nothing reads the store.
  app.get("/healthz", (_req, res) => {
    res.json({ status: "ok" });
  });

  // Before the session is read: with no forwarder every /v1 path is 404, and a path or method it will not carry is
  // refused here, so that nothing of the session store or the Conduit is touched for it.
  app.use(v1Gate(deps.forward !== undefined));

  app.use(
    session({
      name: COOKIE_NAME,
      secret: deps.sessionSecret,
      store: new PagesSessionStore(deps.store, clock),
      genid: randomToken,
      resave: false,
      saveUninitialized: false,
      // Sliding: each response renews the cookie and, through the store's `touch`, the key's TTL.
      rolling: true,
      cookie: { ...COOKIE_OPTIONS, maxAge: IDLE_SECONDS * 1000 },
    }),
  );
  // A /v1 body is the forwarder's to read, whole or streamed: this parser would take it, and refuse past 16 kB.
  const forms = express.urlencoded({ extended: false, limit: "16kb" });
  app.use((req, res, next) => {
    if (isV1Path(rawPathOf(req))) next();
    else forms(req, res, next);
  });
  // The anti-forgery token, for a page's own script (a meta tag in the layout) and for its forms. No endpoint returns it.
  app.use((req, res, next) => {
    res.locals["csrfToken"] = req.session?.auth?.csrfToken;
    next();
  });
  app.use(csrfProtection());

  app.get("/", (req, res) => {
    const auth = req.session.auth;
    if (!auth) {
      res.redirect(302, "/session/sign-in");
      return;
    }
    // The person's name and the anti-forgery token for the sign-out form: nothing else of the session.
    res.render("home", { displayName: auth.displayName, csrfToken: auth.csrfToken });
  });

  app.get("/session/sign-in", async (req: Request, res) => {
    let record;
    try {
      record = newRecord(await deps.identityProvider.signIn({ query: req.query }), clock());
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
    await callback((done) => {
      req.session.regenerate(done);
    });
    req.session.auth = record;
    await callback((done) => {
      req.session.save(done);
    });
    res.redirect(302, "/");
  });

  app.post("/session/sign-out", async (req, res) => {
    // The anti-forgery check has already run, so there is a session here.
    await callback((done) => {
      req.session.destroy(done);
    });
    res.clearCookie(COOKIE_NAME, COOKIE_OPTIONS);
    res.redirect(303, "/");
  });

  if (deps.extraRoutes || deps.forward) {
    const router = express.Router();
    deps.extraRoutes?.(router);
    // Behind the same headers, session and anti-forgery as every page: nothing here is reached without them.
    if (deps.forward) router.use(forwarder({ settings: deps.forward, ...(deps.log ? { log: deps.log } : {}) }));
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
