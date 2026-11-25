/**
 * Finding and ending a person's page sessions from the identity provider's own words (slice PL9b, back-channel logout).
 *
 * The provider's logout token names a provider session (`sid`) or a person (`sub`); the page service names its sessions by its
 * own identifier. A session records both (`idpSid`, `subject`), so a logout reads the sessions and ends the ones that match. It
 * scans the session prefix rather than keeping an index: an index is a second copy of what a session says, written on every
 * request that renews it, which could drift (a session with no entry is one a logout would leave alive), and a logout is rare and
 * comes only from the provider with a signed token. The cost is a read of every session for each logout, which this service's
 * session count (people signed in now, never more than eight hours old) keeps small.
 *
 * Nothing here is read from a token that has not been verified: `endMatching` takes the claims of a token `verifyLogoutToken` has
 * accepted, after the `jti` it carries has been used up (`useUp`).
 */
import { createHash } from "node:crypto";

import { isSessionRecord } from "./sessionPolicy.js";
import type { SessionRecord } from "./sessionPolicy.js";
import { LOGOUT_JTI_PREFIX, SESSION_KEY_PREFIX } from "./sessionStore.js";
import type { SessionStore } from "./sessionStore.js";
import { endStaged } from "./staging.js";

const SID_PATTERN = /^[A-Za-z0-9_-]{43}$/;

/** The key that remembers a logout token's `jti` once it has been used. */
export function jtiKey(jti: string): string {
  return `${LOGOUT_JTI_PREFIX}${createHash("sha256").update(jti).digest("hex")}`;
}

/** Uses a `jti` up: true the first time, false for every later presentation, and for the second of two at once. */
export function useUp(store: SessionStore, jti: string, ttlSeconds: number): Promise<boolean> {
  return store.claim(jtiKey(jti), "1", ttlSeconds);
}

interface Stored {
  auth?: unknown;
  staged?: unknown;
}

function parse(raw: string | null): Stored | undefined {
  if (raw === null) return undefined;
  try {
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? (parsed as Stored) : undefined;
  } catch {
    return undefined;
  }
}

/** Ends one page session: the folders it held and the session itself. Safe for a session already gone. */
export async function endPageSession(store: SessionStore, stagedStore: SessionStore, pageSid: string): Promise<void> {
  if (!SID_PATTERN.test(pageSid)) return;
  const key = `${SESSION_KEY_PREFIX}${pageSid}`;
  const stored = parse(await store.get(key));
  const held = Array.isArray(stored?.staged) ? stored.staged.filter((token): token is string => typeof token === "string") : undefined;
  await endStaged(stagedStore, held);
  await store.del(key);
}

/** True when a session is one the logout names. */
function named(auth: SessionRecord, claims: { sid?: string; sub?: string }): boolean {
  const own = auth.idpSid === undefined || auth.idpSid === "" ? undefined : auth.idpSid;
  // Named by provider session: the sessions that hold it, and (because a session signed in before the provider gave a `sid`
  // holds none, so cannot be told apart) those of the same person that record none.
  if (claims.sid !== undefined) {
    if (own === claims.sid) return true;
    return own === undefined && claims.sub !== undefined && auth.subject === claims.sub;
  }
  // Named by person alone: every session of theirs.
  return claims.sub !== undefined && auth.subject === claims.sub;
}

/** Ends the page sessions a verified logout token names, and says how many. */
export async function endMatching(
  store: SessionStore,
  stagedStore: SessionStore,
  claims: { sid?: string; sub?: string },
): Promise<number> {
  if (claims.sid === undefined && claims.sub === undefined) return 0;
  const ending: string[] = [];
  for (const key of await store.listKeys(SESSION_KEY_PREFIX)) {
    const pageSid = key.slice(SESSION_KEY_PREFIX.length);
    if (!SID_PATTERN.test(pageSid)) continue;
    const auth = parse(await store.get(key))?.auth;
    if (isSessionRecord(auth) && named(auth, claims)) ending.push(pageSid);
  }
  for (const pageSid of ending) await endPageSession(store, stagedStore, pageSid);
  return ending.length;
}
