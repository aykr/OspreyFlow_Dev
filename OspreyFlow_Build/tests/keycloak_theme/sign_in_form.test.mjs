// ADR-115 E2: the sign-in card's behaviour on Keycloak's own pages (`harness/sign_in_form.js`), run
// in jsdom against the markup Keycloak 26.0.8 rendered when measured: `#kc-form-login` with
// `#username`, `#password` and `#kc-login`; `#kc-reset-password-form` with `#username`. Validation is
// on submit, never on keystroke, in the handoff's own words; a field in error says so to assistive
// technology (`aria-invalid`, `aria-describedby`). The live proof against a real Keycloak is
// `tests/harness/test_sign_in_page_live.py`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(new URL("../../../OspreyFlow_Core/package.json", import.meta.url));
const { JSDOM } = require("jsdom");
const SCRIPT = readFileSync(new URL("../../../OspreyFlow_Core/harness/sign_in_form.js", import.meta.url), "utf8");

const LOGIN = `
<h1 id="kc-page-title">Sign in</h1>
<form id="kc-form-login" action="/login" method="post">
  <div class="pf-v5-c-form__group"><label for="username">Email or username</label>
    <span class="pf-v5-c-form-control"><input id="username" name="username" type="text"></span></div>
  <div class="pf-v5-c-form__group"><label for="password">Password</label>
    <div class="pf-v5-c-input-group"><span class="pf-v5-c-form-control"><input id="password" name="password" type="password"></span></div></div>
  __FORGOT__
  <div id="kc-form-buttons"><button id="kc-login" name="login" type="submit">Sign in</button></div>
</form>`;
// Keycloak 26.0.8's login form disables its button as it submits (`onsubmit="login.disabled = true;
// return true;"`, read from a live page): a refused submit must give the button back, or a corrected
// form cannot be sent at all — found by the live test, which timed out on the second click.
const FORGOT = `<div class="pf-v5-c-login__main-footer-band"><a href="/reset">Forgot password?</a></div>`;
const RESET = `
<h1 id="kc-page-title">Reset your password</h1>
<form id="kc-reset-password-form" action="/reset" method="post">
  <div class="pf-v5-c-form__group"><label for="username">Email or username</label>
    <span class="pf-v5-c-form-control"><input id="username" name="username" type="text"></span></div>
  <div class="pf-v5-c-form__group"><div class="pf-v5-c-form__actions">
    <button id="kc-form-buttons" type="submit">Submit</button>
    <a class="pf-v5-c-button pf-m-secondary pf-m-block" href="/login">Back to sign in</a></div></div>
</form>
<div id="kc-info" class="login-pf-signup"><div id="kc-info-wrapper">For OspreyFlow accounts only.</div></div>`;

function page(body, { resetByEmail = true, keycloakDisables = false } = {}) {
  const dom = new JSDOM(`<!doctype html><body>${body}</body>`, { runScripts: "outside-only" });
  if (keycloakDisables) {
    // What a browser does with Keycloak's `onsubmit="login.disabled = true; return true;"`: an
    // inline handler, registered at parse, so it runs before this script's. jsdom does not put the
    // form's named controls in an inline handler's scope, so it is modelled here as the same thing.
    const form = dom.window.document.getElementById("kc-form-login");
    form.addEventListener("submit", () => { form.elements.namedItem("login").disabled = true; });
  }
  dom.window.eval(`window.OSPREY_RESET_BY_EMAIL = ${resetByEmail};\n` + SCRIPT);
  dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
  return dom.window;
}

function submit(window, values) {
  const doc = window.document;
  for (const [id, value] of Object.entries(values)) doc.getElementById(id).value = value;
  const form = doc.querySelector("form");
  const event = new window.Event("submit", { cancelable: true });
  form.dispatchEvent(event);
  return { sent: !event.defaultPrevented, error: (id) => {
    const field = doc.getElementById(id);
    const describedBy = field.getAttribute("aria-describedby");
    return field.getAttribute("aria-invalid") === "true" ? doc.getElementById(describedBy)?.textContent : null;
  } };
}

test("an empty form says what each field needs, and is not sent", () => {
  const result = submit(page(LOGIN.replace("__FORGOT__", FORGOT)), { username: "  ", password: "" });
  assert.equal(result.sent, false);
  assert.equal(result.error("username"), "Enter your email address or username.");
  assert.equal(result.error("password"), "Enter your password.");
});

test("an address that is not one, and a username with a space, are named as such", () => {
  const window = page(LOGIN.replace("__FORGOT__", FORGOT));
  assert.equal(submit(window, { username: "j.okafor@acme", password: "x" }).error("username"),
    "Enter an email address in the format name@organisation.gov.uk, or use your username.");
  assert.equal(submit(window, { username: "j okafor", password: "x" }).error("username"),
    "Usernames use letters, numbers, dots, hyphens and underscores, with no spaces.");
});

test("a well-formed address or username and a password are sent, and earlier errors cleared", () => {
  const window = page(LOGIN.replace("__FORGOT__", FORGOT));
  submit(window, { username: "", password: "" });
  for (const username of ["j.okafor", "name@organisation.gov.uk"]) {
    const result = submit(window, { username, password: "correct-horse-1" });
    assert.equal(result.sent, true);
    assert.equal(result.error("username"), null);
    assert.equal(window.document.querySelectorAll(".osprey-field-error").length, 0);
  }
});

test("nothing is said while typing, only on submit", () => {
  const window = page(LOGIN.replace("__FORGOT__", FORGOT));
  const field = window.document.getElementById("username");
  field.value = "j okafor";
  field.dispatchEvent(new window.Event("input"));
  assert.equal(field.getAttribute("aria-invalid"), null);
});

test("with no mail server, the way back is the administrator, said where the link would be", () => {
  const help = (w) => w.document.querySelector(".osprey-no-reset")?.textContent ?? null;
  assert.equal(help(page(LOGIN.replace("__FORGOT__", ""), { resetByEmail: false })),
    "Forgot your password? Ask your OspreyFlow administrator to reset your sign-in. They'll give you a one-time code.");
  assert.equal(help(page(LOGIN.replace("__FORGOT__", FORGOT))), null);
});

test("the card ends with how accounts are made", () => {
  const w = page(LOGIN.replace("__FORGOT__", FORGOT));
  assert.equal(w.document.querySelector(".osprey-card-foot").textContent,
    "No account yet? Your OspreyFlow administrator invites people and assigns roles.");
});

test("the reset page checks the address or username, and its button says what it sends", () => {
  const window = page(RESET);
  assert.equal(window.document.querySelector("#kc-reset-password-form [type=submit]").textContent, "Send reset link");
  const result = submit(window, { username: "" });
  assert.equal(result.sent, false);
  assert.equal(result.error("username"), "Enter your email address or username.");
  assert.equal(submit(window, { username: "j.okafor" }).sent, true);
});

test("after a reset is sent, the card says to check your email, with a way back to sign in", () => {
  const sent = `<div class="pf-v5-c-alert pf-m-success"><span class="kc-feedback-text">If an OspreyFlow account matches what you entered, a reset link is on its way.</span></div>`;
  const window = page(sent + LOGIN.replace("__FORGOT__", FORGOT));
  const doc = window.document;
  assert.equal(doc.getElementById("kc-page-title").textContent, "Check your email");
  assert.equal(doc.getElementById("kc-form-login").hidden, true);
  const back = [...doc.querySelectorAll("button")].find((b) => b.textContent === "Back to sign in");
  back.click();
  assert.equal(doc.getElementById("kc-form-login").hidden, false);
  assert.equal(doc.getElementById("kc-page-title").textContent, "Sign in");
});

test("a refused submit gives Keycloak's button back, so the corrected form can be sent", () => {
  const window = page(LOGIN.replace("__FORGOT__", FORGOT), { keycloakDisables: true });
  submit(window, { username: "", password: "" });
  assert.equal(window.document.getElementById("kc-login").disabled, false);
});

test("a field's error sits directly under the field, before any help beneath it", () => {
  const window = page(LOGIN.replace("__FORGOT__", ""), { resetByEmail: false });
  submit(window, { username: "j.okafor", password: "" });
  const group = window.document.getElementById("password").closest(".pf-v5-c-form__group");
  const after = [...group.children].map((c) => c.className);
  assert.ok(after.indexOf("osprey-field-error") < after.indexOf("osprey-no-reset"), after.join(" "));
});

test("the reset page's instruction leads the card, under its title, as the handoff has it", () => {
  const doc = page(RESET).document;
  const form = doc.getElementById("kc-reset-password-form");
  const info = doc.getElementById("kc-info");
  assert.equal(info.nextElementSibling, form);
  assert.ok(info.classList.contains("osprey-lead"));
});
