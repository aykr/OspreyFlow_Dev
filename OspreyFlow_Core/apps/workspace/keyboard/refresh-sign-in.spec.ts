// ADR-050 Amendment 3: a refresh keeps the person signed in and where they were. This drives the real
// Glass (`/`, `main.tsx` and `App.tsx`, not a harness) and the real `oidc-client-ts`, with its hidden
// `prompt=none` frame, against a fake identity provider served at the transport (`page.route`, which
// answers the page's frames too). The fake answers as Keycloak does, refusals included (rule 15): with
// no session, `prompt=none` is answered `error=login_required` on the redirect, never a code. The
// Conduit is faked the same way, with only what the sign-in and Home read. No keyboard action is new
// (the Sign in screen is unchanged), so this file registers none; it lives here for this suite's
// server, which serves the whole workspace.
import { expect, test, type Page } from "@playwright/test";

const IDP = "http://localhost:8081/realms/osprey";
const API = "http://localhost:8000";

interface FakeIdentityProvider {
  /** Keycloak's own session cookie, as far as this fake is concerned. */
  session: boolean;
  /** Every `prompt=none` round asked of it. */
  silentRounds: number;
}

function jwt(claims: Record<string, unknown>): string {
  const part = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "RS256", typ: "JWT" })}.${part(claims)}.c2lnbmF0dXJl`;
}

async function fakeIdentityProviderAndConduit(page: Page, idp: FakeIdentityProvider): Promise<void> {
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
      },
    }),
  );
  await page.route(`${IDP}/protocol/openid-connect/auth?**`, (route) => {
    const asked = new URL(route.request().url());
    const back = new URL(asked.searchParams.get("redirect_uri")!);
    back.searchParams.set("state", asked.searchParams.get("state")!);
    if (asked.searchParams.get("prompt") === "none") {
      idp.silentRounds += 1;
      // Keycloak's refusal: no session, so no code, and no login page either.
      if (!idp.session) back.searchParams.set("error", "login_required");
      else back.searchParams.set("code", `code-${idp.silentRounds}`);
      return route.fulfill({ status: 302, headers: { location: back.toString() } });
    }
    // The interactive sign-in is the login page; these tests never get as far as typing into it.
    return route.fulfill({ status: 200, contentType: "text/html", body: "<title>Sign in to osprey</title>" });
  });
  await page.route(`${IDP}/protocol/openid-connect/token`, (route) => {
    // A code is exchanged only while the session lives, as Keycloak's would be refused after logout.
    if (!idp.session) return route.fulfill({ status: 400, json: { error: "invalid_grant" } });
    const now = Math.floor(Date.now() / 1000);
    const claims = { iss: IDP, aud: "osprey-glass", sub: "analyst-1", iat: now, exp: now + 300, preferred_username: "analyst1", given_name: "Ada" };
    return route.fulfill({
      json: { access_token: jwt({ ...claims, aud: "osprey-api" }), id_token: jwt(claims), token_type: "Bearer", expires_in: 300 },
    });
  });
  await page.route(`${API}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/me")
      return route.fulfill({ json: { id: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-a", roles: ["osprey-admin"], receivable_handling_codes: [] } });
    if (path === "/v1/me/rights")
      return route.fulfill({ json: { rights: ["investigate", "create_case", "administer_system", "manage_people"] } });
    // What the workspace reads before it draws anything, in the shapes the Conduit answers.
    if (path === "/v1/ontology")
      return route.fulfill({ json: { version: 1, entity_types: [{ name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] }], edge_types: [] } });
    if (path === "/v1/map/providers") return route.fulfill({ json: { default: "none", providers: [] } });
    if (path === "/v1/handling-scheme") return route.fulfill({ json: { classification: ["OFFICIAL"], handling_codes: {} } });
    if (path === "/v1/investigations") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: "not in this fake" } });
  });
}

const signInScreen = (page: Page) => page.getByRole("heading", { name: "Sign in", exact: true });
const home = (page: Page) => page.getByRole("heading", { level: 1, name: /, Ada$/ });
const admin = (page: Page) => page.getByRole("navigation", { name: "Admin sections" });
const openAdmin = (page: Page) => page.getByRole("button", { name: /^Open Admin/ }).click();

test("a refresh with a live identity-provider session lands signed in, on Home, without the screen", async ({ page }) => {
  const idp = { session: true, silentRounds: 0 };
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await expect(home(page)).toBeVisible();
  await expect(signInScreen(page)).toHaveCount(0);

  await page.reload();
  await expect(home(page)).toBeVisible();
  await expect(signInScreen(page)).toHaveCount(0);
  // One silent round per load, and only one.
  expect(idp.silentRounds).toBe(2);
});

test("a refresh in Admin lands in Admin, not on Home", async ({ page }) => {
  const idp = { session: true, silentRounds: 0 };
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await expect(home(page)).toBeVisible();
  await openAdmin(page);
  await expect(admin(page)).toBeVisible();

  await page.reload();
  await expect(admin(page)).toBeVisible();
  await expect(home(page)).toHaveCount(0);
  await expect(signInScreen(page)).toHaveCount(0);
});

test("a refresh with no session shows the Sign in screen with its own sentence, and the silent round is not repeated", async ({ page }) => {
  const idp = { session: false, silentRounds: 0 };
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await expect(signInScreen(page)).toBeVisible();
  await expect(page.getByText("You see only what your role, clearance and cases allow.", { exact: false })).toBeVisible();
  // Nothing about an error the person never met: the plain screen.
  await expect(page.getByText(/could not be completed|could not be started/)).toHaveCount(0);
  // A silent failure never loops: still the one round after the screen has been up a while.
  await page.waitForTimeout(3_000);
  expect(idp.silentRounds).toBe(1);
});

test("the place is kept in this tab only: a new tab with the same identity-provider session opens on Home", async ({ page, context }) => {
  const idp = { session: true, silentRounds: 0 };
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await openAdmin(page);
  await expect(admin(page)).toBeVisible();

  const other = await context.newPage();
  await fakeIdentityProviderAndConduit(other, idp);
  await other.goto("/");
  await expect(home(other)).toBeVisible();
});
