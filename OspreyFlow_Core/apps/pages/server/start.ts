/**
 * Starting the service: the function `main.ts` calls. It reads the settings (refusing, in words, when the
 * session secret is missing or short), builds the Valkey client and the app, and listens. Everything it
 * reaches for is passed in, so that a test starts the real thing with an in-memory store and a free port.
 */
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { Redis } from "ioredis";

import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { unconfiguredProvider } from "./identity.js";
import type { CodeFlowProvider, IdentityProvider } from "./identity.js";
import { createOidcFlow } from "./oidc.js";
import { ValkeySessionStore } from "./sessionStore.js";
import { attachStreamProxy } from "./stream.js";
import type { SessionStore } from "./sessionStore.js";
import { valkeyOptions } from "./valkey.js";

/** Where the service says things, and how it ends. The process's own, unless a test passes others. */
export interface Io {
  log(message: string): void;
  error(message: string): void;
  exit(code: number): void;
}

export interface StartDeps {
  /** A store to use in place of Valkey (a test's in-memory one). With none, Valkey is connected to. */
  store?: SessionStore;
  identityProvider?: IdentityProvider;
  /** The sign-in flow to use in place of the real one (`OSPREY_PAGES_OIDC_ISSUER` and the rest). */
  codeFlow?: CodeFlowProvider;
  host?: string;
  /** Milliseconds since the epoch, for the session and the live-updates proxy. A test moves it by hand. */
  clock?: () => number;
  /** How often the live-updates proxy looks at its open sockets, in milliseconds. */
  streamCheckMs?: number;
}

export interface Running {
  port: number;
  stop(): Promise<void>;
}

const processIo: Io = {
  log: (message) => console.log(message),
  error: (message) => console.error(message),
  exit: (code) => process.exit(code),
};

/**
 * Starts the service. Returns it running, or `undefined` after saying why it could not start and ending
 * with code 1. What it says never includes the session secret: `loadConfig` names the setting and the rule.
 */
export async function main(
  env: NodeJS.ProcessEnv = process.env,
  io: Io = processIo,
  deps: StartDeps = {},
): Promise<Running | undefined> {
  let config;
  try {
    config = loadConfig(env);
  } catch (error) {
    io.error(`pages: cannot start: ${error instanceof Error ? error.message : "the settings are not usable"}`);
    io.exit(1);
    return undefined;
  }

  let client: Redis | undefined;
  let store = deps.store;
  if (store === undefined) {
    client = new Redis(valkeyOptions(config));
    client.on("error", (error: Error) => {
      io.error(`pages: valkey: ${error.message}`);
    });
    store = new ValkeySessionStore(client);
  }

  // With none of the sign-in settings set there is no flow, and sign-in answers 503 as it did before it was built.
  const codeFlow = deps.codeFlow ?? (config.oidc ? createOidcFlow(config.oidc, deps.clock ? { now: deps.clock } : {}) : undefined);
  const app = createApp({
    store,
    identityProvider: deps.identityProvider ?? unconfiguredProvider,
    ...(codeFlow ? { codeFlow } : {}),
    sessionSecret: config.sessionSecret.reveal(),
    ...(deps.clock ? { clock: deps.clock } : {}),
  });
  const server = await new Promise<Server>((resolve, reject) => {
    const listening = app.listen(config.port, deps.host ?? "0.0.0.0", () => resolve(listening));
    listening.once("error", reject);
  });
  // Every WebSocket upgrade is answered here, never by a page's route: with no Conduit address set the
  // proxy is absent and each one is refused 404 (ADR-152 decision 5).
  const stream = attachStreamProxy(server, {
    settings: config.stream,
    store,
    sessionSecret: config.sessionSecret.reveal(),
    ...(deps.clock ? { clock: deps.clock } : {}),
    ...(deps.streamCheckMs === undefined ? {} : { checkMs: deps.streamCheckMs }),
    log: (message) => {
      io.error(message);
    },
  });
  const port = (server.address() as AddressInfo).port;
  io.log(`pages: listening on ${port}`);

  return {
    port,
    stop: () =>
      new Promise<void>((resolve) => {
        stream.close();
        server.close(() => {
          client?.disconnect();
          resolve();
        });
      }),
  };
}
