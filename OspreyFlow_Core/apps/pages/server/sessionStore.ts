/**
 * The session store: one interface, two implementations (ADR-152 decision 4).
 *
 * The deployment's Valkey runs `noeviction` (`harness/render.py`), so a key with no time limit is never
 * removed: a leak. Every write therefore carries its TTL in the same command, and the rules below are
 * enforced by both implementations. The in-memory one exists so tests run with no Valkey, and so it
 * must refuse what Valkey, as this service uses it, refuses (rule 15): a write with no TTL, a key
 * outside the service's prefix, a value over the limit. A fake that only grants proves nothing.
 */

export const SESSION_KEY_PREFIX = "pages-session:";

/**
 * A started sign-in, kept from the start to the callback (ADR-152 decision 4, slice PL9a): state, nonce and
 * the PKCE verifier, single use, ten minutes. Under its own prefix so that nothing of it is ever read as a
 * session, and every key has a limit like the rest.
 */
export const LOGIN_KEY_PREFIX = "pages-login:";

/**
 * A release folder held for a check and an import (slice IS5a), under its own prefix: a random token names it, the session that
 * staged it is the only one that can read it, and every key has a limit like the rest. It lives only in the pages process's own
 * memory (`MemorySessionStore`): the deployment's Valkey keeps its built-in save points and writes snapshots to disk, so
 * `ValkeySessionStore` refuses this prefix outright.
 */
export const STAGED_KEY_PREFIX = "pages-staged:";

/**
 * A back-channel logout token's `jti` once it has been used (slice PL9b), `pages-jti:<sha-256 of the jti>`: set only if absent
 * (`claim`), with a limit a little past the token's own life, so that the same token cannot end a session twice. Nothing else is
 * kept under it: a logout finds the sessions it names by reading the sessions themselves, not by an index.
 */
export const LOGOUT_JTI_PREFIX = "pages-jti:";

/**
 * A sign-out's last hop, held between the sign-out and the browser's next request (slice PL9b): the provider's end-session
 * address, which carries the person's ID token as the hint. One minute, single use, under its own prefix, and only in the pages
 * process's own memory (like `STAGED_KEY_PREFIX`): `ValkeySessionStore` refuses it, so the token is never written to disk.
 */
export const LOGOUT_KEY_PREFIX = "pages-logout:";

/** The most a stored session may hold. A session is a few tokens; a value past this is a defect. */
export const MAX_VALUE_BYTES = 64 * 1024;

/** The most a staged release folder may hold once written as JSON: the folder's own cap (`staging.ts`) with room for its escapes. */
export const MAX_STAGED_VALUE_BYTES = 4 * 1024 * 1024;

/** A write or a read the store will not carry out. */
export class StoreRefusal extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StoreRefusal";
  }
}

export interface SessionStore {
  get(key: string): Promise<string | null>;
  /** Stores `value` under `key` for `ttlSeconds`, whole seconds, at least 1. There is no write without one. */
  set(key: string, value: string, ttlSeconds: number): Promise<void>;
  /** Gives an existing key `ttlSeconds` more from now. False when there is no such key. */
  expire(key: string, ttlSeconds: number): Promise<boolean>;
  del(key: string): Promise<void>;
  /**
   * Reads a key and removes it in one step: of two callers at once, one gets the value and the other `null`.
   * A single-use record (a started sign-in) is read only this way.
   */
  take(key: string): Promise<string | null>;
  /** The live keys that begin with `prefix`, which must be one of this service's own. */
  listKeys(prefix: string): Promise<string[]>;
  /**
   * Stores `value` under `key` for `ttlSeconds` only when there is no live key of that name, and says whether it did: of two
   * callers at once with one key, exactly one gets `true`. How a single-use value (a logout token's `jti`) is used up.
   */
  claim(key: string, value: string, ttlSeconds: number): Promise<boolean>;
}

const PREFIXES = [SESSION_KEY_PREFIX, LOGIN_KEY_PREFIX, STAGED_KEY_PREFIX, LOGOUT_JTI_PREFIX, LOGOUT_KEY_PREFIX] as const;

function guardKey(key: string): void {
  const ok = typeof key === "string" && PREFIXES.some((prefix) => key.startsWith(prefix) && key.length > prefix.length);
  if (!ok) {
    throw new StoreRefusal(`the key is not under this service's prefixes ${PREFIXES.join(" or ")}`);
  }
}

/**
 * The Valkey store never carries a held folder (Valkey saves its keys to disk, and a folder holds recipes and mappings) nor a
 * sign-out's last hop (it holds the person's ID token).
 */
function guardNotStaged(key: string): void {
  if (typeof key === "string" && (key.startsWith(STAGED_KEY_PREFIX) || key.startsWith(LOGOUT_KEY_PREFIX))) {
    throw new StoreRefusal("a held release folder and a sign-out's last hop are kept in the process's memory only: Valkey saves its keys to disk");
  }
}

function guardPrefix(prefix: string): void {
  if (typeof prefix !== "string" || !PREFIXES.some((own) => prefix.startsWith(own))) {
    throw new StoreRefusal(`the prefix is not under this service's prefixes ${PREFIXES.join(" or ")}`);
  }
}

function guardTtl(ttlSeconds: unknown): asserts ttlSeconds is number {
  if (typeof ttlSeconds !== "number" || !Number.isInteger(ttlSeconds) || ttlSeconds < 1) {
    throw new StoreRefusal("every key needs a TTL of whole seconds, at least 1: Valkey runs noeviction, so one without is a leak");
  }
}

function guardValue(key: string, value: string): void {
  const limit = key.startsWith(STAGED_KEY_PREFIX) ? MAX_STAGED_VALUE_BYTES : MAX_VALUE_BYTES;
  if (typeof value !== "string" || Buffer.byteLength(value, "utf8") > limit) {
    throw new StoreRefusal(`the value is over the limit of ${limit} bytes`);
  }
}

interface Entry {
  value: string;
  expiresAt: number;
}

export class MemorySessionStore implements SessionStore {
  private readonly entries = new Map<string, Entry>();
  private readonly clock: () => number;
  private sweeper: ReturnType<typeof setInterval> | undefined;

  /**
   * `sweepEveryMs`: how often a timer removes what has expired, with nobody reading it. The store a deployment holds a release
   * folder in is one nobody has to touch again, so it asks for one; a store built without it removes only on a read or a write.
   * The timer never keeps the process alive (`unref`), and `close` stops it.
   */
  constructor(options: { clock?: () => number; sweepEveryMs?: number } = {}) {
    this.clock = options.clock ?? Date.now;
    if (options.sweepEveryMs !== undefined) {
      if (!Number.isInteger(options.sweepEveryMs) || options.sweepEveryMs < 1) {
        throw new StoreRefusal("the sweep interval must be a whole number of milliseconds, at least 1");
      }
      this.sweeper = setInterval(() => this.sweep(), options.sweepEveryMs);
      this.sweeper.unref();
    }
  }

  /** Removes every entry that has expired. */
  sweep(): void {
    for (const stored of [...this.entries.keys()]) this.live(stored);
  }

  /** Stops the sweep timer. The store still works. */
  close(): void {
    if (this.sweeper !== undefined) clearInterval(this.sweeper);
    this.sweeper = undefined;
  }

  private live(key: string): Entry | undefined {
    const entry = this.entries.get(key);
    if (entry && entry.expiresAt <= this.clock()) {
      this.entries.delete(key);
      return undefined;
    }
    return entry;
  }

  async get(key: string): Promise<string | null> {
    guardKey(key);
    return this.live(key)?.value ?? null;
  }

  async set(key: string, value: string, ttlSeconds: number): Promise<void> {
    guardKey(key);
    guardTtl(ttlSeconds);
    guardValue(key, value);
    // This store holds a release folder in the process's memory for a deployment, so a key nobody reads again must not stay:
    // every write first removes what has expired.
    this.sweep();
    this.entries.set(key, { value, expiresAt: this.clock() + ttlSeconds * 1000 });
  }

  async expire(key: string, ttlSeconds: number): Promise<boolean> {
    guardKey(key);
    guardTtl(ttlSeconds);
    const entry = this.live(key);
    if (!entry) return false;
    entry.expiresAt = this.clock() + ttlSeconds * 1000;
    return true;
  }

  async del(key: string): Promise<void> {
    guardKey(key);
    this.entries.delete(key);
  }

  /** Read and remove with no `await` between the two, so no other caller can read the value in between. */
  async take(key: string): Promise<string | null> {
    guardKey(key);
    const entry = this.live(key);
    this.entries.delete(key);
    return entry?.value ?? null;
  }

  async listKeys(prefix: string): Promise<string[]> {
    guardPrefix(prefix);
    return [...this.entries.keys()].filter((key) => key.startsWith(prefix) && this.live(key) !== undefined);
  }

  /** Checks and writes with no `await` between the two, so no other caller can claim the same key in between. */
  async claim(key: string, value: string, ttlSeconds: number): Promise<boolean> {
    guardKey(key);
    guardTtl(ttlSeconds);
    guardValue(key, value);
    if (this.live(key) !== undefined) return false;
    this.entries.set(key, { value, expiresAt: this.clock() + ttlSeconds * 1000 });
    return true;
  }

  /** For tests: how many entries the store holds, expired or not. It removes nothing, so it shows what a sweep has not yet done. */
  size(): number {
    return this.entries.size;
  }

  /** For tests: the keys that have not expired. */
  keys(): string[] {
    return [...this.entries.keys()].filter((key) => this.live(key) !== undefined);
  }

  /** For tests: whole seconds left on a key, or null when there is no such live key. */
  ttl(key: string): number | null {
    const entry = this.live(key);
    return entry ? Math.ceil((entry.expiresAt - this.clock()) / 1000) : null;
  }
}

/** What the Valkey store needs of a client: `ioredis`'s own methods, as far as they are used. */
export interface ValkeyClient {
  set(key: string, value: string, mode: "EX", seconds: number): Promise<"OK" | null>;
  /** `SET key value EX seconds NX`: only when there is no such key; `null` when there is. */
  set(key: string, value: string, mode: "EX", seconds: number, flag: "NX"): Promise<"OK" | null>;
  /** `SCAN`, as `ioredis` has it. Optional only so that a test's double need not carry it; the store refuses a scan without it. */
  scan?(cursor: string, match: "MATCH", pattern: string, count: "COUNT", n: number): Promise<[string, string[]]>;
  get(key: string): Promise<string | null>;
  expire(key: string, seconds: number): Promise<number>;
  del(...keys: string[]): Promise<number>;
  /** `GETDEL`: the value and its removal in one command (Redis 6.2, Valkey). */
  getdel(key: string): Promise<string | null>;
}

export class ValkeySessionStore implements SessionStore {
  constructor(private readonly client: ValkeyClient) {}

  async get(key: string): Promise<string | null> {
    guardKey(key);
    guardNotStaged(key);
    return this.client.get(key);
  }

  /** `SET key value EX ttl`: the value and its time limit in one command, so no key is ever without one. */
  async set(key: string, value: string, ttlSeconds: number): Promise<void> {
    guardKey(key);
    guardNotStaged(key);
    guardTtl(ttlSeconds);
    guardValue(key, value);
    await this.client.set(key, value, "EX", ttlSeconds);
  }

  async expire(key: string, ttlSeconds: number): Promise<boolean> {
    guardKey(key);
    guardNotStaged(key);
    guardTtl(ttlSeconds);
    return (await this.client.expire(key, ttlSeconds)) === 1;
  }

  async del(key: string): Promise<void> {
    guardKey(key);
    guardNotStaged(key);
    await this.client.del(key);
  }

  async take(key: string): Promise<string | null> {
    guardKey(key);
    guardNotStaged(key);
    return this.client.getdel(key);
  }

  /** `SCAN` with a glob made of the prefix alone, which holds no glob character (every prefix is this service's own). */
  async listKeys(prefix: string): Promise<string[]> {
    guardPrefix(prefix);
    guardNotStaged(prefix);
    const scan = this.client.scan?.bind(this.client);
    if (!scan) throw new StoreRefusal("this store's client cannot scan");
    const found = new Set<string>();
    let cursor = "0";
    do {
      const [next, batch] = await scan(cursor, "MATCH", `${prefix}*`, "COUNT", 200);
      for (const key of batch) found.add(key);
      cursor = next;
    } while (cursor !== "0");
    return [...found];
  }

  async claim(key: string, value: string, ttlSeconds: number): Promise<boolean> {
    guardKey(key);
    guardNotStaged(key);
    guardTtl(ttlSeconds);
    guardValue(key, value);
    return (await this.client.set(key, value, "EX", ttlSeconds, "NX")) === "OK";
  }
}
