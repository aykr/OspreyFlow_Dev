/**
 * The pages service's Express application: sign-in, session, security headers, anti-forgery, and the
 * one page that says who is signed in. Built by a factory so that a test drives the real thing with an
 * in-memory store and a fake identity provider; `main.ts` builds it with Valkey.
 */
import express from "express";
import type { ErrorRequestHandler, Express, Request, Response, Router } from "express";
import session from "express-session";
import type { SessionData } from "express-session";
import nunjucks from "nunjucks";
import { fileURLToPath } from "node:url";

import { ASSETS_PREFIX, assetUrl, assetsHandler } from "./assets.js";
import type { AssetsSetting } from "./assets.js";
import { DEFAULT_BODY_STALL_MS, pageBodyStall } from "./bodyStall.js";
import { SessionEnded, accessTokenFor, createRenewal } from "./accessToken.js";
import type { Renewal, RenewalOptions } from "./accessToken.js";
import type { ForwardSettings, PagesTree } from "./config.js";
import { csrfProtection } from "./csrf.js";
import { forwarder, v1Gate } from "./forward.js";
import { PagesSessionStore } from "./expressStore.js";
import { registerPages, servedBy, uploadPathsOf } from "./pages.js";
import type { PageModule } from "./pages.js";
import { securityHeaders } from "./headers.js";
import { IdentityProviderRefused, IdentityProviderUnavailable, LogoutTokenRefused, isRefusalReason } from "./identity.js";
import type { CodeFlowProvider, IdentityProvider, LogoutRefusalReason, RefusalReason } from "./identity.js";
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
import { BACKCHANNEL_LOGOUT_PATH, LOGOUT_TOKEN_MAX_AGE_SECONDS } from "./oidc.js";
import { endMatching, useUp } from "./providerSessions.js";
import { createSessionEventReporter } from "./sessionEvents.js";
import type { SessionEventReporter } from "./sessionEvents.js";
import { COOKIE_NAME, IDLE_SECONDS, MIN_SECRET_LENGTH, newRecord, randomToken } from "./sessionPolicy.js";
import { LOGIN_KEY_PREFIX, LOGOUT_KEY_PREFIX } from "./sessionStore.js";
import { STAGED_SWEEP_MS, endStaged } from "./staging.js";
import { MemorySessionStore } from "./sessionStore.js";
import type { SessionStore } from "./sessionStore.js";
import { SIGNED_OUT_WORDS, isV1Path, rawPathOf, refuseJson } from "./v1.js";

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
  /**
   * How the access token is renewed (slice PL9b): the waits between tries of an exchange that never arrived. Renewal itself needs
   * `codeFlow`: with none there is no provider to exchange with, and no renewal.
   */
  renewal?: RenewalOptions;
}

/**
 * What the live-update proxy asks of the app for a session it has read: the access token that session's call carries, renewed
 * first (the same renewal, single flight with every page request) when it is near its end. It throws `SessionEnded` when the
 * provider will not renew; the session is then already destroyed.
 */
export type StreamTokenFor = (sid: string, session: SessionData) => Promise<string>;

/** The app's answer for the proxy, which is attached to the server and not to Express and so never meets the renewal middleware. */
export function streamTokenFor(app: Express): StreamTokenFor | undefined {
  const found: unknown = app.locals["streamTokenFor"];
  return typeof found === "function" ? (found as StreamTokenFor) : undefined;
}

/** How long a sign-out's last hop is held for the browser's next request. */
const LOGOUT_HANDOFF_SECONDS = 60;
/** A logout token's `jti` is remembered this long: its whole life, and the clock's tolerance either side, and some. */
const LOGOUT_JTI_SECONDS = LOGOUT_TOKEN_MAX_AGE_SECONDS * 2 + 60;

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

/** Under `/session`: the service's own routes (sign-in, its callback, sign-out), which are never renewed. */
function isSessionPath(req: Request): boolean {
  const path = rawPathOf(req);
  return path === "/session" || path.startsWith("/session/");
}

/** A request from a script and not a person's browser asking for a page: a `/v1` call, or one that asks for JSON and not HTML. */
function wantsJson(req: Request): boolean {
  if (isV1Path(rawPathOf(req))) return true;
  const accept = req.headers.accept ?? "";
  return accept.includes("application/json") && !accept.includes("text/html");
}

/**
 * The answer to a request whose session the provider would not renew (ADR-044: the words say nothing of why and never that
 * access was revoked). A script's call is 401 in the forwarder's own words; a page is sent to sign in again, to the address it
 * asked for (a form post, which cannot be asked for again, to the start); and a person who signed in moments ago is told so in
 * words, because sending them round again would sign them in and refuse them without end. The session is already destroyed and its
 * cookie cleared (`accessToken.ts` ends it before it throws).
 */
function answerEnded(req: Request, res: Response, ended: SessionEnded): void {
  if (res.headersSent) return;
  if (wantsJson(req)) {
    refuseJson(res, 401, SIGNED_OUT_WORDS);
    return;
  }
  if (ended.recentSignIn) {
    res.status(403).render("error", {
      title: "Sign-in refused",
      message: "Sign-in was refused. Nothing about your access has changed.",
    });
    return;
  }
  if (req.method === "GET" || req.method === "HEAD") {
    const back = req.originalUrl;
    res.redirect(302, safeReturnTo(back) === back && back !== "/" ? `/session/sign-in?returnTo=${encodeURIComponent(back)}` : "/session/sign-in");
    return;
  }
  res.redirect(303, "/session/sign-in");
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

  const codeFlow = deps.codeFlow;
  // Renewal needs a provider to exchange with: with a code flow, a request's session record is bound to it (below).
  const renewal: Renewal | undefined = codeFlow
    ? createRenewal({
        refresh: (token) => codeFlow.refresh(token),
        now: clock,
        log,
        ...(deps.renewal ? { options: deps.renewal } : {}),
      })
    : undefined;

  // The provider's own logout (back-channel, OpenID Connect Back-Channel Logout 1.0): before the session is read, because the
  // caller is the provider's server and has none; its credential is the signed token. Whatever fails answers the same plain
  // refusal, with no detail, and ends nothing.
  if (codeFlow) {
    const refuseLogout = (res: Response, reason: LogoutRefusalReason): void => {
      log(`pages: back-channel logout refused: ${reason}`);
      res.status(400).type("text/plain").send("Refused");
    };
    const logoutForm = express.urlencoded({ extended: false, limit: "16kb" });
    app.post(
      BACKCHANNEL_LOGOUT_PATH,
      (req, res, next) => {
        logoutForm(req, res, (error?: unknown) => {
          if (error) refuseLogout(res, "malformed");
          else next();
        });
      },
      async (req: Request, res: Response) => {
        const body: unknown = req.body;
        const token = typeof body === "object" && body !== null ? (body as Record<string, unknown>)["logout_token"] : undefined;
        if (typeof token !== "string") {
          refuseLogout(res, "malformed");
          return;
        }
        let claims;
        try {
          claims = await codeFlow.verifyLogoutToken(token);
        } catch (error) {
          if (error instanceof LogoutTokenRefused) {
            refuseLogout(res, error.reason);
            return;
          }
          if (error instanceof IdentityProviderUnavailable) {
            log("pages: back-channel logout not checked: the identity provider's keys could not be had");
            res.status(503).type("text/plain").send("Unavailable");
            return;
          }
          log("pages: back-channel logout failed: unexpected");
          res.status(500).type("text/plain").send("Failed");
          return;
        }
        // Used up only once it has been verified, so that a refusal never burns a genuine token; the second of two at once loses.
        if (!(await useUp(deps.store, claims.jti, LOGOUT_JTI_SECONDS))) {
          refuseLogout(res, "replay");
          return;
        }
        await endMatching(deps.store, stagedStore, claims);
        res.status(200).end();
      },
    );
  }

  const sessionStore = new PagesSessionStore(deps.store, clock);
  app.use(
    session({
      name: COOKIE_NAME,
      secret: deps.sessionSecret,
      store: sessionStore,
      genid: randomToken,
      resave: false,
      saveUninitialized: false,
      // Sliding: each response renews the cookie and, through the store's `touch`, the key's TTL.
      rolling: true,
      cookie: { ...COOKIE_OPTIONS, maxAge: IDLE_SECONDS * 1000 },
    }),
  );
  // Renewal (slice PL9b): this request's session record is bound to the renewal, and renewed now if it is near its end, so that a
  // refusal by the provider is answered here, before any page or script runs, and not inside a handler that would take it for
  // a failure of its own. A call to `accessTokenFor` later in the request renews in the same way. Nothing under `/session` is
  // bound: sign-out must not wait for a token, and sign-in has no session to renew.
  app.use(async (req, res, next) => {
    const auth = req.session?.auth;
    if (renewal === undefined || auth === undefined || isSessionPath(req)) {
      next();
      return;
    }
    let ended = false;
    renewal.bind(auth, {
      persist: () =>
        callback((done) => {
          req.session.save(done);
        }),
      end: async (reason) => {
        if (ended) return;
        ended = true;
        log(`pages: session ended: ${reason}`);
        try {
          await endStaged(stagedStore, req.session?.staged);
          await callback((done) => {
            req.session.destroy(done);
          });
        } catch {
          log("pages: session ended: the store could not be told");
        }
        res.clearCookie(COOKIE_NAME, COOKIE_OPTIONS);
      },
    });
    try {
      await accessTokenFor(auth);
    } catch (error) {
      if (error instanceof SessionEnded) {
        answerEnded(req, res, error);
        return;
      }
      next(error);
      return;
    }
    next();
  });
  // The live-update proxy (`stream.ts`) is attached to the server and handles an upgrade outside Express, so the middleware above
  // never runs for it. It is given this instead: the same renewal (so one exchange for a session however many requests and
  // reconnects meet its token's end), the same persisting of a renewal, and the same ending of a session the provider refuses.
  if (renewal !== undefined) {
    const forStream: StreamTokenFor = async (sid, record) => {
      const auth = record.auth;
      if (auth === undefined) throw new SessionEnded("unexpected", false);
      let ended = false;
      renewal.bind(auth, {
        persist: () =>
          callback((done) => {
            sessionStore.set(sid, record, done);
          }),
        end: async (reason) => {
          if (ended) return;
          ended = true;
          log(`pages: session ended: ${reason}`);
          try {
            await endStaged(stagedStore, record.staged);
            await callback((done) => {
              sessionStore.destroy(sid, done);
            });
          } catch {
            log("pages: session ended: the store could not be told");
          }
        },
      });
      return accessTokenFor(auth);
    };
    app.locals["streamTokenFor"] = forStream;
  }
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
    // a log line, and the session is deleted either way. (`/session` is never bound to the renewal: no exchange is made here.)
    let token: string | undefined;
    const idToken = req.session.auth?.idToken;
    try {
      const auth = req.session.auth;
      token = auth ? await accessTokenFor(auth) : undefined;
    } catch {
      token = undefined;
    }
    // The pages session ends first, so that a provider that cannot be reached never leaves it alive.
    await callback((done) => {
      req.session.destroy(done);
    });
    if (token !== undefined) void sessionEvents?.report("sign_out", token);
    res.clearCookie(COOKIE_NAME, COOKIE_OPTIONS);
    // Then the person's session at the provider (the owner's rule: "signed out" here must not leave them signed in there). The
    // provider's end-session address carries the ID token as its hint, so it is not sent in the answer to this form post (a
    // browser holds a redirect after a form post to `form-action 'self'`, and the token would be in a response): the answer is
    // a same-origin address with an opaque, single-use name, and the token is in the one navigation after it.
    let next = "/";
    if (codeFlow) {
      try {
        const url = await codeFlow.endSessionUrl(idToken);
        if (url !== undefined) {
          const id = randomToken();
          await stagedStore.set(`${LOGOUT_KEY_PREFIX}${id}`, url, LOGOUT_HANDOFF_SECONDS);
          next = `/session/sign-out/provider?r=${id}`;
        }
      } catch {
        // Said in fixed words: the provider's own are never kept. The pages session is already gone.
        log("pages: sign-out: the identity provider's session could not be ended from here");
      }
    }
    res.redirect(303, next);
  });

  // The last hop of a sign-out: no session (it is gone), a name the sign-out made, read once. Anything else goes home and learns nothing.
  app.get("/session/sign-out/provider", async (req, res) => {
    const id = req.query["r"];
    const url = typeof id === "string" && /^[A-Za-z0-9_-]{43}$/.test(id) ? await stagedStore.take(`${LOGOUT_KEY_PREFIX}${id}`) : null;
    res.redirect(302, url ?? "/");
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

  const onError: ErrorRequestHandler = (error: unknown, req, res, _next) => {
    // A handler asked for a token the provider would not renew: the same answer as the middleware's.
    if (error instanceof SessionEnded) {
      answerEnded(req, res, error);
      return;
    }
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
