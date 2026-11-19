/**
 * The options the Valkey client is made with, as a pure function of the settings, so that a test can see
 * that the service's own database number reaches the client (ADR-152 decision 4: "under its own database
 * number"; the Conduit's is 0). `main.ts` builds the client from this and from nothing else.
 */
import type { Config } from "./config.js";

export interface ValkeyClientOptions {
  host: string;
  port: number;
  db: number;
  password?: string;
  tls?: Record<string, never>;
}

export function valkeyOptions(config: Config): ValkeyClientOptions {
  const { host, port, db, password, tls } = config.valkey;
  return {
    host,
    port,
    db,
    ...(password === undefined ? {} : { password }),
    ...(tls ? { tls: {} } : {}),
  };
}
