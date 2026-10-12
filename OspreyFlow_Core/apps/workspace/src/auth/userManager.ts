// `06_DECISIONS.md` ADR-050 — the sign-in state machine. Built on `oidc-client-ts` (Apache-2.0,
// `make licence-check` — see the allowlist in `spec/00_ARCHITECTURE.md` §7) rather than hand-rolled,
// per the build brief's own instruction to prefer a maintained library over hand-rolling PKCE.
import { User, UserManager, WebStorageStateStore } from "oidc-client-ts";

import { GLASS_CLIENT_ID, oidcAuthority, postLogoutRedirectUri, redirectUri } from "./oidcConfig";

/** The four custom claims `services/api/auth.py` builds a `Principal` from, plus `sub` — exactly
 * `00_ARCHITECTURE.md` §1.3's own list: "a signed access token carrying the principal's subject,
 * clearance, organisational unit, roles and receivable handling codes." Read from the **ID**
 * token's claims (`User.profile`), which the realm's own protocol mappers carry
 * (`harness/realm.py`'s `_claim_mappers`, `id.token.claim: true`) — not re-derived from the access
 * token, which the Glass never decodes; it only ever sends that one to the Conduit as a bearer. */
export interface DisplayPrincipal {
  sub: string;
  /** The identity provider's user name (`preferred_username`); empty when the token has none. */
  username: string;
  clearance: string;
  orgUnit: string;
  roles: string[];
  receivableHandlingCodes: string[];
}

export function displayPrincipalFromUser(user: User): DisplayPrincipal {
  const profile = user.profile as Record<string, unknown>;
  const asStringArray = (value: unknown): string[] =>
    Array.isArray(value) ? value.map(String) : value != null ? [String(value)] : [];
  return {
    sub: String(profile.sub ?? ""),
    username: String(profile.preferred_username ?? ""),
    clearance: String(profile.clearance ?? ""),
    orgUnit: String(profile.org_unit ?? ""),
    roles: asStringArray(profile.roles),
    receivableHandlingCodes: asStringArray(profile.receivable_handling_codes),
  };
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
      client_id: GLASS_CLIENT_ID,
      redirect_uri: redirectUri(),
      post_logout_redirect_uri: postLogoutRedirectUri(),
      response_type: "code",
      scope: "openid",
      // The Glass drives re-authentication explicitly on a 401 / a failed silent renewal
      // (`App.tsx`'s own `reauthenticateSilently`), not via this library's background timer — the
      // ADR's own "preserve state, re-fetch" sequence is the Glass's responsibility, not a thing to
      // race against an automatic renewal firing mid-sequence.
      automaticSilentRenew: false,
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

/** `prompt=none` against the identity provider's own session cookie — `06_DECISIONS.md` ADR-050's
 * Decision section: "Re-authentication uses a silent `prompt=none` authorization request against
 * the Keycloak session cookie, which keeps the long-lived credential in the IdP's own cookie
 * rather than in storage the page can read." Resolves to `null` rather than throwing on the
 * expected failure (`login_required` — the IdP's own session has actually expired): the caller's
 * job is to decide what "no silent session" means, not to catch this function's own exception
 * type, matching `00_ARCHITECTURE.md` §1.3's "cannot reach the identity provider" vs. "the identity
 * provider said no" distinction ADR-050 carries to the Glass — a network failure here is left to
 * propagate, a `login_required` is not.
 */
export async function reauthenticateSilently(): Promise<User | null> {
  try {
    return await getUserManager().signinSilent();
  } catch (error) {
    if (error instanceof Error && error.name === "ErrorResponse") {
      return null;
    }
    throw error;
  }
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
