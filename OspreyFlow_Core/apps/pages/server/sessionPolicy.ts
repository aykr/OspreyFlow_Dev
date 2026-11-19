/**
 * The session: what is kept for a signed-in person, for how long, and under what name.
 *
 * ADR-152 decision 4 and ADR-050 Amendment 4. The tokens live here, in the store, and nowhere else; the
 * browser holds one opaque identifier. The choices the ADR leaves open: 32 random bytes as base64url;
 * idle one hour, sliding; absolute eight hours; no key's TTL longer than either or than the identity
 * provider's own session. A record past its absolute lifetime is refused and deleted even when the
 * store's own expiry has not fired.
 */
import { randomBytes } from "node:crypto";

import type { ProviderSession } from "./identity.js";
import { IdentityProviderUnavailable } from "./identity.js";
import { SESSION_KEY_PREFIX } from "./sessionStore.js";
import type { SessionStore } from "./sessionStore.js";

export const COOKIE_NAME = "osprey_pages";
export const IDLE_SECONDS = 60 * 60;
export const ABSOLUTE_SECONDS = 8 * 60 * 60;

const ID_PATTERN = /^[A-Za-z0-9_-]{43}$/;

export function isSessionId(value: unknown): value is string {
  return typeof value === "string" && ID_PATTERN.test(value);
}

export interface SessionRecord {
  v: 1;
  subject: string;
  displayName: string;
  accessToken: string;
  refreshToken: string;
  idToken?: string;
  /** The synchroniser token: the anti-forgery token for this session and no other. */
  csrfToken: string;
  /** Milliseconds since the epoch. */
  createdAt: number;
  idpSessionExpiresAt: number;
}

export interface ActiveSession {
  id: string;
  record: SessionRecord;
}

function keyFor(id: string): string {
  return `${SESSION_KEY_PREFIX}${id}`;
}

function randomToken(): string {
  return randomBytes(32).toString("base64url");
}

function isRecord(value: unknown): value is SessionRecord {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    r["v"] === 1 &&
    typeof r["subject"] === "string" &&
    typeof r["displayName"] === "string" &&
    typeof r["accessToken"] === "string" &&
    typeof r["refreshToken"] === "string" &&
    typeof r["csrfToken"] === "string" &&
    typeof r["createdAt"] === "number" &&
    typeof r["idpSessionExpiresAt"] === "number"
  );
}

export class SessionService {
  constructor(
    private readonly store: SessionStore,
    private readonly clock: () => number = Date.now,
  ) {}

  /** Whole seconds a key may live from now: the least of the idle hour, the absolute remainder and the provider's remainder. */
  private ttlFor(record: SessionRecord): number {
    const now = this.clock();
    const remaining = Math.min(
      IDLE_SECONDS * 1000,
      record.createdAt + ABSOLUTE_SECONDS * 1000 - now,
      record.idpSessionExpiresAt - now,
    );
    return Math.floor(remaining / 1000);
  }

  async create(provided: ProviderSession): Promise<ActiveSession> {
    const record: SessionRecord = {
      v: 1,
      subject: provided.subject,
      displayName: provided.displayName,
      accessToken: provided.accessToken,
      refreshToken: provided.refreshToken,
      ...(provided.idToken === undefined ? {} : { idToken: provided.idToken }),
      csrfToken: randomToken(),
      createdAt: this.clock(),
      idpSessionExpiresAt: provided.idpSessionExpiresAt,
    };
    const ttl = this.ttlFor(record);
    if (ttl < 1) throw new IdentityProviderUnavailable("the provider's own session had already ended");
    const id = randomToken();
    await this.store.set(keyFor(id), JSON.stringify(record), ttl);
    return { id, record };
  }

  /** The live session for an identifier, renewed for another idle hour; null, with the key gone, when there is none. */
  async load(id: string): Promise<ActiveSession | null> {
    if (!isSessionId(id)) return null;
    const key = keyFor(id);
    const raw = await this.store.get(key);
    if (raw === null) return null;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = undefined;
    }
    if (!isRecord(parsed)) {
      await this.store.del(key);
      return null;
    }
    const ttl = this.ttlFor(parsed);
    if (ttl < 1) {
      await this.store.del(key);
      return null;
    }
    if (!(await this.store.expire(key, ttl))) return null; // it went between the read and the renewal
    return { id, record: parsed };
  }

  async destroy(id: string): Promise<void> {
    if (isSessionId(id)) await this.store.del(keyFor(id));
  }
}
