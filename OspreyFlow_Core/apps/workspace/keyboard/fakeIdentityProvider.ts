// A fake identity provider at the transport (`page.route`), so a spec can drive the real Glass (`/`, `main.tsx`,
// `App.tsx`) signed in, with the real `oidc-client-ts` and its hidden `prompt=none` frame. Taken from
// `refresh-sign-in.spec.ts`'s fake, which models Keycloak 26's refusals (rule 15) and is measured against the live
// one there; this copy is the signed-in half only, for specs about what the signed-in Glass draws.
// Everything on the identity provider's origin is answered here, never passed on (on the Mac it is the owner's
// own deployment's port).
import { createHash } from "node:crypto";

import type { Page } from "@playwright/test";

export const IDP = "http://localhost:8081/realms/osprey";
export const API = "http://localhost:8000";

export type Refusal = "login_required" | "interaction_required" | "consent_required";

export interface FakeIdentityProvider {
  /** Keycloak's own session cookie, as far as this fake is concerned. */
  session: boolean;
  /** Every `prompt=none` round asked of it. */
  silentRounds: number;
  /** What it answers a `prompt=none` round with when there is no session. */
  refusal?: Refusal;
  /** The `prompt=none` requests, as the library sent them. */
  asked?: URLSearchParams[];
}

interface Issued {
  challenge: string;
  redirectUri: string;
  used: boolean;
}

function jwt(claims: Record<string, unknown>): string {
  const part = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "RS256", typ: "JWT" })}.${part(claims)}.c2lnbmF0dXJl`;
}


export async function fakeIdentityProvider(page: Page, idp: FakeIdentityProvider): Promise<void> {
  const issued = new Map<string, Issued>();
  // Everything on these two origins is answered here, never passed on: on the Mac they are the owner's
  // own deployment's ports (8081, 8000). Registered first, so the routes below (later, so first
  // matched) answer what they name and this answers the rest.
  await page.route("http://localhost:8081/**", (route) => route.fulfill({ status: 404, body: "" }));
  await page.route(`${IDP}/.well-known/openid-configuration`, (route) =>
    route.fulfill({
      json: {
        issuer: IDP,
        authorization_endpoint: `${IDP}/protocol/openid-connect/auth`,
        token_endpoint: `${IDP}/protocol/openid-connect/token`,
        end_session_endpoint: `${IDP}/protocol/openid-connect/logout`,
        jwks_uri: `${IDP}/protocol/openid-connect/certs`,
        authorization_response_iss_parameter_supported: true,
        code_challenge_methods_supported: ["plain", "S256"],
      },
    }),
  );
  await page.route(`${IDP}/protocol/openid-connect/auth?**`, (route) => {
    const asked = new URL(route.request().url()).searchParams;
    const redirectUri = asked.get("redirect_uri") ?? "";
    // The realm registers the Glass's root alone, exactly (`harness/realm.py`'s `_glass_client`):
    // anything else is Keycloak's error page, never a redirect.
    const origin = new URL(route.request().frame().page().url() || "http://x/").origin;
    if (asked.get("client_id") !== "osprey-glass" || redirectUri !== `${origin}/`)
      return route.fulfill({ status: 400, contentType: "text/html", body: "Invalid parameter: redirect_uri" });
    const back = new URL(redirectUri);
    back.searchParams.set("state", asked.get("state") ?? "");
    back.searchParams.set("iss", IDP);
    if (asked.get("prompt") === "none") {
      idp.silentRounds += 1;
      idp.asked?.push(asked);
      if (!idp.session) {
        back.searchParams.set("error", idp.refusal ?? "login_required");
        return route.fulfill({ status: 302, headers: { location: back.toString() } });
      }
      if (asked.get("code_challenge_method") !== "S256" || !asked.get("code_challenge"))
        return route.fulfill({ status: 400, contentType: "text/html", body: "Missing parameter: code_challenge" });
      const code = `code-${idp.silentRounds}-${Math.random().toString(36).slice(2)}`;
      issued.set(code, { challenge: asked.get("code_challenge")!, redirectUri, used: false });
      back.searchParams.set("session_state", "s1");
      back.searchParams.set("code", code);
      return route.fulfill({ status: 302, headers: { location: back.toString() } });
    }
    // The interactive sign-in is the login page; these tests never get as far as typing into it.
    return route.fulfill({ status: 200, contentType: "text/html", body: "<title>Sign in to osprey</title>" });
  });
  await page.route(`${IDP}/protocol/openid-connect/token`, (route) => {
    const form = new URLSearchParams(route.request().postData() ?? "");
    const grant = issued.get(form.get("code") ?? "");
    const verifier = form.get("code_verifier") ?? "";
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const refused =
      !idp.session ||
      form.get("grant_type") !== "authorization_code" ||
      form.get("client_id") !== "osprey-glass" ||
      !grant ||
      grant.used ||
      grant.redirectUri !== form.get("redirect_uri") ||
      grant.challenge !== challenge;
    if (grant) grant.used = true;
    if (refused) return route.fulfill({ status: 400, json: { error: "invalid_grant", error_description: "Code not valid" } });
    const now = Math.floor(Date.now() / 1000);
    const claims = { iss: IDP, aud: "osprey-glass", sub: "analyst-1", iat: now, exp: now + 300, preferred_username: "analyst1", given_name: "Ada" };
    return route.fulfill({
      json: { access_token: jwt({ ...claims, aud: "osprey-api" }), id_token: jwt(claims), token_type: "Bearer", expires_in: 300 },
    });
  });
}
