/**
 * The `express-session` store (ADR-152 decision 2: "`express-session` with a Valkey store"): the package's
 * `Store` interface over this service's key-value store (`sessionStore.ts`, which has a Valkey
 * implementation and an in-memory one that refuses what Valkey refuses).
 *
 * This is where the lifetimes are enforced, so that they hold whichever key-value store is behind it:
 * every write carries a TTL no longer than the idle hour, the absolute eight hours or the identity
 * provider's own session; a record past either is refused and deleted even when the store's own expiry
 * has not fired; and a session that is not signed in is never stored (it would have no limit to carry).
 */
import { Store } from "express-session";
import type { SessionData } from "express-session";

import { isSessionRecord, ttlSeconds } from "./sessionPolicy.js";
import { SESSION_KEY_PREFIX } from "./sessionStore.js";
import type { SessionStore } from "./sessionStore.js";

/** A session identifier as `genid` makes it: 32 random bytes as base64url. Anything else is not ours. */
const SID_PATTERN = /^[A-Za-z0-9_-]{43}$/;

type Done<T = void> = (error?: unknown, result?: T) => void;

function settle<T>(work: Promise<T>, done: (error: unknown, result?: T) => void): void {
  work.then(
    (result) => {
      done(null, result);
    },
    (error: unknown) => {
      done(error);
    },
  );
}

function keyFor(sid: string): string {
  if (!SID_PATTERN.test(sid)) throw new Error("not a session identifier this service made");
  return `${SESSION_KEY_PREFIX}${sid}`;
}

export class PagesSessionStore extends Store {
  constructor(
    private readonly kv: SessionStore,
    private readonly clock: () => number = Date.now,
  ) {
    super();
  }

  override get(sid: string, callback: (error: unknown, session?: SessionData | null) => void): void {
    settle(this.read(sid), callback);
  }

  override set(sid: string, session: SessionData, callback?: Done): void {
    settle(this.write(sid, session), (error) => callback?.(error));
  }

  /** Renews the key for another idle hour, but never past the absolute or the provider's lifetime. */
  override touch(sid: string, session: SessionData, callback?: Done): void {
    settle(this.renew(sid, session), (error) => callback?.(error));
  }

  override destroy(sid: string, callback?: Done): void {
    settle(this.remove(sid), (error) => callback?.(error));
  }

  private async read(sid: string): Promise<SessionData | null> {
    if (!SID_PATTERN.test(sid)) return null;
    const key = keyFor(sid);
    const raw = await this.kv.get(key);
    if (raw === null) return null;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = undefined;
    }
    const auth = typeof parsed === "object" && parsed !== null ? (parsed as { auth?: unknown }).auth : undefined;
    if (!isSessionRecord(auth) || ttlSeconds(auth, this.clock()) < 1) {
      await this.kv.del(key); // refused, and gone
      return null;
    }
    return parsed as SessionData;
  }

  private async write(sid: string, session: SessionData): Promise<void> {
    const key = keyFor(sid);
    const auth = session.auth;
    if (!isSessionRecord(auth)) throw new Error("a session that is not signed in is not stored");
    const ttl = ttlSeconds(auth, this.clock());
    if (ttl < 1) {
      await this.kv.del(key);
      return;
    }
    await this.kv.set(key, JSON.stringify(session), ttl);
  }

  private async renew(sid: string, session: SessionData): Promise<void> {
    const key = keyFor(sid);
    const auth = session.auth;
    if (!isSessionRecord(auth)) return;
    const ttl = ttlSeconds(auth, this.clock());
    if (ttl < 1) {
      await this.kv.del(key);
      return;
    }
    await this.kv.expire(key, ttl); // false: it went in the meantime, and there is nothing to renew
  }

  private async remove(sid: string): Promise<void> {
    if (!SID_PATTERN.test(sid)) return;
    await this.kv.del(keyFor(sid));
  }
}
