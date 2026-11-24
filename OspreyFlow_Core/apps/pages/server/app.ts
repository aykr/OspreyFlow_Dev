/**
 * The pages service's Express application: sign-in, session, security headers, anti-forgery, and the
 * one page that says who is signed in. Built by a factory so that a test drives the real thing with an
 * in-memory store and a fake identity provider; `main.ts` builds it with Valkey.
 */
import express from "express";
import type { ErrorRequestHandler, Express, Request, Response, Router } from "express";
import session from "express-session";
import nunjucks from "nunjucks";
import { fileURLToPath } from "node:url";

import { ASSETS_PREFIX, assetUrl, assetsHandler } from "./assets.js";
import type { AssetsSetting } from "./assets.js";
import { DEFAULT_BODY_STALL_MS, pageBodyStall } from "./bodyStall.js";
import { accessTokenFor } from "./accessToken.js";
import type { ForwardSettings, PagesTree } from "./config.js";
import { csrfProtection } from "./csrf.js";
import { forwarder, v1Gate } from "./forward.js";
import { PagesSessionStore } from "./expressStore.js";
import { registerPages, servedBy, uploadPathsOf } from "./pages.js";
import type { PageModule } from "./pages.js";
import { securityHeaders } from "./headers.js";
import { IdentityProviderRefused, IdentityProviderUnavailable, isRefusalReason } from "./identity.js";
import type { CodeFlowProvider, IdentityProvider, RefusalReason } from "./identity.js";
import {
  LOGIN_COOKIE_NAME,
  LOGIN_COOKIE_OPTIONS,
  LOGIN_TTL_SECONDS,
  isLoginRecord,
  readLoginId,
  safeReturnTo,
  signLoginId,
} from "./loginState.js";
import type { LoginRecord } from "./loginState.js";
import { createSessionEventReporter } from "./sessionEvents.js";
import type { SessionEventReporter } from "./sessionEvents.js";
import { COOKIE_NAME, IDLE_SECONDS, MIN_SECRET_LENGTH, newRecord, randomToken } from "./sessionPolicy.js";
import { LOGIN_KEY_PREFIX } from "./sessionStore.js";
import { STAGED_SWEEP_MS, endStaged } from "./staging.js";
import { MemorySessionStore } from "./sessionStore.js";
import type { SessionStore } from "./sessionStore.js";
import { isV1Path, rawPathOf } from "./v1.js";

export interface AppDeps {
  store: SessionStore;
  /**
   * Where a release folder is held between the Studio's Releases steps. By default the app's own in-process memory, which is
   * what a deployment uses: the session store is Valkey, and Valkey saves its keys to disk (the folder holds recipes and
   * mappings, and is never written to disk). A test passes the memory store it reads.
   */
  stagedStore?: SessionStore;
  /** The one-shot seam PL3 built (a fake, or `unconfiguredProvider`). Not used for sign-in when `codeFlow` is given. */
  identityProvider: IdentityProvider;
  /**
   * The real sign-in (PL9a): with it, `GET /session/sign-in` starts the authorisation-code flow and
   * `GET /session/callback` completes it. Without it, sign-in is `identityProvider.signIn` as before, and the
   * callback answers 503.
   */
  codeFlow?: CodeFlowProvider;
  /** Signs the session cookie (`OSPREY_PAGES_SESSION_SECRET`). At least 32 characters; never logged. */
  sessionSecret: string;
  /** Milliseconds since the epoch. A test moves it by hand. */
  clock?: () => number;
  /** Routes a later slice adds, after the core routes and behind the same session, headers and anti-forgery. */
  extraRoutes?: (router: Router) => void;
  /**
   * The built browser assets: the folder `/assets/pages/*` serves and the names the layout links to. Without it there is no
   * asset route and the layout links no stylesheet (`start.ts` refuses to run a production service without it).
   */
  assets?: AssetsSetting;
  /** Pages in the route-module convention (`pages.ts`): checked now, so a fault is a refusal to start, in words. */
  pages?: readonly PageModule[];
  /**
   * The tree this service serves (`OSPREY_PAGES_TREE`, read once in `config.ts`): its templates are the folder the views are
   * searched in, and its pages are the ones of `pages` that name it. The default tree when left out.
   */
  tree?: PagesTree;
  /** The `FUNCTIONS.yaml` ids a page may name, when a test wants its own list instead of the file's. */
  functionIds?: ReadonlySet<string>;
  /** Template folders searched after the tree's own: a test's throw-away fixture page lives in one. */
  viewDirs?: readonly string[];
  /** The `/v1` forwarder's settings (slice PL10). Absent: there is no forwarder, and every `/v1` path answers 404. */
  forward?: ForwardSettings;
  /** Where the forwarder says what went wrong: a fixed phrase and a status. */
  log?: (message: string) => void;
  /** How long a browser may send nothing mid-body before its connection is ended (default 60 s; a test shortens it). */
  bodyStallMs?: number;
  /**
   * Reports a sign-in and a sign-out to the Conduit (SE8c). Absent, one is made from `forward`'s address; with no
   * address either, nothing is reported. A test gives its own to watch, or to take the call away.
   */
  sessionEvents?: SessionEventReporter;
  /** How long one report may take before it is given up (default 3 s; a test shortens it). */
  sessionEventTimeoutMs?: number;
}

/** A tree's templates (ADR-152 decisions 6 and 7: one tree per deployment). `dist/tree-<name>` in the build, which copies each. */
const treeFolder = (tree: PagesTree): string => fileURLToPath(new URL(`../tree-${tree}`, import.meta.url));

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
  const log = deps.log ?? ((message: string): void => console.error(message));
  // SE8c: a sign-in and a sign-out are reported to the Conduit, which records them. Never awaited by a response and never
  // a reason to refuse one (`sessionEvents.ts`); with no Conduit address there is nothing to report to.
  const sessionEvents =
    deps.sessionEvents ??
    (deps.forward
      ? createSessionEventReporter({
          conduitUrl: deps.forward.conduitUrl,
          log,
          ...(deps.sessionEventTimeoutMs === undefined ? {} : { timeoutMs: deps.sessionEventTimeoutMs }),
        })
      : undefined);
  // Checked before anything is built: two pages on one path, or an id that is no row of FUNCTIONS.yaml, stops the start.
  const tree = deps.tree ?? "default";
  const mountPages = deps.pages ? registerPages(deps.pages, deps.functionIds, tree) : undefined;
  const app = express();

  if (sessionEvents) app.locals["sessionEvents"] = sessionEvents;
  app.disable("x-powered-by");
  app.disable("etag");
  // The front proxy terminates TLS and says so in `X-Forwarded-Proto`; `express-session` sends a `Secure`
  // cookie only on a request it believes arrived over TLS. Only a hop on a private address is believed.
  app.set("trust proxy", "loopback, linklocal, uniquelocal");
  nunjucks.configure([treeFolder(tree), ...(deps.viewDirs ?? [])], { autoescape: true, express: app, noCache: false });
  app.set("view engine", "njk");
  // What the Studio pages (slice IS5a) read from the app: the Conduit's address and limits, the store that holds a staged
  // release folder, the clock and the log. Settings, never a request's own.
  const stagedStore = deps.stagedStore ?? new MemorySessionStore({ clock, sweepEveryMs: STAGED_SWEEP_MS });
  app.locals["studio"] = {
    forward: deps.forward,
    store: stagedStore,
    clock,
    log: deps.log ?? ((): void => undefined),
    bodyStallMs: deps.bodyStallMs ?? DEFAULT_BODY_STALL_MS,
  };

  app.use(securityHeaders());

  // The built assets, with no session: a sign-in page needs its stylesheet, and an asset is the same for everyone. Mounted
  // before the session middleware so that nothing reads the store, and after the headers so that each carries the policy.
  if (deps.assets) app.use(ASSETS_PREFIX, assetsHandler(deps.assets.dir));
  // What the layout links to and a page's template names: the stylesheet, and `asset('modules/<name>.ts')` for a script.
  const manifest = deps.assets?.manifest;
  app.use((_req, res, next) => {
    res.locals["stylesheet"] = manifest?.["pages.css"] === undefined ? undefined : assetUrl(manifest, "pages.css");
    res.locals["asset"] = (name: string): string => assetUrl(manifest, name);
    // A page's optional enhancement: its module's address when the build made it, else nothing (the page works without it).
    res.locals["assetIfBuilt"] = (name: string): string => (manifest?.[name] === undefined ? "" : assetUrl(manifest, name));
    next();
  });

  // No session, no secret and no call to the store or the identity provider: a probe must answer
  // when either is down. It is mounted before the session middleware so that nothing reads the store.
  app.get("/healthz", (_req, res) => {
    res.json({ status: "ok" });
  });

  // Before the session is read: with no forwarder every /v1 path is 404, and a path or method it will not carry is
  // refused here, so that nothing of the session store or the Conduit is touched for it.
  app.use(v1Gate(deps.forward !== undefined));
  // Node's whole-request timeout is off (`start.ts`): a page route's body that goes silent is ended here, a /v1 body in the forwarder.
  app.use(pageBodyStall(deps.bodyStallMs ?? DEFAULT_BODY_STALL_MS));

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
  app.use(csrfProtection({ uploadPaths: deps.pages ? uploadPathsOf(deps.pages.filter((page) => servedBy(page, tree))) : new Set<string>() }));

  app.get("/", (req, res) => {
    const auth = req.session.auth;
    if (!auth) {
      res.redirect(302, "/session/sign-in");
      return;
    }
    // The person's name and the anti-forgery token for the sign-out form: nothing else of the session.
    res.render("home", { displayName: auth.displayName, csrfToken: auth.csrfToken });
  });

  const unavailable = (res: Response): void => {
    res.status(503).render("error", {
      title: "Sign-in not available",
      message:
        "Sign-in is not available just now. Nothing about your access has changed. Try again in a few minutes.",
    });
  };

  // The words never include the provider's, and say nothing of why: a person who was refused learns only
  // that nothing about their access has changed. The log says the class of the refusal, a word of ours from
  // `REFUSAL_REASONS`, and never the provider's words nor an error's own message (SE8c). The attempt itself stays in
  // the identity provider's own log; nothing is reported to the Conduit for it.
  const refused = (res: Response, reason: RefusalReason): void => {
    console.error(`pages: sign-in refused: ${reason}`);
    res.status(403).render("error", {
      title: "Sign-in refused",
      message: "Sign-in was refused. Nothing about your access has changed.",
    });
  };

  /** A new identifier at every sign-in, never one the browser brought; the one it had is ended. */
  const startSession = async (req: Request, res: Response, provided: Parameters<typeof newRecord>[0], returnTo: string): Promise<void> => {
    let record;
    try {
      record = newRecord(provided, clock());
    } catch (error) {
      if (error instanceof IdentityProviderUnavailable) {
        unavailable(res);
        return;
      }
      throw error;
    }
    await callback((done) => {
      req.session.regenerate(done);
    });
    req.session.auth = record;
    await callback((done) => {
      req.session.save(done);
    });
    // Reported once the session exists, and not waited for: a sign-in is never held up or stopped by the record of it.
    void sessionEvents?.report("sign_in", await accessTokenFor(record));
    res.redirect(302, returnTo);
  };

  const codeFlow = deps.codeFlow;

  app.get("/session/sign-in", async (req: Request, res) => {
    if (codeFlow) {
      // The start of the round trip: the record of this sign-in is kept here, and the browser holds only its identifier.
      let begun;
      try {
        begun = await codeFlow.begin();
      } catch (error) {
        if (error instanceof IdentityProviderUnavailable) {
          unavailable(res);
          return;
        }
        throw error;
      }
      const id = randomToken();
      const record: LoginRecord = { v: 1, ...begun.pending, returnTo: safeReturnTo(req.query["returnTo"]), createdAt: clock() };
      await deps.store.set(`${LOGIN_KEY_PREFIX}${id}`, JSON.stringify(record), LOGIN_TTL_SECONDS);
      res.cookie(LOGIN_COOKIE_NAME, signLoginId(id, deps.sessionSecret), { ...LOGIN_COOKIE_OPTIONS, maxAge: LOGIN_TTL_SECONDS * 1000 });
      res.redirect(302, begun.authorizationUrl);
      return;
    }
    let provided;
    try {
      provided = await deps.identityProvider.signIn({ query: req.query });
    } catch (error) {
      if (error instanceof IdentityProviderUnavailable) {
        unavailable(res);
        return;
      }
      throw error;
    }
    await startSession(req, res, provided, "/");
  });

  // A GET, so the anti-forgery check does not apply and `state` does the work (ADR-152 decision 4): the
  // callback must bring the login cookie, its record must exist (and is deleted as it is read, so a second
  // use finds nothing), and the provider's `state` must be the record's own.
  app.get("/session/callback", async (req: Request, res) => {
    if (!codeFlow) {
      unavailable(res);
      return;
    }
    res.clearCookie(LOGIN_COOKIE_NAME, LOGIN_COOKIE_OPTIONS); // whatever the outcome, this sign-in is over
    const id = readLoginId(req.headers.cookie, deps.sessionSecret);
    if (id === null) {
      refused(res, "no_login_cookie");
      return;
    }
    const raw = await deps.store.take(`${LOGIN_KEY_PREFIX}${id}`);
    let pending: unknown;
    try {
      pending = raw === null ? undefined : JSON.parse(raw);
    } catch {
      pending = undefined;
    }
    if (!isLoginRecord(pending)) {
      refused(res, "no_login_record");
      return;
    }
    let provided;
    try {
      provided = await codeFlow.complete({ query: new URL(req.originalUrl, "http://pages.invalid").search.slice(1) }, pending);
    } catch (error) {
      if (error instanceof IdentityProviderRefused) {
        refused(res, isRefusalReason(error.reason) ? error.reason : "refused");
        return;
      }
      if (error instanceof IdentityProviderUnavailable) {
        console.error("pages: sign-in could not be completed: provider_unavailable");
        unavailable(res);
        return;
      }
      // Anything else came from the provider's side of the exchange and may carry its words: only the class is logged.
      console.error("pages: sign-in failed: unexpected");
      res.status(500).render("error", {
        title: "Something went wrong",
        message: "Something went wrong on our side. Try again in a few minutes.",
      });
      return;
    }
    await startSession(req, res, provided, safeReturnTo(pending.returnTo));
  });

  app.post("/session/sign-out", async (req, res) => {
    // The anti-forgery check has already run, so there is a session here. A release folder this session staged goes first.
    await endStaged(stagedStore, req.session.staged);
    // The session's token is read before the session goes, so that the Conduit can be told: reported (and not waited
    // for) only if the Conduit accepts the token, which it checks itself; an expired one is refused there and costs
    // a log line, and the session is deleted either way.
    let token: string | undefined;
    try {
      const auth = req.session.auth;
      token = auth ? await accessTokenFor(auth) : undefined;
    } catch {
      token = undefined;
    }
    await callback((done) => {
      req.session.destroy(done);
    });
    if (token !== undefined) void sessionEvents?.report("sign_out", token);
    res.clearCookie(COOKIE_NAME, COOKIE_OPTIONS);
    res.redirect(303, "/");
  });

  if (mountPages || deps.extraRoutes || deps.forward) {
    const router = express.Router();
    mountPages?.(router);
    deps.extraRoutes?.(router);
    // Behind the same headers, session and anti-forgery as every page: nothing here is reached without them.
    if (deps.forward) router.use(forwarder({
          settings: deps.forward,
          ...(deps.log ? { log: deps.log } : {}),
          ...(deps.bodyStallMs === undefined ? {} : { bodyStallMs: deps.bodyStallMs }),
        }));
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
