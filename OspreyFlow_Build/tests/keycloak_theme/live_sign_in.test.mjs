// ADR-115 E2, the live proof (`CLAUDE.md` rule 15): the OspreyFlow login theme mounted in a real
// Keycloak, driven in a real browser — the jsdom tests beside this one prove the script against the
// markup as measured; this proves Keycloak renders that markup, loads both scripts and says the
// theme's words, and that the realm's rules behave as the page says.
//
// Skipped unless pointed at throwaway Keycloaks (never the deployment's), each with realm `osprey`,
// the `osprey` login theme, the realm's `sign_in_rules`, a public client `probe` and a user
// `j.okafor` / `correct-horse-1` with address `j.okafor@example.test`:
//   OSPREY_TEST_SIGNIN_NOMAIL_URL  — rendered with reset_by_email=false, no mail server
//   OSPREY_TEST_SIGNIN_MAIL_URL    — rendered with reset_by_email=true, mail to a catcher
//   OSPREY_TEST_SIGNIN_MAILPIT_URL — that catcher's web address (Mailpit, test only)
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(new URL("../../../OspreyFlow_Core/package.json", import.meta.url));
const NOMAIL = process.env.OSPREY_TEST_SIGNIN_NOMAIL_URL;
const MAIL = process.env.OSPREY_TEST_SIGNIN_MAIL_URL;
const MAILPIT = process.env.OSPREY_TEST_SIGNIN_MAILPIT_URL;
const skip = !(NOMAIL && MAIL && MAILPIT) && "needs throwaway Keycloaks (see the file's header)";

const auth = (base) =>
  `${base}/realms/osprey/protocol/openid-connect/auth?client_id=probe&response_type=code&scope=openid&redirect_uri=${encodeURIComponent(base + "/done")}`;

async function browser() {
  const { chromium } = require("playwright");
  return chromium.launch();
}

const errorOf = (page, id) =>
  page.evaluate((field) => {
    const el = document.getElementById(field);
    return el.getAttribute("aria-invalid") === "true"
      ? document.getElementById(el.getAttribute("aria-describedby"))?.textContent
      : null;
  }, id);

test("without a mail server: the card's words, no reset link, the administrator named, validation before any request", { skip }, async () => {
  const b = await browser();
  try {
    const page = await b.newPage();
    await page.goto(auth(NOMAIL));
    assert.equal((await page.textContent("#kc-page-title")).trim(), "Sign in");
    assert.equal((await page.textContent("label[for=username]")).trim(), "Email or username");
    assert.equal(await page.evaluate(() => window.OSPREY_RESET_BY_EMAIL), false);
    assert.equal(await page.locator("a", { hasText: /forgot/i }).count(), 0);
    assert.equal((await page.textContent(".osprey-no-reset")).trim(),
      "Forgot your password? Ask your OspreyFlow administrator to reset your sign-in. They'll give you a one-time code.");
    assert.equal((await page.textContent(".osprey-card-foot")).trim(),
      "No account yet? Your OspreyFlow administrator invites people and assigns roles.");

    const before = page.url();
    let posted = false;
    page.on("request", (r) => { if (r.method() === "POST") posted = true; });
    await page.click("#kc-login");
    assert.equal(await errorOf(page, "username"), "Enter your email address or username.");
    assert.equal(await errorOf(page, "password"), "Enter your password.");
    await page.fill("#username", "j.okafor@acme");
    await page.fill("#password", "x");
    await page.click("#kc-login");
    assert.equal(await errorOf(page, "username"), "Enter an email address in the format name@organisation.gov.uk, or use your username.");
    assert.equal(posted, false, "an invalid form never reaches Keycloak");
    assert.equal(page.url(), before);

    await page.fill("#username", "j.okafor");
    await page.fill("#password", "wrong-1");
    await page.click("#kc-login");
    await page.waitForLoadState();
    const said = (await page.locator("#input-error, .pf-v5-c-helper-text__item-text, .pf-v5-c-alert").allTextContents()).join(" ");
    assert.match(said, /That email or username and password do not match an OspreyFlow account\. Check for typos, or ask your OspreyFlow administrator to reset your sign-in\. Five failed attempts lock the account for 15 minutes\./);
  } finally {
    await b.close();
  }
});

test("with a mail server: reset your password, then check your email, and the mail is sent", { skip }, async () => {
  const b = await browser();
  try {
    await fetch(`${MAILPIT}/api/v1/messages`, { method: "DELETE" });
    const page = await b.newPage();
    await page.goto(auth(MAIL));
    assert.equal(await page.evaluate(() => window.OSPREY_RESET_BY_EMAIL), true);
    assert.equal(await page.locator(".osprey-no-reset").count(), 0);
    await page.click("text=Forgot password?");
    await page.waitForLoadState();
    assert.equal((await page.textContent("#kc-page-title")).trim(), "Reset your password");
    assert.match(await page.textContent("body"), /For OspreyFlow accounts only\. If you sign in through your organisation, reset your password there instead\./);
    assert.equal((await page.textContent("#kc-reset-password-form [type=submit]")).trim(), "Send reset link");
    assert.ok(await page.locator("a", { hasText: "Back to sign in" }).count());
    // A quiet text button in the tokens' secondary text, not PatternFly's own blue outline.
    const back = await page.evaluate(() => {
      const a = [...document.querySelectorAll("a")].find((x) => x.textContent.trim() === "Back to sign in");
      const probe = document.createElement("span");
      probe.style.color = "var(--text-secondary)";
      document.body.appendChild(probe);
      const want = getComputedStyle(probe).color;
      return { colour: getComputedStyle(a).color, want, top: getComputedStyle(a).borderTopWidth };
    });
    assert.equal(back.colour, back.want);
    assert.equal(back.top, "0px");
    const lead = await page.evaluate(() => document.getElementById("kc-info").nextElementSibling?.id);
    assert.equal(lead, "kc-reset-password-form");
    await page.click("#kc-reset-password-form [type=submit]");
    assert.equal(await errorOf(page, "username"), "Enter your email address or username.");

    await page.fill("#username", "j.okafor");
    await page.click("#kc-reset-password-form [type=submit]");
    await page.waitForLoadState();
    assert.equal((await page.textContent("#kc-page-title")).trim(), "Check your email");
    assert.match(await page.textContent("body"), /It expires in 30 minutes\./);
    assert.equal(await page.isHidden("#kc-form-login"), true);
    let mails = { messages: [] };
    for (let i = 0; i < 20 && mails.messages.length === 0; i++) {
      mails = await (await fetch(`${MAILPIT}/api/v1/messages`)).json();
      if (!mails.messages.length) await new Promise((r) => setTimeout(r, 250));
    }
    assert.equal(mails.messages[0]?.To?.[0]?.Address, "j.okafor@example.test");
    await page.click("text=Back to sign in");
    assert.equal(await page.isVisible("#kc-form-login"), true);
    assert.equal((await page.textContent("#kc-page-title")).trim(), "Sign in");
  } finally {
    await b.close();
  }
});
