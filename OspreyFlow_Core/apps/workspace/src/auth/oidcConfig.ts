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
//
// **Superseded for a deployment by ADR-114 Amendment 4 (stage B3): the address is read at run
// time.** A deployment serves `/deployment.json` (rendered by `harness/site.py`, mounted read-only
// into the workspace image), naming its identity provider — `id.` in front of the Glass's own name,
// through the front proxy. `loadDeploymentSettings()` reads it before the Glass draws anything. The
// default above remains only for the Vite development server, which serves no such file.
const DEFAULT_KEYCLOAK_PORT = 8081;

interface DeploymentSettings {
  identityProvider: string;
  realm: string;
  /** The marking a surface with no case data shows (ADR-115 decision 2). */
  marking: string | null;
}

let deployment: DeploymentSettings | null = null;

/** Reads `/deployment.json` once. A missing or unreadable file (the development server, which
 * answers any path with the page itself) leaves the development default in place. */
export async function loadDeploymentSettings(
  fetcher: typeof fetch = (input, init) => fetch(input, init),
): Promise<void> {
  try {
    const response = await fetcher("/deployment.json", { cache: "no-store" });
    if (!response.ok) return;
    const body = (await response.json()) as {
      identity_provider?: unknown;
      realm?: unknown;
      marking?: unknown;
    };
    if (typeof body.identity_provider === "string" && body.identity_provider) {
      deployment = {
        identityProvider: body.identity_provider.replace(/\/+$/, ""),
        realm:
          typeof body.realm === "string" && body.realm ? body.realm : "osprey",
        marking: typeof body.marking === "string" && body.marking ? body.marking : null,
      };
    }
  } catch {
    // Not a deployment: the development default stands.
  }
}

/** The deployment's marking, or `null` where there is no deployment file (the development server). */
export function deploymentMarking(): string | null {
  return deployment?.marking ?? null;
}

/** For tests: forget what was read. */
export function resetDeploymentSettings(): void {
  deployment = null;
}

function identityProviderOrigin(): string {
  if (deployment) return deployment.identityProvider;
  const override = import.meta.env.VITE_OIDC_ISSUER_ORIGIN;
  if (override) return override;
  return `${window.location.protocol}//${window.location.hostname}:${DEFAULT_KEYCLOAK_PORT}`;
}

/** `harness/apply.py`'s own `--realm` default. */
const BUILD_REALM = import.meta.env.VITE_OIDC_REALM || "osprey";

export function oidcRealm(): string {
  return deployment?.realm ?? BUILD_REALM;
}

/** `harness/realm.py`'s `GLASS_CLIENT_ID` — restated here rather than imported: this bundle has no
 * dependency on the harness, the same separation `network.public_origin`'s own schema comment
 * draws in the other direction. */
export const GLASS_CLIENT_ID = "osprey-glass";

export function oidcAuthority(): string {
  return `${identityProviderOrigin()}/realms/${oidcRealm()}`;
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
