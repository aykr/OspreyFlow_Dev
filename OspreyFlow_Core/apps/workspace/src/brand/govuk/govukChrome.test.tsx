// @vitest-environment jsdom
//
// ADR-132 Amendment 2: the identity provider's sign-in page carries the same GOV.UK header and footer
// as the Glass. `harness/govuk_chrome.js` (plain script, no React) holds them as static markup; this
// fails if that markup drifts from what these components render.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand } from "@ospreyflow/glass-shared";
import { GovukFooter } from "./GovukFooter";
import { GovukHeader } from "./GovukHeader";

const SCRIPT = readFileSync(join(__dirname, "../../../../../harness/govuk_chrome.js"), "utf-8");

function constant(name: string): string {
  const match = new RegExp(`var ${name} = (".*");`).exec(SCRIPT);
  if (!match) throw new Error(`no ${name} in harness/govuk_chrome.js`);
  return JSON.parse(match[1]!) as string;
}

afterEach(() => applyBrand("ospreyflow"));

describe("the sign-in page's GOV.UK header and footer", () => {
  it("are the Glass's own components", () => {
    applyBrand("govuk", true);
    // The full markup, as on gov.uk: off gov.uk the script itself takes the crown out (ADR-132 Amendment 8).
    expect(constant("HEADER")).toBe(renderToStaticMarkup(<GovukHeader hostname="prison-intelligence.service.gov.uk" identity />));
    expect(constant("FOOTER")).toBe(renderToStaticMarkup(<GovukFooter organisation={null} />));
  });

  // ADR-132 Amendment 8: off gov.uk both crop the logo to the word mark the same way.
  it("crop the header's logo off gov.uk as the Glass's component does", () => {
    applyBrand("govuk", true);
    const off = renderToStaticMarkup(<GovukHeader hostname="govuk.ospreyflow.app" identity />);
    const viewBox = /viewBox="([^"]+)"/.exec(off)![1]!;
    const width = /width="([^"]+)"/.exec(off)![1]!;
    expect(SCRIPT).toContain(`logotype.setAttribute("viewBox", "${viewBox}")`);
    expect(SCRIPT).toContain(`logotype.setAttribute("width", "${width}")`);
  });
});

// ADR-152 decision 14, invariant I9: the script is the sign-in page's whole GOV.UK frame, so it is run, as the browser runs
// it, against a page with the settings the harness writes, and what it draws is read back.
describe("the sign-in page's chrome, run", () => {
  const settings = { serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase: "none", glassOrigin: "" };

  // The script reads exactly two things of `window`: the settings and the page's hostname. jsdom's own address cannot be
  // moved from a test, so the script is given a `window` holding the two, as a browser at that address would.
  function run(given: Record<string, unknown>, hostname = "localhost"): HTMLElement {
    document.body.innerHTML = '<main id="kc-form-login"></main>';
    document.documentElement.setAttribute("data-brand", "govuk");
    const page = { OSPREY_GOVUK: { ...settings, ...given }, location: { hostname } };
    new Function("window", SCRIPT)(page);
    return document.body;
  }

  // The harness writes the switch into every GOV.UK sign-in theme as a boolean, so "off" is the key written as false. A
  // settings object with no key (from before the switch existed) is also off: the switch is the only thing that turns the
  // identity on (the owner's ruling of 23 November 2026).
  const off = { govukIdentity: false };

  it("with the switch off (the default, written as false) draws the organisation's name, no logotype, no crown", () => {
    const body = run(off);
    expect(body.querySelector(".govuk-header__logotype")).toBeNull();
    expect(body.querySelector(".govuk-header svg")).toBeNull();
    expect(body.querySelector(".govuk-header__organisation-name")?.textContent).toBe("Ministry of Examples");
    // ADR-152 decision 14: the department's name with the service name, as `GovukHeader.tsx` draws them.
    expect(body.querySelector(".govuk-header__service-name")?.textContent).toBe("Prison Intelligence");
    expect(body.querySelector(".govuk-footer__crown")).toBeNull();
    expect(body.textContent).not.toMatch(/Crown copyright|Open Government Licence/);
  });

  it("with the switch off falls back to the service's name, then to OspreyFlow", () => {
    const serviceOnly = run({ ...off, organisation: null });
    expect(serviceOnly.querySelector(".govuk-header__organisation-name")?.textContent).toBe("Prison Intelligence");
    expect(serviceOnly.querySelector(".govuk-header__service-name")).toBeNull(); // one name is drawn once
    const bare = run({ ...off, organisation: null, serviceName: null });
    expect(bare.querySelector(".govuk-header__organisation-name")?.textContent).toBe("OspreyFlow");
    expect(bare.querySelector(".govuk-header__service-name")).toBeNull();
    // The same name for both is one name, not two.
    expect(run({ ...off, organisation: "Prison Intelligence" }).querySelector(".govuk-header__service-name")).toBeNull();
  });

  it.each(["localhost", "prison-intelligence.service.gov.uk"])("with no switch key at all (%s) is off: no logotype, no crown, the name in its place", (host) => {
    const body = run({}, host);
    expect(body.querySelector(".govuk-header__logotype")).toBeNull();
    expect(body.querySelector(".govuk-footer__crown")).toBeNull();
    expect(body.textContent).not.toMatch(/Crown copyright|Open Government Licence/);
    expect(body.querySelector(".govuk-header__organisation-name")?.textContent).toBe("Ministry of Examples");
  });

  it("with only a quoted or truthy non-true value is still off", () => {
    for (const given of ["true", 1, "yes"]) expect(run({ govukIdentity: given }).querySelector(".govuk-header__logotype")).toBeNull();
  });

  it("with the switch on draws the word mark (no crown off gov.uk), as before", () => {
    const body = run({ govukIdentity: true });
    const logo = body.querySelector(".govuk-header__logotype");
    expect(logo).not.toBeNull();
    expect(logo!.querySelector("g")).toBeNull();
    expect(body.querySelector(".govuk-header__organisation-name")).toBeNull();
  });

  // Invariant I9, on the address the first rounds never ran it at: the footer's crown, Crown copyright and Open Government
  // Licence line follow the switch AND a gov.uk address, so the switch off on a gov.uk address draws none of them.
  const crownly = /Crown copyright|Open Government Licence/;

  it.each(["prison-intelligence.service.gov.uk", "gov.uk"])(
    "with the switch off on %s still draws no crown, no Crown copyright, no licence line and no logotype",
    (host) => {
      const body = run(off, host);
      expect(body.querySelector(".govuk-footer__crown")).toBeNull();
      expect(body.querySelector(".govuk-footer__licence-logo")).toBeNull();
      expect(body.textContent).not.toMatch(crownly);
      expect(body.querySelector(".govuk-header__logotype")).toBeNull();
      expect(body.querySelector(".govuk-header svg")).toBeNull();
      expect(body.querySelector(".govuk-header__organisation-name")?.textContent).toBe("Ministry of Examples");
    },
  );

  it("with the switch on, on a gov.uk address, draws the crown, Crown copyright and the licence line (so the cases above cannot pass by drawing nothing)", () => {
    const body = run({ govukIdentity: true }, "prison-intelligence.service.gov.uk");
    expect(body.querySelector(".govuk-header__logotype g")).not.toBeNull();
    expect(body.querySelector(".govuk-footer__crown, .govuk-footer__licence-logo")).not.toBeNull();
    expect(body.textContent).toMatch(/Crown copyright/);
    expect(body.textContent).toMatch(/Open Government Licence/);
  });

  it.each(["localhost", "govuk.ospreyflow.app", "notgov.uk", "gov.uk.example.org"])(
    "with the switch on, off gov.uk (%s), draws no crown and no Crown copyright",
    (host) => {
      const body = run({ govukIdentity: true }, host);
      expect(body.querySelector(".govuk-header__logotype")).not.toBeNull(); // the word mark stays (Amendment 8)
      expect(body.querySelector(".govuk-header__logotype g")).toBeNull();
      expect(body.querySelector(".govuk-footer__crown")).toBeNull();
      expect(body.textContent).not.toMatch(crownly);
    },
  );
});
