/**
 * The identity provider, as two interfaces.
 *
 * `IdentityProvider` is the one-shot seam PL3 built: `signIn({query})` answers with a person who has
 * signed in. Only a fake (in the tests) and `unconfiguredProvider`, which says none is set up, implement it.
 *
 * `CodeFlowProvider` is the real thing (ADR-152 decisions 4 and 5, slice PL9a): the authorisation-code
 * flow with PKCE, `state` and `nonce` against the realm, in two halves because the person's browser goes
 * to the provider in between. `oidc.ts` implements it with `openid-client`. When the app is given one,
 * `/session/sign-in` is its start and `/session/callback` its end; the one-shot seam is then not used.
 */

/** What the provider says of a person who has signed in. Tokens are the server's, never the browser's. */
export interface ProviderSession {
  subject: string;
  displayName: string;
  accessToken: string;
  refreshToken: string;
  idToken?: string;
  /** Milliseconds since the epoch at which the access token ends, from the provider's `expires_in`. */
  accessTokenExpiresAt?: number;
  /** The provider's own identifier for this sign-in (`sid`), which its logout token names. */
  providerSessionId?: string;
  /** Milliseconds since the epoch at which the provider's own session ends. */
  idpSessionExpiresAt: number;
}

/**
 * The provider cannot be reached or is not set up. Not the same as access refused (ADR-044): nothing
 * about the person's access is known to have changed, and the words say so.
 */
export class IdentityProviderUnavailable extends Error {
  /**
   * True only when the request provably never reached the provider (a refused connection, a name that does not resolve, a
   * gateway's 503): it can be asked again with the same refresh token. False when it may have been received (a time-out, a
   * reset, a 500): a rotating provider may already have spent the token, and a second presentation would revoke the session.
   */
  readonly notDelivered: boolean;

  constructor(message: string, options: { notDelivered?: boolean } = {}) {
    super(message);
    this.name = "IdentityProviderUnavailable";
    this.notDelivered = options.notDelivered ?? false;
  }
}

/**
 * Why a sign-in was refused, as a word of ours from a closed list: what the service's own log says (SE8c), and nothing of
 * the provider's own words. The provider's refusals themselves stay in the provider's own log, which is where an
 * organisation reads them; the service records only the class.
 */
export const REFUSAL_REASONS = [
  "no_login_cookie",
  "no_login_record",
  "provider_error",
  "state_mismatch",
  "no_code",
  "code_refused",
  "id_token_invalid",
  "nonce_mismatch",
  "no_id_token",
  "no_subject",
  "refused",
] as const;

export type RefusalReason = (typeof REFUSAL_REASONS)[number];

export function isRefusalReason(value: unknown): value is RefusalReason {
  return typeof value === "string" && (REFUSAL_REASONS as readonly string[]).includes(value);
}

/**
 * The provider was reached and said no, or answered with something that does not verify: a refused
 * code, a state or nonce that is not the flow's own, a token for another audience, the provider's own
 * `error=` on the callback. Answered `403` in words that change nothing about the person's access, and
 * **never** in the provider's words (ADR-044: not the same as `IdentityProviderUnavailable`). What is
 * logged is `reason`, a word from `REFUSAL_REASONS`, never `message`.
 */
export class IdentityProviderRefused extends Error {
  readonly reason: RefusalReason;

  constructor(message: string, reason: RefusalReason = "refused") {
    super(message);
    this.name = "IdentityProviderRefused";
    this.reason = reason;
  }
}

/** What the start keeps on the server, under the login record, until the callback reads it once. */
export interface PendingLogin {
  state: string;
  nonce: string;
  /** The PKCE verifier: the one secret of the start, and in no response, cookie or log. */
  verifier: string;
}

/** What a refresh grant gives back, in the service's own terms. Tokens: never logged, never in an error. */
export interface RenewedTokens {
  accessToken: string;
  /** Milliseconds since the epoch; absent when neither `expires_in` nor the token's own `exp` says. */
  accessTokenExpiresAt?: number;
  /** Absent when the provider did not rotate it: the one held stays. */
  refreshToken?: string;
  idToken?: string;
  /** Milliseconds since the epoch at which the provider's own session now ends, when it says. */
  idpSessionExpiresAt?: number;
}

/**
 * Why a logout token was refused, as a word of ours from a closed list: what the service's own log says, and nothing of the
 * token. The answer to the provider is the same plain refusal for every one of them.
 */
export const LOGOUT_REFUSAL_REASONS = [
  "malformed",
  "signature",
  "issuer",
  "audience",
  "event",
  "nonce",
  "subject",
  "age",
  "jti",
  "replay",
] as const;

export type LogoutRefusalReason = (typeof LOGOUT_REFUSAL_REASONS)[number];

/** A logout token that failed a check. Nothing is ended for it. */
export class LogoutTokenRefused extends Error {
  readonly reason: LogoutRefusalReason;

  constructor(reason: LogoutRefusalReason) {
    super(`the logout token was refused: ${reason}`);
    this.name = "LogoutTokenRefused";
    this.reason = reason;
  }
}

/** What a verified logout token names. */
export interface LogoutClaims {
  /** The provider session it ends, when it names one. */
  sid?: string;
  /** The person it ends every session of, when it names one. */
  sub?: string;
  /** Its unique identifier: used once. */
  jti: string;
}

export interface CodeFlowProvider {
  /** The address to send the person to, and what the callback will need. Throws `IdentityProviderUnavailable`. */
  begin(): Promise<{ authorizationUrl: string; pending: PendingLogin }>;
  /**
   * Completes the sign-in from the address the provider sent the browser back to. Throws
   * `IdentityProviderRefused` or `IdentityProviderUnavailable`; the provider's own words are in neither.
   */
  complete(callback: { query: string }, pending: PendingLogin): Promise<ProviderSession>;
  /**
   * Exchanges a refresh token for new tokens (slice PL9b). Throws `IdentityProviderRefused` when the provider said no or
   * answered something that is not a token response, and `IdentityProviderUnavailable` (with `notDelivered` as it is) when it
   * could not be reached or failed. The provider's own words are in neither.
   */
  refresh(refreshToken: string): Promise<RenewedTokens>;
  /**
   * The provider's end-session address for a person leaving, with the ID token as the hint when there is one, the client and
   * the registered return address (slice PL9b), or `undefined` when the provider names none. Throws `IdentityProviderUnavailable`.
   */
  endSessionUrl(idToken: string | undefined): Promise<string | undefined>;
  /**
   * Checks a back-channel logout token against everything the OpenID Connect Back-Channel Logout specification asks of one
   * (signature against the provider's keys, issuer, audience, the logout event, no nonce, `sub` or `sid`, a short age, a `jti`),
   * and says what it names. Throws `LogoutTokenRefused` for any failed check and `IdentityProviderUnavailable` when the
   * provider's keys cannot be had. Whether the `jti` has been used before is the caller's to check.
   */
  verifyLogoutToken(token: string): Promise<LogoutClaims>;
}

export interface IdentityProvider {
  /** Completes a sign-in. Throws `IdentityProviderUnavailable` when the provider cannot be reached. */
  signIn(request: { query: Record<string, unknown> }): Promise<ProviderSession>;
}

/** What the service starts with until the real exchange is built: no one can sign in. */
export const unconfiguredProvider: IdentityProvider = {
  async signIn(): Promise<ProviderSession> {
    throw new IdentityProviderUnavailable("no identity provider is set up for the pages service");
  },
};
