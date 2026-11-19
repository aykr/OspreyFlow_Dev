import type { Express, Router } from "express";

import { createApp } from "../../server/app.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { testClock } from "./clock.js";
import type { TestClock } from "./clock.js";
import { fakeProvider } from "./fakeProvider.js";
import type { FakeProviderOptions } from "./fakeProvider.js";

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
}

/** The real app factory, with the in-memory store that refuses what Valkey refuses and a fake provider. */
export function build(options: BuildOptions = {}): Built {
  const clock = testClock();
  const store = new MemorySessionStore({ clock: options.storeClock ?? clock });
  const app = createApp({
    store,
    identityProvider: fakeProvider({ now: clock, ...options.provider }),
    clock,
    extraRoutes: (router) => {
      router.all("/_test/echo", (_req, res) => {
        res.status(200).type("text/plain").send("accepted");
      });
      options.routes?.(router);
    },
  });
  return { app, store, clock };
}
