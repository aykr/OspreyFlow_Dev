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

  function run(given: Record<string, unknown>): HTMLElement {
    document.body.innerHTML = '<main id="kc-form-login"></main>';
    document.documentElement.setAttribute("data-brand", "govuk");
    (window as unknown as { OSPREY_GOVUK: unknown }).OSPREY_GOVUK = { ...settings, ...given };
    new Function(SCRIPT)();
    return document.body;
  }

  it("with the switch off (the default, and the key absent) draws the organisation's name, no logotype, no crown", () => {
    const body = run({});
    expect(body.querySelector(".govuk-header__logotype")).toBeNull();
    expect(body.querySelector(".govuk-header svg")).toBeNull();
    expect(body.querySelector(".govuk-header__organisation-name")?.textContent).toBe("Ministry of Examples");
    // ADR-152 decision 14: the department's name with the service name, as `GovukHeader.tsx` draws them.
    expect(body.querySelector(".govuk-header__service-name")?.textContent).toBe("Prison Intelligence");
    expect(body.querySelector(".govuk-footer__crown")).toBeNull();
    expect(body.textContent).not.toMatch(/Crown copyright|Open Government Licence/);
  });

  it("with the switch off falls back to the service's name, then to OspreyFlow", () => {
    const serviceOnly = run({ organisation: null });
    expect(serviceOnly.querySelector(".govuk-header__organisation-name")?.textContent).toBe("Prison Intelligence");
    expect(serviceOnly.querySelector(".govuk-header__service-name")).toBeNull(); // one name is drawn once
    const bare = run({ organisation: null, serviceName: null });
    expect(bare.querySelector(".govuk-header__organisation-name")?.textContent).toBe("OspreyFlow");
    expect(bare.querySelector(".govuk-header__service-name")).toBeNull();
    // The same name for both is one name, not two.
    expect(run({ organisation: "Prison Intelligence" }).querySelector(".govuk-header__service-name")).toBeNull();
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
});
