import type { IdentityProvider, ProviderSession } from "../../server/identity.js";
import { IdentityProviderUnavailable } from "../../server/identity.js";

function b64url(text: string): string {
  return Buffer.from(text, "utf8").toString("base64url");
}

/**
 * Tokens shaped like a real identity provider's (three dot-separated segments, the first starting
 * `eyJ`), each carrying a marker, so a scan for "any token anywhere" can tell a leak from chance.
 * Synthetic: they sign nothing.
 */
function sentinelToken(kind: string): string {
  return `eyJhbGciOiJSUzI1NiJ9.${b64url(JSON.stringify({ marker: `SENTINEL-${kind}`, sub: "p" }))}.sig-SENTINEL-${kind}-signature`;
}

export const SENTINEL_TOKENS = {
  accessToken: sentinelToken("ACCESS"),
  refreshToken: sentinelToken("REFRESH"),
  idToken: sentinelToken("ID"),
} as const;

export const SENTINEL_SUBJECT = "sub-SENTINEL-SUBJECT-0001";

export interface FakeProviderOptions {
  displayName?: string;
  /** How long, from the moment of sign-in, the fake identity provider's own session lasts. */
  idpSessionSeconds?: number;
  now: () => number;
  /** Makes sign-in fail as an unreachable provider does. */
  unavailable?: boolean;
}

/**
 * The identity provider as an interface, with a fake: it signs in anyone, with sentinel tokens.
 * It also models a refusal, as a real provider's unreachability is (rule 15): `unavailable` throws
 * what the interface says an unreachable provider throws.
 */
export function fakeProvider(options: FakeProviderOptions): IdentityProvider {
  return {
    async signIn(): Promise<ProviderSession> {
      if (options.unavailable) throw new IdentityProviderUnavailable("the fake provider is down");
      return {
        subject: SENTINEL_SUBJECT,
        displayName: options.displayName ?? "Alex Example",
        ...SENTINEL_TOKENS,
        idpSessionExpiresAt: options.now() + (options.idpSessionSeconds ?? 36000) * 1000,
      };
    },
  };
}
