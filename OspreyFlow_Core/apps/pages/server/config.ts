/**
 * The service's settings, from its environment. The Valkey settings use the Conduit's own names
 * (`VALKEY_HOST` and the rest, `services/api/config.py`), so the renderer sets them once; the database
 * number is the service's own (ADR-152 decision 4: "under its own database number and key prefix").
 */

export interface ValkeySettings {
  host: string;
  port: number;
  /** The service's own database number, never the Conduit's. */
  db: number;
  password: string | undefined;
  tls: boolean;
}

export interface Config {
  port: number;
  valkey: ValkeySettings;
}

/** Valkey's default is 16 databases, numbered 0 to 15. */
const MAX_DB = 15;
const DEFAULT_PAGES_DB = 1;

function wholeNumber(name: string, raw: string, max: number): number {
  if (!/^\d+$/.test(raw)) throw new Error(`${name} must be a whole number, not ${JSON.stringify(raw)}`);
  const value = Number(raw);
  if (value > max) throw new Error(`${name} must be at most ${max}, not ${value}`);
  return value;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const rawDb = env["OSPREY_PAGES_VALKEY_DB"];
  const db = rawDb === undefined ? DEFAULT_PAGES_DB : wholeNumber("OSPREY_PAGES_VALKEY_DB", rawDb, MAX_DB);
  const conduitDb = Number(env["VALKEY_DB"] ?? "0") || 0;
  if (db === conduitDb) {
    throw new Error(
      `OSPREY_PAGES_VALKEY_DB is ${db}, the Conduit's own database: the pages service keeps its sessions ` +
        "in a database of its own, so that nothing of either can be read or flushed as the other's",
    );
  }
  return {
    port: wholeNumber("OSPREY_PAGES_PORT", env["OSPREY_PAGES_PORT"] ?? "8090", 65535),
    valkey: {
      host: env["VALKEY_HOST"] ?? "localhost",
      port: wholeNumber("VALKEY_PORT", env["VALKEY_PORT"] ?? "6379", 65535),
      db,
      password: env["VALKEY_PASSWORD"] || undefined,
      tls: ["1", "true", "yes"].includes((env["VALKEY_TLS"] ?? "").toLowerCase()),
    },
  };
}
