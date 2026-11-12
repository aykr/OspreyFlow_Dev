// `06_DECISIONS.md` ADR-050 — the sign-in state machine. Built on `oidc-client-ts` (Apache-2.0,
// `make licence-check` — see the allowlist in `spec/00_ARCHITECTURE.md` §7) rather than hand-rolled,
// per the build brief's own instruction to prefer a maintained library over hand-rolling PKCE.
import { User, UserManager, WebStorageStateStore } from "oidc-client-ts";

import { SIGN_IN_WINDOW_NAME } from "./callbackFrame";
import { oidcAuthority, oidcClientId, oidcScope, postLogoutRedirectUri, redirectUri } from "./oidcConfig";

/** Who signed in, as the ID token names them: the token's subject and their names, nothing more.
 * What they may see and do is the Conduit's resolved principal (`GET /v1/me`), **never a claim of
 * the token** (ADR-148 Amendment 8): on Entra ID a token's `roles` are app roles an Entra
 * administrator assigns, not OspreyFlow's, and its subject is not the principal's id (the object id
 * is). The Glass never decodes the access token; it only sends it to the Conduit as a bearer. */
export interface SignedInSession {
  /** The ID token's subject: whether a renewal is the same sign-in, and nothing else. */
  sub: string;
  /** The identity provider's user name (`preferred_username`); empty when the token has none. */
  username: string;
  /** The person's given name, for Home's greeting (ADR-115 E3); empty when the token has none. */
  givenName: string;
}

export function sessionFromUser(user: User): SignedInSession {
  const profile = user.profile as Record<string, unknown>;
  return {
    sub: String(profile.sub ?? ""),
    username: String(profile.preferred_username ?? ""),
    givenName: String(profile.given_name ?? ""),
  };
}

/** `GET /v1/me`'s answer (`schemas.rights.MeResponse`). */
export interface ResolvedPrincipal {
  id: string;
  clearance: string;
  org_unit: string;
  roles: string[];
  receivable_handling_codes: string[];
}

/** What the Glass shows and gates on: the names from the sign-in, everything else the Conduit's.
 * `sub` is the principal's id as the Conduit knows it (an Entra object id, or Keycloak's subject). */
export interface DisplayPrincipal {
  sub: string;
  username: string;
  givenName?: string;
  clearance: string;
  orgUnit: string;
  roles: string[];
  receivableHandlingCodes: string[];
}

export function displayPrincipal(session: SignedInSession | null, me: ResolvedPrincipal): DisplayPrincipal {
  return {
    sub: me.id,
    username: session?.username ?? "",
    givenName: session?.givenName ?? "",
    clearance: me.clearance,
    orgUnit: me.org_unit,
    roles: [...me.roles],
    receivableHandlingCodes: [...me.receivable_handling_codes],
  };
}

/** `GET /v1/me`, or `null` when it does not answer: the Glass then shows no role or clearance and
 * offers nothing a role gates (it fails closed; the Conduit refuses every call regardless). */
export async function fetchResolvedPrincipal(apiBaseUrl: string, bearerToken: string): Promise<ResolvedPrincipal | null> {
  try {
    const response = await fetch(`${apiBaseUrl}/v1/me`, { headers: { Authorization: `Bearer ${bearerToken}` } });
    if (!response.ok) return null;
    const body = (await response.json()) as Partial<ResolvedPrincipal>;
    if (typeof body.id !== "string" || typeof body.clearance !== "string" || !Array.isArray(body.roles)) return null;
    return {
      id: body.id,
      clearance: body.clearance,
      org_unit: typeof body.org_unit === "string" ? body.org_unit : "",
      roles: body.roles.map(String),
      receivable_handling_codes: Array.isArray(body.receivable_handling_codes) ? body.receivable_handling_codes.map(String) : [],
    };
  } catch {
    return null;
  }
}

/** A `Storage` that never touches the disk or `sessionStorage` — `06_DECISIONS.md` ADR-050's own
 * "No refresh token is stored anywhere… held in memory only," extended to the whole signed-in
 * `User` object rather than parsed apart: this deployment never requests `offline_access`
 * (`scope` below carries no such value, and the realm's own client is not configured with refresh
 * rotation), so no refresh token is ever issued to begin with — this store is what keeps even the
 * *access* token out of anything a same-origin script could read from storage after the fact.
 * `oidc-client-ts`'s own transient `stateStore` (the PKCE `code_verifier`/`state` pairing across
 * the redirect round trip) is deliberately left at its library default (`sessionStorage`):  it is
 * consumed and discarded the moment `signinRedirectCallback` runs, never the credential itself. */
class InMemoryStorage implements Storage {
  private readonly map = new Map<string, string>();

  get length(): number {
    return this.map.size;
  }

  clear(): void {
    this.map.clear();
  }

  getItem(key: string): string | null {
    return this.map.has(key) ? (this.map.get(key) as string) : null;
  }

  key(index: number): string | null {
    return Array.from(this.map.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.map.delete(key);
  }

  setItem(key: string, value: string): void {
    this.map.set(key, value);
  }
}

let manager: UserManager | undefined;

/** One instance for the process lifetime — `App.tsx` calls this rather than constructing its own,
 * so the in-memory store above is actually shared rather than reset on every re-render. */
export function getUserManager(): UserManager {
  if (!manager) {
    manager = new UserManager({
      authority: oidcAuthority(),
      client_id: oidcClientId(),
      redirect_uri: redirectUri(),
      post_logout_redirect_uri: postLogoutRedirectUri(),
      response_type: "code",
      scope: oidcScope(),
      // The library's own timer stays off. The Glass renews in the background itself
      // (`tokenRenewal.ts`, ADR-050 Amendment 1), ahead of expiry and after a refused call alike,
      // through one renewal at a time — so no automatic renewal can fire in the middle of another.
      automaticSilentRenew: false,
      // The silent round's hidden iframe loads the whole workspace bundle before it hands the answer
      // back (`callbackFrame.ts`); the library's 10 seconds is short for a cold cache.
      silentRequestTimeoutInSeconds: 20,
      // The sign-in again in place opens under this name, so the page it comes back to knows it is
      // only carrying the answer (`callbackFrame.ts`).
      popupWindowTarget: SIGN_IN_WINDOW_NAME,
      userStore: new WebStorageStateStore({ store: new InMemoryStorage() }),
    });
  }
  return manager;
}

/** The authorisation request's extras: an organisation's brokered provider is named to Keycloak
 * (`kc_idp_hint`) so it goes straight there (ADR-115 decision 3); otherwise none. */
export function signInArgs(organisationProvider: string | undefined): { extraQueryParams: Record<string, string> } | undefined {
  return organisationProvider ? { extraQueryParams: { kc_idp_hint: organisationProvider } } : undefined;
}

export function signIn(organisationProvider?: string): Promise<void> {
  return getUserManager().signinRedirect(signInArgs(organisationProvider));
}

export function completeSignInFromRedirect(): Promise<User> {
  return getUserManager().signinRedirectCallback();
}

/** The silent renewal (ADR-050 Amendment 1, `tokenRenewal.ts`): `prompt=none` against the identity
 * provider's own session cookie — `06_DECISIONS.md` ADR-050's Decision section:
 * "Re-authentication uses a silent `prompt=none` authorization request against the Keycloak session
 * cookie, which keeps the long-lived credential in the IdP's own cookie
 * rather than in storage the page can read." Resolves to `null` rather than throwing on the
 * expected failure (`login_required` — the IdP's own session has actually expired): the caller's
 * job is to decide what "no silent session" means, not to catch this function's own exception
 * type, matching `00_ARCHITECTURE.md` §1.3's "cannot reach the identity provider" vs. "the identity
 * provider said no" distinction ADR-050 carries to the Glass — a network failure here is left to
 * propagate, a `login_required` is not.
 */
export async function renewSilently(): Promise<User | null> {
  try {
    // `forceIframeAuth`: always the `prompt=none` round against the identity provider's cookie,
    // never a refresh token (ADR-050 objection 5's ruling: none is used by the browser), even though
    // Keycloak puts one in the code exchange's answer.
    return await getUserManager().signinSilent({ forceIframeAuth: true });
  } catch (error) {
    if (error instanceof Error && error.name === "ErrorResponse") {
      return null;
    }
    throw error;
  }
}

/** After the identity provider's session has ended: sign in again in a small window of its own, so
 * the workspace stays as it is behind it (ADR-050 Amendment 1). Opened from the person's own click. */
export function signInAgainInPlace(): Promise<User> {
  return getUserManager().signinPopup();
}

export function signOut(): Promise<void> {
  return getUserManager().signoutRedirect();
}

export function isSignInRedirectCallback(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.has("code") && params.has("state");
}

/** Strips `code`/`state`/`session_state` from the visible URL after the callback is consumed —
 * left in place, a reload would try to consume the same authorization code twice and fail. */
export function clearRedirectCallbackParams(): void {
  const url = new URL(window.location.href);
  for (const param of ["code", "state", "session_state", "iss"]) {
    url.searchParams.delete(param);
  }
  window.history.replaceState({}, document.title, url.toString());
}
