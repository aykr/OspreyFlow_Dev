import type { Express, Router } from "express";

import { createApp } from "../../server/app.js";
import type { IdentityProvider } from "../../server/identity.js";
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
}

/** The real app factory, with the in-memory store that refuses what Valkey refuses and a fake provider. */
export function build(options: BuildOptions = {}): Built {
  const clock = testClock();
  const store = new MemorySessionStore({ clock: options.storeClock ?? clock });
  const app = createApp({
    store: options.wrapStore ? options.wrapStore(store) : store,
    identityProvider: options.identityProvider ?? fakeProvider({ now: clock, ...options.provider }),
    clock,
    sessionSecret: options.sessionSecret ?? TEST_SESSION_SECRET,
    extraRoutes: (router) => {
      router.all("/_test/echo", (_req, res) => {
        res.status(200).type("text/plain").send("accepted");
      });
      options.routes?.(router);
    },
  });
  return { app, store, clock };
}
