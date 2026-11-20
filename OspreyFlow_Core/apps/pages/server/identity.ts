/**
 * The identity provider, as an interface. In this slice only a fake (in the tests) and a provider that
 * says none is set up exist; the authorization-code exchange with PKCE against Keycloak or Entra ID
 * (ADR-152 decision 4) is a later slice, and needs a real provider to prove.
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
