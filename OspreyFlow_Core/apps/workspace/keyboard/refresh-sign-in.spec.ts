// ADR-050 Amendment 3: a refresh keeps the person signed in and where they were. This drives the real
// Glass (`/`, `main.tsx` and `App.tsx`, not a harness) and the real `oidc-client-ts`, with its hidden
// `prompt=none` frame, against a fake identity provider served at the transport (`page.route`, which
// answers the page's frames too). Rule 15: the fake refuses as Keycloak 26 does where
// `tests/harness/test_refresh_silent_sign_in_keycloak.py` measures the real one — with no session,
// `prompt=none` answered `login_required` on the redirect with `state` and `iss`, never a code — and,
// beyond what was measured live, with `interaction_required` and `consent_required`, which OIDC Core
// §3.1.2.6 names for `prompt=none` and Keycloak documents but no live case here provokes; an unregistered `redirect_uri` or client is refused outright; and a code is exchanged once,
// for the PKCE verifier its challenge names and the `redirect_uri` it was given to, else
// `invalid_grant`. The request the library sends is held to `fixtures/silent-round-request.json`,
// which the live Keycloak test sends as it is. The Conduit is faked with only what the sign-in and
// Home read. No keyboard action is new (the Sign in screen is unchanged), so this file registers none.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

const IDP = "http://localhost:8081/realms/osprey";
const API = "http://localhost:8000";
const SILENT_ROUND: { path: string; fixed: Record<string, string>; random: string[] } = JSON.parse(
  readFileSync(new URL("./fixtures/silent-round-request.json", import.meta.url), "utf-8"),
);

type Refusal = "login_required" | "interaction_required" | "consent_required";

interface FakeIdentityProvider {
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

const EVERY_RIGHT = ["investigate", "create_case", "administer_system", "manage_people"];

async function fakeIdentityProviderAndConduit(page: Page, idp: FakeIdentityProvider, rights: string[] = EVERY_RIGHT): Promise<void> {
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
  await page.route(`${API}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/me")
      return route.fulfill({ json: { id: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-a", roles: ["osprey-admin"], receivable_handling_codes: [] } });
    if (path === "/v1/me/rights")
      return route.fulfill({ json: { rights } });
    // What the workspace reads before it draws anything, in the shapes the Conduit answers.
    if (path === "/v1/ontology")
      return route.fulfill({ json: { version: 1, entity_types: [{ name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] }], edge_types: [] } });
    if (path === "/v1/map/providers") return route.fulfill({ json: { default: "none", providers: [] } });
    if (path === "/v1/handling-scheme") return route.fulfill({ json: { classification: ["OFFICIAL"], handling_codes: {} } });
    if (path === "/v1/investigations") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: "not in this fake" } });
  });
}

// Home or Admin is drawn only after the silent round, whose hidden frame loads the whole workspace
// from the development server (on the test server, at times past the default five seconds).
const afterTheRound = expect.configure({ timeout: 15_000 });
const signInScreen = (page: Page) => page.getByRole("heading", { name: "Sign in", exact: true });
const home = (page: Page) => page.getByRole("heading", { level: 1, name: /, Ada$/ });
const admin = (page: Page) => page.getByRole("navigation", { name: "Admin sections" });
const openAdmin = (page: Page) => page.getByRole("button", { name: /^Open Admin/ }).click();

test("a refresh with a live identity-provider session lands signed in, on Home, without the screen", async ({ page }) => {
  const idp = { session: true, silentRounds: 0 };
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await afterTheRound(home(page)).toBeVisible();
  await expect(signInScreen(page)).toHaveCount(0);

  await page.reload();
  await afterTheRound(home(page)).toBeVisible();
  await expect(signInScreen(page)).toHaveCount(0);
  // One silent round per load, and only one.
  expect(idp.silentRounds).toBe(2);
});

test("a refresh in Admin lands in Admin, not on Home", async ({ page }) => {
  const idp = { session: true, silentRounds: 0 };
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await afterTheRound(home(page)).toBeVisible();
  await openAdmin(page);
  await afterTheRound(admin(page)).toBeVisible();

  await page.reload();
  await afterTheRound(admin(page)).toBeVisible();
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
  await afterTheRound(admin(page)).toBeVisible();

  const other = await context.newPage();
  await fakeIdentityProviderAndConduit(other, idp);
  await other.goto("/");
  await afterTheRound(home(other)).toBeVisible();
});

test("a kept Admin for a person whose rights do not open it lands on Home, and Home is kept", async ({ page }) => {
  // The tab was Admin for someone else (their session ended without signing out); this person may
  // only investigate. The place grants nothing (ADR-145 N6).
  const idp = { session: true, silentRounds: 0 };
  await fakeIdentityProviderAndConduit(page, idp, ["investigate", "create_case"]);
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("seeded")) {
      sessionStorage.setItem("seeded", "1");
      sessionStorage.setItem("ospreyflow.place", "admin");
    }
  });
  await page.goto("/");
  await afterTheRound(home(page)).toBeVisible();
  await expect(admin(page)).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("ospreyflow.place"))).toBe("home");
});

for (const refusal of ["login_required", "interaction_required", "consent_required"] as const) {
  test(`Keycloak's ${refusal} on the silent round falls to the Sign in screen, asked once`, async ({ page }) => {
    const idp: FakeIdentityProvider = { session: false, silentRounds: 0, refusal };
    await fakeIdentityProviderAndConduit(page, idp);
    await page.goto("/");
    await expect(signInScreen(page)).toBeVisible();
    await expect(page.getByText(/could not be completed|could not be started/)).toHaveCount(0);
    await page.waitForTimeout(1_500);
    expect(idp.silentRounds).toBe(1);
  });
}

test("the silent round is the request the live Keycloak test sends (fixtures/silent-round-request.json)", async ({ page }) => {
  const idp: FakeIdentityProvider = { session: true, silentRounds: 0, asked: [] };
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await afterTheRound(home(page)).toBeVisible();
  const [sent] = idp.asked!;
  const origin = new URL(page.url()).origin;
  const fixed = Object.fromEntries(
    [...sent!.entries()].filter(([k]) => !SILENT_ROUND.random.includes(k)).map(([k, v]) => [k, v.replace(origin, "<origin>")]),
  );
  expect(new URL(`${IDP}/protocol/openid-connect/auth`).pathname.replace("/realms/osprey", "")).toBe(SILENT_ROUND.path);
  expect(fixed).toEqual(SILENT_ROUND.fixed);
  expect([...sent!.keys()].filter((k) => SILENT_ROUND.random.includes(k)).sort()).toEqual([...SILENT_ROUND.random].sort());
});

test("a code is exchanged once: the fake refuses it again, as Keycloak does", async ({ page }) => {
  const idp: FakeIdentityProvider = { session: true, silentRounds: 0 };
  let first = "";
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/protocol/openid-connect/token") && !first) first = r.postData() ?? "";
  });
  await fakeIdentityProviderAndConduit(page, idp);
  await page.goto("/");
  await afterTheRound(home(page)).toBeVisible();
  // The library's own exchange, sent again whole: the same code, verifier and redirect_uri. Only
  // the code having been used can refuse it.
  expect(new URLSearchParams(first).get("code_verifier")).toBeTruthy();
  const again = await page.evaluate(
    async ([token, body]) =>
      (await fetch(token!, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body })).status,
    [`${IDP}/protocol/openid-connect/token`, first],
  );
  expect(again).toBe(400);
});
