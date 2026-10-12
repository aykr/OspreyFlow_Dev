// A scripted, keyboard-only walkthrough of the sign-in screen — `06_DECISIONS.md` ADR-050, proving
// reachability end to end for the eighth keyboard-driven surface (`sign-in-harness.tsx`'s own
// docstring has the full reasoning). Like the other specs in this directory, this test never calls
// `page.mouse`/`.click()`.
//
// **What this proves, precisely.** Not "can Tab reach the button" — a plain native `<button>` is
// reachable by Tab for free. What needs proving is that a real keyboard `Enter` keypress reaches
// `SignInScreen`'s own `onSignIn` → the real `signIn()` in `src/auth/userManager.ts` → a real
// `oidc-client-ts` OIDC-discovery fetch → a real top-level navigation to the identity provider's
// authorization endpoint, carrying the right `client_id`, `response_type=code` and a PKCE
// `code_challenge` — real application wiring, not a mocked callback. Both the discovery fetch and
// the navigation are intercepted at the transport, the same shape `metrics-panel.spec.ts` already
// uses for a `fetch`.
import { expect, test, type Page } from "@playwright/test";

import { assertAllCovered, registerCovered, SIGN_IN_ACTIONS } from "./actionRegistry";

// `src/auth/oidcConfig.ts`'s own default derivation: this harness's origin is
// `http://localhost:5185` (`playwright.config.ts`'s `webServer`), so the computed authority is
// `http://localhost:8081/realms/osprey` — `05_DEPLOYMENT.md` §3's own default Keycloak port,
// unrelated to and not reachable from this suite; every request to it is intercepted below.
const AUTHORITY = "http://localhost:8081/realms/osprey";

async function serveIdentityProvider(page: Page) {
  await page.route(`${AUTHORITY}/.well-known/openid-configuration`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        issuer: AUTHORITY,
        authorization_endpoint: `${AUTHORITY}/protocol/openid-connect/auth`,
        token_endpoint: `${AUTHORITY}/protocol/openid-connect/token`,
        end_session_endpoint: `${AUTHORITY}/protocol/openid-connect/logout`,
        jwks_uri: `${AUTHORITY}/protocol/openid-connect/certs`,
        response_types_supported: ["code"],
        subject_types_supported: ["public"],
        id_token_signing_alg_values_supported: ["RS256"],
      }),
    });
  });
  await page.route(`${AUTHORITY}/protocol/openid-connect/auth**`, async (route) => {
    await route.fulfill({ status: 200, contentType: "text/html", body: "<html>stub IdP</html>" });
  });
}

/** Tab from the top of the page until `name` has focus — proving Tab reaches it, never focusing it
 * directly. The welcome page's header (About, the theme) comes first (ADR-115 E2). */
async function tabTo(page: Page, name: string) {
  const target = page.getByRole("button", { name, exact: true });
  await target.waitFor();
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement)) return;
  }
  await expect(target).toBeFocused();
}

test("a keyboard-activated sign-in reaches a real OIDC discovery fetch and a real authorization redirect", async ({
  page,
}) => {
  await serveIdentityProvider(page);
  await page.goto("/keyboard/sign-in-harness.html");
  await tabTo(page, "Sign in");
  await page.keyboard.press("Enter");

  await page.waitForURL(new RegExp(`${AUTHORITY}/protocol/openid-connect/auth`.replace(/\./g, "\\.")));
  const url = new URL(page.url());
  expect(url.searchParams.get("client_id")).toBe("osprey-glass");
  expect(url.searchParams.get("response_type")).toBe("code");
  expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  expect(url.searchParams.get("code_challenge")).toBeTruthy();

  registerCovered("SIGN_IN_ACTIONS", "submit-sign-in");
});

// ADR-115 decision 3: with a brokered provider configured, the organisation's button goes straight
// to it — Keycloak's `kc_idp_hint` on the real authorisation request.
test("organisation sign-in by keyboard names the organisation's provider to the identity provider", async ({ page }) => {
  await serveIdentityProvider(page);
  await page.goto("/keyboard/sign-in-harness.html?organisation=acme-entra");
  await tabTo(page, "Continue with organisation sign-in");
  await page.keyboard.press("Enter");
  await page.waitForURL(new RegExp(`${AUTHORITY}/protocol/openid-connect/auth`.replace(/\./g, "\\.")));
  const url = new URL(page.url());
  expect(url.searchParams.get("kc_idp_hint")).toBe("acme-entra");
  expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  registerCovered("SIGN_IN_ACTIONS", "continue-with-organisation-sign-in");
});

test("the welcome page's theme switches by keyboard", async ({ page }) => {
  await page.goto("/keyboard/sign-in-harness.html");
  await tabTo(page, "Light theme");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("button", { name: "Dark theme", exact: true })).toBeFocused();
  registerCovered("SIGN_IN_ACTIONS", "switch-the-welcome-theme");
});

test("every registered sign-in action has its own proving test case above", () => {
  assertAllCovered("SIGN_IN_ACTIONS", SIGN_IN_ACTIONS);
});
