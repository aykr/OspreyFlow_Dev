/**
 * Starting the service: the function `main.ts` calls. It reads the settings (refusing, in words, when the
 * session secret is missing or short), builds the Valkey client and the app, and listens. Everything it
 * reaches for is passed in, so that a test starts the real thing with an in-memory store and a free port.
 */
import { createServer } from "node:http";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { Redis } from "ioredis";

import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { unconfiguredProvider } from "./identity.js";
import type { IdentityProvider } from "./identity.js";
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
  host?: string;
  /** Milliseconds since the epoch, for the session and the live-updates proxy. A test moves it by hand. */
  clock?: () => number;
  /** How often the live-updates proxy looks at its open sockets, in milliseconds. */
  streamCheckMs?: number;
}

export interface Running {
  port: number;
  /** The listening server: a test reads the timeouts it was given. */
  server: Server;
  stop(): Promise<void>;
}

/** Longer than the front proxy's idle keep-alive, so that it never reuses a connection this side is closing. */
const KEEP_ALIVE_TIMEOUT_MS = 65_000;
const HEADERS_TIMEOUT_MS = 66_000;

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

  const app = createApp({
    store,
    identityProvider: deps.identityProvider ?? unconfiguredProvider,
    sessionSecret: config.sessionSecret.reveal(),
    ...(deps.clock ? { clock: deps.clock } : {}),
    ...(config.forward ? { forward: config.forward } : {}),
    log: (message) => {
      io.error(message);
    },
  });
  // Node's own timeouts must not cut a long upload or a long read short (nginx gave an hour). The whole-request
  // timeout is off: an upload is as long as its file, and the forwarder's own silence timeout (the Conduit's
  // setting) is what ends a stalled one. The header timeout stays, above the keep-alive's, as Node requires.
  const server = createServer(
    { requestTimeout: 0, headersTimeout: HEADERS_TIMEOUT_MS, keepAliveTimeout: KEEP_ALIVE_TIMEOUT_MS },
    app,
  );
  server.timeout = 0;
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(config.port, deps.host ?? "0.0.0.0", () => resolve());
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
    server,
    stop: () =>
      new Promise<void>((resolve) => {
        stream.close();
        server.close(() => {
          client?.disconnect();
          resolve();
        });
        // A call still in flight (an upload, a long read) is ended rather than waited for.
        server.closeAllConnections();
      }),
  };
}
