// ADR-132 Amendment 2: on the identity provider's sign-in page under the GOV.UK brand, the shared
// light and dark script holds the page light and draws no theme button, and `govuk_chrome.js` adds
// the GOV.UK header, service navigation, skip link and footer. Without the brand, the script
// behaves as before.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(new URL("../../../OspreyFlow_Core/package.json", import.meta.url));
const { JSDOM } = require("jsdom");
const THEME = readFileSync(new URL("../../../OspreyFlow_Core/harness/theme_cookie.js", import.meta.url), "utf8");
const CHROME = readFileSync(new URL("../../../OspreyFlow_Core/harness/govuk_chrome.js", import.meta.url), "utf8");

/** A page like Keycloak's sign-in page, with the scripts run in the order the theme loads them. */
function page({ brand, cookie = "ospreyflow_theme=dark", settings } = {}) {
  const dom = new JSDOM(
    '<!doctype html><html><head></head><body><main><form id="kc-form-login"><input name="username"></form></main></body></html>',
    { url: "http://id.govuk.ospreyflow.localhost:8081/realms/osprey/", runScripts: "outside-only" },
  );
  dom.window.document.cookie = cookie;
  if (brand) dom.window.eval(`document.documentElement.setAttribute("data-brand", "${brand}");`);
  dom.window.eval(THEME);
  if (settings) {
    dom.window.eval(`window.OSPREY_GOVUK = ${JSON.stringify(settings)};`);
    dom.window.eval(CHROME);
  }
  return dom.window;
}

const SETTINGS = {
  serviceName: "Prison Intelligence",
  organisation: null,
  phase: "beta",
  glassOrigin: "http://govuk.ospreyflow.localhost:8081",
};

test("under GOV.UK the page is light whatever was chosen, with no theme button", () => {
  const win = page({ brand: "govuk" });
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "light");
  assert.equal(win.document.getElementById("osprey-theme-toggle"), null);
  win.ospreyTheme.set("dark");
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "light");
});

test("without a brand the saved choice and the button are as before", () => {
  const win = page({});
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "dark");
  assert.ok(win.document.getElementById("osprey-theme-toggle"));
});

test("the GOV.UK header, service name, skip link and footer are added in reading order", () => {
  const win = page({ brand: "govuk", settings: SETTINGS });
  // A link's name as a screen reader gets it here: its text, or the label on its logo.
  const nameOf = (a) => a.textContent.trim() || a.querySelector("[aria-label]")?.getAttribute("aria-label") || "";
  const links = [...win.document.querySelectorAll("a[href]")].map((a) => [nameOf(a), a.getAttribute("href")]);
  const names = links.map(([name]) => name);
  assert.equal(names[0], "Skip to main content");
  assert.ok(names.findIndex((n) => n.includes("GOV.UK")) > 0);
  assert.deepEqual(links.find(([n]) => n === "Prison Intelligence"), ["Prison Intelligence", SETTINGS.glassOrigin + "/"]);
  assert.deepEqual(links.find(([n]) => n === "Accessibility statement"), [
    "Accessibility statement",
    SETTINGS.glassOrigin + "/accessibility-statement.html",
  ]);
  assert.ok(names.indexOf("Cookies") > names.indexOf("Prison Intelligence"));
  const phase = win.document.querySelector('[aria-label="Service phase"]');
  assert.ok(phase && phase.textContent.includes("Beta"));
});

test("the skip link's target is the page's main content, focusable", () => {
  const win = page({ brand: "govuk", settings: SETTINGS });
  const skip = win.document.querySelector("a.govuk-skip-link");
  const target = win.document.getElementById(skip.getAttribute("href").slice(1));
  assert.ok(target && target.contains(win.document.getElementById("kc-form-login")));
  assert.equal(target.getAttribute("tabindex"), "-1");
});

test("a service name is text, never markup", () => {
  const win = page({ brand: "govuk", settings: { ...SETTINGS, serviceName: "<img src=x onerror=alert(1)>" } });
  assert.equal(win.document.querySelector("img[src=x]"), null);
});

const SIGN_IN = readFileSync(new URL("../../../OspreyFlow_Core/harness/sign_in_form.js", import.meta.url), "utf8");
const LOGIN_FORM = `<form id="kc-form-login" action="/login" method="post">
  <input id="username" name="username" type="text"><input id="password" name="password" type="password">
  <div class="pf-v5-c-login__main-footer-band"><a href="/reset">Forgot password?</a></div>
  <div id="kc-form-buttons"><button id="kc-login" name="login" type="submit">Sign in</button></div>
</form>`;

/** The card script on a sign-in page, with or without the GOV.UK brand, and no mail server. */
function card(brand) {
  const dom = new JSDOM(`<!doctype html><html><body>${LOGIN_FORM}</body></html>`, { runScripts: "outside-only" });
  if (brand) dom.window.eval(`document.documentElement.setAttribute("data-brand", "${brand}");`);
  dom.window.eval("window.OSPREY_RESET_BY_EMAIL = false;\n" + SIGN_IN);
  dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
  return dom.window.document.body.textContent;
}

test("under GOV.UK the card's words name no product; without it they say OspreyFlow", () => {
  assert.ok(card().includes("Ask your OspreyFlow administrator"), "the OspreyFlow card is unchanged");
  const govuk = card("govuk");
  assert.ok(govuk.includes("Ask your administrator"));
  assert.ok(!govuk.includes("OspreyFlow"));
});

// WCAG 3.1.1 Language of Page (A): Keycloak's `keycloak.v2` template writes `lang` on `<html>` only
// when the realm has internationalisation on, which this realm does not, so the sign-in page had
// none (found by the GDS baseline audit's axe scan of the live sign-in page, 1 November 2026).
// The shared script names the page English, as the Glass's own `index.html` does, under both brands;
// a `lang` Keycloak did write is left as it is. Shown red before the script set it.
for (const brand of [undefined, "govuk"]) {
  test(`the sign-in page is marked English (${brand ?? "ospreyflow"} brand)`, () => {
    const win = page({ brand });
    assert.equal(win.document.documentElement.getAttribute("lang"), "en");
  });
}

test("a lang Keycloak wrote is kept", () => {
  const dom = new JSDOM('<!doctype html><html lang="cy"><head></head><body></body></html>', {
    url: "http://id.ospreyflow.localhost/realms/osprey/",
    runScripts: "outside-only",
  });
  dom.window.eval(THEME);
  assert.equal(dom.window.document.documentElement.getAttribute("lang"), "cy");
});
