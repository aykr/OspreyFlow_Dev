/**
 * The service's settings, from its environment. The Valkey settings use the Conduit's own names
 * (`VALKEY_HOST` and the rest, `services/api/config.py`), so the renderer sets them once; the database
 * number is the service's own (ADR-152 decision 4: "under its own database number and key prefix").
 */

import { inspect } from "node:util";

const REDACTED = "[redacted]";

/**
 * A value that must never be printed or sent. Its printed form (`String`, a template literal, `util.inspect`,
 * `console.log`) and its JSON form are "[redacted]"; the value is held in a private field, so it is not an
 * own property to enumerate or copy with a spread. Using it is a deliberate call to `reveal()`.
 */
export class Secret {
  readonly #value: string;

  constructor(value: string) {
    this.#value = value;
  }

  reveal(): string {
    return this.#value;
  }

  toString(): string {
    return REDACTED;
  }

  toJSON(): string {
    return REDACTED;
  }

  [inspect.custom](): string {
    return REDACTED;
  }
}

export interface ValkeySettings {
  host: string;
  port: number;
  /** The service's own database number, never the Conduit's. */
  db: number;
  password: string | undefined;
  tls: boolean;
}

/** The live-updates proxy's settings (ADR-152 decision 5). Present only when the Conduit's address is set. */
export interface StreamSettings {
  /** The Conduit's address as `OSPREY_PAGES_CONDUIT_URL` gives it: scheme, host and port, no path. */
  conduitUrl: string;
  /** The deployment's own origin: scheme, host and port, no trailing slash. The only `Origin` an upgrade may carry. */
  publicOrigin: string;
  /** Seconds with no frame in either direction before a socket is closed. */
  idleSeconds: number;
}

export interface Config {
  port: number;
  /** Signs the session cookie. Never logged, and never in an error message; printed or turned into JSON it is "[redacted]". */
  sessionSecret: Secret;
  valkey: ValkeySettings;
  /** Absent when `OSPREY_PAGES_CONDUIT_URL` is unset: there is then no proxy, and the stream path answers 404. */
  stream?: StreamSettings;
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

const MIN_SECRET_LENGTH = 32;

function sessionSecret(env: NodeJS.ProcessEnv): Secret {
  const secret = env["OSPREY_PAGES_SESSION_SECRET"];
  if (secret === undefined || secret === "") {
    throw new Error("OSPREY_PAGES_SESSION_SECRET is required: it signs the session cookie");
  }
  // The message names the setting and the rule, never the value (not even a short one's, nor its length).
  if (secret.length < MIN_SECRET_LENGTH) {
    throw new Error(`OSPREY_PAGES_SESSION_SECRET must be at least ${MIN_SECRET_LENGTH} characters`);
  }
  return new Secret(secret);
}

const DEFAULT_STREAM_IDLE_SECONDS = 3600;
const MAX_STREAM_IDLE_SECONDS = 24 * 60 * 60;

/** Parses an address setting into `URL`, naming the setting in the words and never the value (it may carry a credential). */
function addressSetting(name: string, raw: string): URL {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${name} must be an address such as https://host:port`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error(`${name} must begin with http:// or https://`);
  if (url.username !== "" || url.password !== "") throw new Error(`${name} must not carry a user name or password`);
  if (url.search !== "" || url.hash !== "" || raw.includes("?") || raw.includes("#")) {
    throw new Error(`${name} must not carry a query or a fragment`);
  }
  return url;
}

function streamSettings(env: NodeJS.ProcessEnv): StreamSettings | undefined {
  const rawConduit = env["OSPREY_PAGES_CONDUIT_URL"];
  if (rawConduit === undefined || rawConduit === "") return undefined;
  const conduit = addressSetting("OSPREY_PAGES_CONDUIT_URL", rawConduit);
  if (conduit.pathname !== "/" || rawConduit.endsWith("//")) {
    throw new Error("OSPREY_PAGES_CONDUIT_URL must be the Conduit's address alone (scheme, host and port), with no path");
  }
  const rawOrigin = env["OSPREY_PAGES_PUBLIC_ORIGIN"];
  if (rawOrigin === undefined || rawOrigin === "") {
    throw new Error(
      "OSPREY_PAGES_PUBLIC_ORIGIN is required when OSPREY_PAGES_CONDUIT_URL is set: the live-updates proxy " +
        "refuses an upgrade from any origin but the deployment's own, and has none to compare with",
    );
  }
  const origin = addressSetting("OSPREY_PAGES_PUBLIC_ORIGIN", rawOrigin);
  // `URL.origin` is the scheme, host and port alone; anything else in the setting (a path, a trailing slash) would never equal a browser's `Origin`.
  if (rawOrigin !== origin.origin) {
    throw new Error(
      "OSPREY_PAGES_PUBLIC_ORIGIN must be the origin alone: scheme, host and port, lower case, with no path and no trailing slash",
    );
  }
  const rawIdle = env["OSPREY_PAGES_STREAM_IDLE_SECONDS"];
  const idleSeconds =
    rawIdle === undefined
      ? DEFAULT_STREAM_IDLE_SECONDS
      : wholeNumber("OSPREY_PAGES_STREAM_IDLE_SECONDS", rawIdle, MAX_STREAM_IDLE_SECONDS);
  if (idleSeconds < 1) throw new Error("OSPREY_PAGES_STREAM_IDLE_SECONDS must be at least 1");
  return { conduitUrl: conduit.origin, publicOrigin: origin.origin, idleSeconds };
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const secret = sessionSecret(env);
  const rawDb = env["OSPREY_PAGES_VALKEY_DB"];
  const db = rawDb === undefined ? DEFAULT_PAGES_DB : wholeNumber("OSPREY_PAGES_VALKEY_DB", rawDb, MAX_DB);
  const conduitDb = Number(env["VALKEY_DB"] ?? "0") || 0;
  if (db === conduitDb) {
    throw new Error(
      `OSPREY_PAGES_VALKEY_DB is ${db}, the Conduit's own database: the pages service keeps its sessions ` +
        "in a database of its own, so that nothing of either can be read or flushed as the other's",
    );
  }
  const stream = streamSettings(env);
  return {
    sessionSecret: secret,
    port: wholeNumber("OSPREY_PAGES_PORT", env["OSPREY_PAGES_PORT"] ?? "8090", 65535),
    valkey: {
      host: env["VALKEY_HOST"] ?? "localhost",
      port: wholeNumber("VALKEY_PORT", env["VALKEY_PORT"] ?? "6379", 65535),
      db,
      password: env["VALKEY_PASSWORD"] || undefined,
      tls: ["1", "true", "yes"].includes((env["VALKEY_TLS"] ?? "").toLowerCase()),
    },
    ...(stream ? { stream } : {}),
  };
}
