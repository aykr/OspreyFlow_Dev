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
  /** Milliseconds since the epoch at which the provider's own session ends. */
  idpSessionExpiresAt: number;
}

/**
 * The provider cannot be reached or is not set up. Not the same as access refused (ADR-044): nothing
 * about the person's access is known to have changed, and the words say so.
 */
export class IdentityProviderUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IdentityProviderUnavailable";
  }
}

/**
 * The provider was reached and said no, or answered with something that does not verify: a refused
 * code, a state or nonce that is not the flow's own, a token for another audience, the provider's own
 * `error=` on the callback. Answered `403` in words that change nothing about the person's access, and
 * **never** in the provider's words (ADR-044: not the same as `IdentityProviderUnavailable`).
 */
export class IdentityProviderRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IdentityProviderRefused";
  }
}

/** What the start keeps on the server, under the login record, until the callback reads it once. */
export interface PendingLogin {
  state: string;
  nonce: string;
  /** The PKCE verifier: the one secret of the start, and in no response, cookie or log. */
  verifier: string;
}

export interface CodeFlowProvider {
  /** The address to send the person to, and what the callback will need. Throws `IdentityProviderUnavailable`. */
  begin(): Promise<{ authorizationUrl: string; pending: PendingLogin }>;
  /**
   * Completes the sign-in from the address the provider sent the browser back to. Throws
   * `IdentityProviderRefused` or `IdentityProviderUnavailable`; the provider's own words are in neither.
   */
  complete(callback: { query: string }, pending: PendingLogin): Promise<ProviderSession>;
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
