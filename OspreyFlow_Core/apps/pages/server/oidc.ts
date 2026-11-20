/**
 * The authorisation-code flow against the realm (ADR-152 decisions 2, 4 and 5; ADR-050 Amendment 4; slice PL9a).
 *
 * `openid-client` runs the flow: discovery, the authorisation address with PKCE S256, `state` and `nonce`,
 * the code exchange with the client secret, and the checks on the ID token's claims. Nothing of the flow is
 * written by hand here. What this module adds is what the library leaves to the caller:
 *
 * - the ID token's **signature**, checked against the realm's key set (`jose`): the library takes a token that
 *   came straight from the token address on trust, which is the specification's right and not ours to rely on;
 * - the two outcomes ADR-044 keeps apart. The provider cannot be reached, or fails (`IdentityProviderUnavailable`,
 *   503): nothing is known to have changed about the person's access. The provider was reached and said no, or
 *   gave back something that does not verify (`IdentityProviderRefused`, 403);
 * - **the provider's words never leave this module.** An error's own message and description may hold anything
 *   the provider chose to say; what is thrown, and so logged and shown, is a fixed reason of ours.
 *
 * The access token is kept whole as the bearer the Conduit will be sent (it verifies the audience itself); the
 * refresh token is kept for the renewal that PL9b builds. Neither is read, logged or put in an error here.
 */
import { createRemoteJWKSet, errors as joseErrors, jwtVerify } from "jose";
import * as client from "openid-client";

import type { OidcSettings } from "./config.js";
import { IdentityProviderRefused, IdentityProviderUnavailable } from "./identity.js";
import type { CodeFlowProvider, PendingLogin, ProviderSession } from "./identity.js";
import { sameValue } from "./loginState.js";
import { ABSOLUTE_SECONDS } from "./sessionPolicy.js";

export const CALLBACK_PATH = "/session/callback";

/** Seconds the provider gets to answer any one request before it counts as unreachable. */
const REQUEST_TIMEOUT_SECONDS = 5;
/** Keycloak signs with RS256 unless a realm says otherwise; a token signed any other way is refused. */
const ID_TOKEN_ALGORITHMS = ["RS256"];
const CLOCK_TOLERANCE_SECONDS = 5;

export interface OidcFlowOptions {
  /** Milliseconds since the epoch, for the provider's session end. A test moves it by hand. */
  now?: () => number;
}

interface Discovered {
  config: client.Configuration;
  jwks: ReturnType<typeof createRemoteJWKSet>;
}

/** Network and time-out failures, wherever in a cause chain they sit: the provider could not be reached. */
const NETWORK_CODES = new Set([
  "ECONNREFUSED",
  "ECONNRESET",
  "ENOTFOUND",
  "EAI_AGAIN",
  "ETIMEDOUT",
  "EHOSTUNREACH",
  "ENETUNREACH",
  "UND_ERR_CONNECT_TIMEOUT",
  "UND_ERR_SOCKET",
  "UND_ERR_HEADERS_TIMEOUT",
  "UND_ERR_BODY_TIMEOUT",
]);

function causes(error: unknown): unknown[] {
  const chain: unknown[] = [];
  let current: unknown = error;
  while (current !== undefined && current !== null && chain.length < 8) {
    chain.push(current);
    current = (current as { cause?: unknown }).cause;
  }
  return chain;
}

function isUnreachable(error: unknown): boolean {
  return causes(error).some((cause) => {
    if (cause instanceof client.ResponseBodyError) return cause.status >= 500;
    // A server error with a body that is not an OAuth error (a gateway's page): the library carries the `Response` as the cause.
    if (cause instanceof Response) return cause.status >= 500;
    if (cause instanceof joseErrors.JWKSTimeout) return true;
    if (cause instanceof DOMException && (cause.name === "TimeoutError" || cause.name === "AbortError")) return true;
    const code = (cause as { code?: unknown }).code;
    if (typeof code === "string" && NETWORK_CODES.has(code)) return true;
    // `fetch` rejects with a bare `TypeError: fetch failed` when nothing answers.
    return cause instanceof TypeError;
  });
}

/**
 * The realm's key set could not be had: it answered something other than 200 (a 500, or a gateway's 502 while the realm
 * restarts), or answered something that is not a key set. jose raises those as a bare `JOSEError` (`ERR_JOSE_GENERIC`) and
 * `JWKSInvalid`; a token that merely fails to verify raises one of the specific classes (`JWSSignatureVerificationFailed`,
 * `JWTClaimValidationFailed`, `JWTExpired`, `JWKSNoMatchingKey` and the rest), which stay refusals. This is the provider
 * failing, not the provider saying no (ADR-044).
 */
function keySetFailed(error: unknown): boolean {
  return causes(error).some((cause) => {
    const code = (cause as { code?: unknown }).code;
    return cause instanceof joseErrors.JOSEError && (code === "ERR_JOSE_GENERIC" || code === "ERR_JWKS_INVALID");
  });
}

/** What a failure of the exchange is: unreachable (503) or refused (403). The words are ours, never the library's. */
function classify(error: unknown, refusal: string): IdentityProviderRefused | IdentityProviderUnavailable {
  if (isUnreachable(error)) return new IdentityProviderUnavailable("the identity provider could not be reached or failed");
  return new IdentityProviderRefused(refusal);
}

export function createOidcFlow(settings: OidcSettings, options: OidcFlowOptions = {}): CodeFlowProvider {
  const now = options.now ?? Date.now;
  const redirectUri = `${settings.publicOrigin}${CALLBACK_PATH}`;
  let discovered: Promise<Discovered> | undefined;

  /** Discovery once, kept; a failure is not kept, so the next sign-in tries again. */
  function provider(): Promise<Discovered> {
    if (discovered === undefined) {
      const issuer = new URL(settings.issuer);
      const attempt = (async (): Promise<Discovered> => {
        const config = await client.discovery(
          issuer,
          settings.clientId,
          settings.clientSecret.reveal(),
          undefined,
          {
            timeout: REQUEST_TIMEOUT_SECONDS,
            // Only a loopback address is admitted over http (config.ts), and only for a test.
            ...(issuer.protocol === "http:" ? { execute: [client.allowInsecureRequests] } : {}),
          },
        );
        const jwksUri = config.serverMetadata().jwks_uri;
        if (!jwksUri) throw new Error("the realm names no key set");
        return { config, jwks: createRemoteJWKSet(new URL(jwksUri), { timeoutDuration: REQUEST_TIMEOUT_SECONDS * 1000 }) };
      })();
      discovered = attempt;
      attempt.catch(() => {
        if (discovered === attempt) discovered = undefined;
      });
    }
    return discovered.catch(() => {
      throw new IdentityProviderUnavailable("the identity provider could not be reached or is not set up as expected");
    });
  }

  return {
    async begin() {
      const { config } = await provider();
      const verifier = client.randomPKCECodeVerifier();
      const state = client.randomState();
      const nonce = client.randomNonce();
      const url = client.buildAuthorizationUrl(config, {
        redirect_uri: redirectUri,
        scope: "openid",
        code_challenge: await client.calculatePKCECodeChallenge(verifier),
        code_challenge_method: "S256",
        state,
        nonce,
      });
      return { authorizationUrl: url.href, pending: { state, nonce, verifier } };
    },

    async complete(callback: { query: string }, pending: PendingLogin): Promise<ProviderSession> {
      const params = new URLSearchParams(callback.query);
      // Everything that can be refused without asking the provider is refused first, so the code is never spent on it.
      if (params.has("error")) throw new IdentityProviderRefused("the provider reported an error");
      if (!sameValue(params.get("state"), pending.state)) throw new IdentityProviderRefused("the state is not this sign-in's own");
      if (!params.get("code")) throw new IdentityProviderRefused("the callback carries no code");

      const { config, jwks } = await provider();
      const current = new URL(redirectUri);
      current.search = params.toString();
      let tokens;
      try {
        tokens = await client.authorizationCodeGrant(config, current, {
          pkceCodeVerifier: pending.verifier,
          expectedState: pending.state,
          expectedNonce: pending.nonce,
          idTokenExpected: true,
        });
      } catch (error) {
        throw classify(error, "the provider refused the code, or its answer did not verify");
      }

      const idToken = tokens.id_token;
      if (typeof idToken !== "string" || idToken === "") throw new IdentityProviderRefused("the answer carries no ID token");
      let claims;
      try {
        ({ payload: claims } = await jwtVerify(idToken, jwks, {
          issuer: config.serverMetadata().issuer,
          audience: settings.clientId,
          algorithms: ID_TOKEN_ALGORITHMS,
          clockTolerance: CLOCK_TOLERANCE_SECONDS,
        }));
      } catch (error) {
        if (keySetFailed(error)) throw new IdentityProviderUnavailable("the identity provider's key set could not be had");
        throw classify(error, "the ID token does not verify");
      }
      // The nonce again, on the token whose signature is now known to be the realm's.
      if (!sameValue(claims["nonce"], pending.nonce)) throw new IdentityProviderRefused("the nonce is not this sign-in's own");
      const subject = claims.sub;
      if (typeof subject !== "string" || subject === "") throw new IdentityProviderRefused("the ID token names no subject");

      const named = [claims["name"], claims["preferred_username"], subject].find(
        (value): value is string => typeof value === "string" && value !== "",
      ) as string;
      // The provider's own session ends with its refresh token (Keycloak says how long it lives); a provider
      // that says nothing leaves only the service's own absolute lifetime.
      const lasts = tokens.refresh_token === undefined ? undefined : (tokens as { refresh_expires_in?: unknown })["refresh_expires_in"];
      const seconds = typeof lasts === "number" && Number.isFinite(lasts) && lasts > 0 ? lasts : ABSOLUTE_SECONDS;
      return {
        subject,
        displayName: named,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token ?? "",
        idToken,
        idpSessionExpiresAt: now() + Math.floor(seconds) * 1000,
      };
    },
  };
}
