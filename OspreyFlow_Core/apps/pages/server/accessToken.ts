/**
 * The bearer the page service sends the Conduit for a person (ADR-152 decision 5; slice PL10).
 *
 * This is the one place that says which token a session's calls carry, and every call site awaits it. Today it
 * is the access token the session holds. PL9 (the real sign-in) replaces the body with the renewal: when the
 * token is near its end it is exchanged for a new one with the refresh token, and the session is updated. The
 * forwarder does not change when that lands.
 */
import type { SessionRecord } from "./sessionPolicy.js";

export async function accessTokenFor(session: SessionRecord): Promise<string> {
  return session.accessToken;
}
