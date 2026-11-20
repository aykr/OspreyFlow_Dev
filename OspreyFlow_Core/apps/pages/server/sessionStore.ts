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

/** The most a stored session may hold. A session is a few tokens; a value past this is a defect. */
export const MAX_VALUE_BYTES = 64 * 1024;

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
}

function guardKey(key: string): void {
  if (typeof key !== "string" || !key.startsWith(SESSION_KEY_PREFIX) || key.length === SESSION_KEY_PREFIX.length) {
    throw new StoreRefusal(`the key is not under this service's prefix ${SESSION_KEY_PREFIX}`);
  }
}

function guardTtl(ttlSeconds: unknown): asserts ttlSeconds is number {
  if (typeof ttlSeconds !== "number" || !Number.isInteger(ttlSeconds) || ttlSeconds < 1) {
    throw new StoreRefusal("every key needs a TTL of whole seconds, at least 1: Valkey runs noeviction, so one without is a leak");
  }
}

function guardValue(value: string): void {
  if (typeof value !== "string" || Buffer.byteLength(value, "utf8") > MAX_VALUE_BYTES) {
    throw new StoreRefusal(`the value is over the limit of ${MAX_VALUE_BYTES} bytes`);
  }
}

interface Entry {
  value: string;
  expiresAt: number;
}

export class MemorySessionStore implements SessionStore {
  private readonly entries = new Map<string, Entry>();
  private readonly clock: () => number;

  constructor(options: { clock?: () => number } = {}) {
    this.clock = options.clock ?? Date.now;
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
    guardValue(value);
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
  get(key: string): Promise<string | null>;
  expire(key: string, seconds: number): Promise<number>;
  del(...keys: string[]): Promise<number>;
}

export class ValkeySessionStore implements SessionStore {
  constructor(private readonly client: ValkeyClient) {}

  async get(key: string): Promise<string | null> {
    guardKey(key);
    return this.client.get(key);
  }

  /** `SET key value EX ttl`: the value and its time limit in one command, so no key is ever without one. */
  async set(key: string, value: string, ttlSeconds: number): Promise<void> {
    guardKey(key);
    guardTtl(ttlSeconds);
    guardValue(value);
    await this.client.set(key, value, "EX", ttlSeconds);
  }

  async expire(key: string, ttlSeconds: number): Promise<boolean> {
    guardKey(key);
    guardTtl(ttlSeconds);
    return (await this.client.expire(key, ttlSeconds)) === 1;
  }

  async del(key: string): Promise<void> {
    guardKey(key);
    await this.client.del(key);
  }
}
