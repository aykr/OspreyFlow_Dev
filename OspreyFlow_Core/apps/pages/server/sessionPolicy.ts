/**
 * The session's policy: what is kept for a signed-in person, for how long, and under what name.
 *
 * ADR-152 decision 4 and ADR-050 Amendment 4. The session itself is `express-session` (ADR-152
 * decision 2); this module holds only the choices the ADR leaves open: the cookie's name, idle one hour
 * and sliding, absolute eight hours, no key's TTL longer than either or than the identity provider's own
 * session. The tokens live in the store and nowhere else; the browser holds one signed, opaque identifier.
 */
import { randomBytes } from "node:crypto";

import type { ProviderSession } from "./identity.js";
import { IdentityProviderUnavailable } from "./identity.js";

export const COOKIE_NAME = "osprey_pages";
export const IDLE_SECONDS = 60 * 60;
export const ABSOLUTE_SECONDS = 8 * 60 * 60;

/** `express-session` signs with HMAC-SHA256, so a secret shorter than the hash's own block is a weak key. */
export const MIN_SECRET_LENGTH = 32;

/** 32 random bytes as base64url: 43 characters. Used for session identifiers and anti-forgery tokens. */
export function randomToken(): string {
  return randomBytes(32).toString("base64url");
}

/** What is kept for a person who has signed in. Tokens are the server's, never the browser's. */
export interface SessionRecord {
  v: 1;
  subject: string;
  displayName: string;
  accessToken: string;
  refreshToken: string;
  idToken?: string;
  /**
   * Milliseconds since the epoch at which the access token ends, as the provider said (`expires_in`) when it was issued.
   * Absent for a token whose end is not known: `accessToken.ts` then reads the token's own `exp`, and renews nothing it cannot date.
   */
  accessTokenExpiresAt?: number;
  /** The identity provider's own identifier for this sign-in (`sid`): what its logout token names (slice PL9b). */
  idpSid?: string;
  /** How many times the access token has been renewed: a copy of the record with a lower number is out of date. */
  renewals?: number;
  /** The synchroniser token: the anti-forgery token for this session and no other. */
  csrfToken: string;
  /** Milliseconds since the epoch. */
  createdAt: number;
  idpSessionExpiresAt: number;
}

declare module "express-session" {
  interface SessionData {
    /** Present once a person has signed in; a session without it is not stored at all. */
    auth?: SessionRecord;
    /**
     * The tokens of the release folders this session has staged (slice IS5a, `staging.ts`), oldest first: the proof that a
     * token is this session's. A few opaque strings; never a folder's content.
     */
    staged?: string[];
  }
}

export function isSessionRecord(value: unknown): value is SessionRecord {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    r["v"] === 1 &&
    typeof r["subject"] === "string" &&
    typeof r["displayName"] === "string" &&
    typeof r["accessToken"] === "string" &&
    typeof r["refreshToken"] === "string" &&
    typeof r["csrfToken"] === "string" &&
    r["csrfToken"] !== "" &&
    typeof r["createdAt"] === "number" &&
    typeof r["idpSessionExpiresAt"] === "number"
  );
}

/**
 * Whole seconds a key may live from `now`: the least of the idle hour, what remains of the absolute
 * eight hours, and what remains of the identity provider's own session. Below 1 the session is over.
 */
export function ttlSeconds(record: SessionRecord, now: number): number {
  const remaining = Math.min(
    IDLE_SECONDS * 1000,
    record.createdAt + ABSOLUTE_SECONDS * 1000 - now,
    record.idpSessionExpiresAt - now,
  );
  return Math.floor(remaining / 1000);
}

/** The record for a person who has just signed in. Throws when the provider's own session has already ended. */
export function newRecord(provided: ProviderSession, now: number): SessionRecord {
  const record: SessionRecord = {
    v: 1,
    subject: provided.subject,
    displayName: provided.displayName,
    accessToken: provided.accessToken,
    refreshToken: provided.refreshToken,
    ...(provided.idToken === undefined ? {} : { idToken: provided.idToken }),
    ...(provided.accessTokenExpiresAt === undefined ? {} : { accessTokenExpiresAt: provided.accessTokenExpiresAt }),
    ...(provided.providerSessionId === undefined ? {} : { idpSid: provided.providerSessionId }),
    csrfToken: randomToken(),
    createdAt: now,
    idpSessionExpiresAt: provided.idpSessionExpiresAt,
  };
  if (ttlSeconds(record, now) < 1) throw new IdentityProviderUnavailable("the provider's own session had already ended");
  return record;
}
