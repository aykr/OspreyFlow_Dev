// `06_DECISIONS.md` ADR-050 — OIDC authorization code with PKCE against the deployment's own
// realm. This module is the one undecided design point ADR-050's own text leaves to the build
// (`process/07_BUILD_PLAN.md`'s Stage 2c entry records the call): how the Glass, whose bundle carries
// no baked address for the *Conduit* (`00_ARCHITECTURE.md` §2.6.1), locates the *identity
// provider* — a second, deliberately separate origin `00_ARCHITECTURE.md` §1.3 already names:
// "Only the workspace and the identity provider are reachable from the browser."
//
// **The call made here: the identity provider is reached directly, at its own published origin —
// not proxied through the workspace's nginx.** Two reasons. First, textual: §1.3 already describes
// two reachable origins, not one; folding Keycloak behind the workspace's proxy would need
// `KC_HTTP_RELATIVE_PATH` set to match on the server side too (Keycloak's own login page emits
// links rooted at whatever path it thinks it is serving from), which is real additional surface
// this build does not touch. Second, practical: credentials are entered *at* the identity
// provider (`00_ARCHITECTURE.md` §1.3), which means a full-page navigation to its own real address
// regardless — there is no same-origin trick available for the login page itself the way there is
// for the Conduit's JSON API.
//
// So the default here derives the identity provider's origin from the **browser's own current
// hostname** plus `05_DEPLOYMENT.md` §3's own default Keycloak port (8081) — the same default
// `harness/render.py`'s `PORT_OVERRIDES` and `harness/apply.py`'s own `--keycloak-url` flag already
// use, and Keycloak is always published (unlike the Conduit, its own publication is not gated by
// `network.expose_conduit`). `VITE_OIDC_ISSUER_ORIGIN` overrides it at build time for a deployment
// that has moved `OSPREY_KEYCLOAK_PORT` away from its default — the same shape `--keycloak-url`
// already requires an operator to pass explicitly in that case, not a new burden this build adds.
const DEFAULT_KEYCLOAK_PORT = 8081;

function identityProviderOrigin(): string {
  const override = import.meta.env.VITE_OIDC_ISSUER_ORIGIN;
  if (override) return override;
  return `${window.location.protocol}//${window.location.hostname}:${DEFAULT_KEYCLOAK_PORT}`;
}

/** `harness/apply.py`'s own `--realm` default. */
export const OIDC_REALM = import.meta.env.VITE_OIDC_REALM || "osprey";

/** `harness/realm.py`'s `GLASS_CLIENT_ID` — restated here rather than imported: this bundle has no
 * dependency on the harness, the same separation `network.public_origin`'s own schema comment
 * draws in the other direction. */
export const GLASS_CLIENT_ID = "osprey-glass";

export function oidcAuthority(): string {
  return `${identityProviderOrigin()}/realms/${OIDC_REALM}`;
}

/** The Glass's own origin — the redirect and post-logout URI both derive from this, matching
 * exactly what `harness/realm.py`'s `_glass_client` renders from `network.public_origin`. A
 * trailing slash on the redirect URI only, never on the origin itself, mirrors that renderer's own
 * `f"{origin}/"` construction. */
export function redirectUri(): string {
  return `${window.location.origin}/`;
}

export function postLogoutRedirectUri(): string {
  return window.location.origin;
}
