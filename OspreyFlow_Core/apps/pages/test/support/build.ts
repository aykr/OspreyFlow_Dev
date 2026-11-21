import type { Express, Router } from "express";

import { createApp } from "../../server/app.js";
import type { AssetManifest } from "../../server/assets.js";
import type { ForwardSettings } from "../../server/config.js";
import type { PageModule } from "../../server/pages.js";
import type { CodeFlowProvider, IdentityProvider } from "../../server/identity.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import type { SessionStore } from "../../server/sessionStore.js";
import { testClock } from "./clock.js";
import type { TestClock } from "./clock.js";
import { fakeProvider } from "./fakeProvider.js";
import type { FakeProviderOptions } from "./fakeProvider.js";
import { TEST_SESSION_SECRET } from "./http.js";

export interface Built {
  app: Express;
  store: MemorySessionStore;
  clock: TestClock;
}

export interface BuildOptions {
  provider?: Partial<Omit<FakeProviderOptions, "now">>;
  /** Routes a later slice would add; here, a route that answers every method. */
  routes?: (router: Router) => void;
  /** The in-memory store's own clock, when a test wants the store's expiry stopped while the app's runs on. */
  storeClock?: () => number;
  /** Wraps the in-memory store before the app sees it: a test that watches, or breaks, every call the app makes to it. */
  wrapStore?: (inner: MemorySessionStore) => SessionStore;
  /** The cookie-signing secret, when a test wants its own (a sentinel it then looks for). */
  sessionSecret?: string;
  /** Replaces the fake identity provider altogether. */
  identityProvider?: IdentityProvider;
  /** The real code flow, against a fake Keycloak: with it, `/session/sign-in` is the start of the round trip. */
  codeFlow?: CodeFlowProvider;
  /** The app's clock, when the code flow must read the same one. */
  clock?: TestClock;
  /** The built assets (the folder `/assets/pages/*` serves and the names the layout links to). */
  assets?: { dir: string; manifest: AssetManifest };
  /** Pages in the route-module convention (ADR-152 decision 6), registered behind the session and the anti-forgery check. */
  pages?: readonly PageModule[];
  /** Extra template folders, searched after the tree's: the foundation's throw-away fixture page lives in one. */
  viewDirs?: readonly string[];
  /** The `FUNCTIONS.yaml` row ids a page may name, when a test wants its own list instead of the real file's. */
  functionIds?: ReadonlySet<string>;
  /** The Conduit's address and limits (the `/v1` forwarder's settings, which the Studio pages' own calls use too). */
  forward?: ForwardSettings;
  /** Where the app says what went wrong: a test that reads the log passes a collector. */
  log?: (message: string) => void;
}

/** The real app factory, with the in-memory store that refuses what Valkey refuses and a fake provider. */
export function build(options: BuildOptions = {}): Built {
  const clock = options.clock ?? testClock();
  const store = new MemorySessionStore({ clock: options.storeClock ?? clock });
  const app = createApp({
    store: options.wrapStore ? options.wrapStore(store) : store,
    identityProvider: options.identityProvider ?? fakeProvider({ now: clock, ...options.provider }),
    ...(options.codeFlow ? { codeFlow: options.codeFlow } : {}),
    clock,
    sessionSecret: options.sessionSecret ?? TEST_SESSION_SECRET,
    ...(options.assets ? { assets: options.assets } : {}),
    ...(options.pages ? { pages: options.pages } : {}),
    ...(options.viewDirs ? { viewDirs: options.viewDirs } : {}),
    ...(options.functionIds ? { functionIds: options.functionIds } : {}),
    ...(options.forward ? { forward: options.forward } : {}),
    ...(options.log ? { log: options.log } : {}),
    extraRoutes: (router) => {
      router.all("/_test/echo", (_req, res) => {
        res.status(200).type("text/plain").send("accepted");
      });
      options.routes?.(router);
    },
  });
  return { app, store, clock };
}
