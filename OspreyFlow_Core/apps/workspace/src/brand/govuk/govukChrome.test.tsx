// @vitest-environment jsdom
//
// ADR-132 Amendment 2: the identity provider's sign-in page carries the same GOV.UK header and footer
// as the Glass. `harness/govuk_chrome.js` (plain script, no React) holds them as static markup; this
// fails if that markup drifts from what these components render.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand } from "../brand";
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
    applyBrand("govuk");
    // The full markup, as on gov.uk: off gov.uk the script itself takes the crown out (ADR-132 Amendment 8).
    expect(constant("HEADER")).toBe(renderToStaticMarkup(<GovukHeader hostname="prison-intelligence.service.gov.uk" />));
    expect(constant("FOOTER")).toBe(renderToStaticMarkup(<GovukFooter organisation={null} />));
  });

  // ADR-132 Amendment 8: off gov.uk both crop the logo to the word mark the same way.
  it("crop the header's logo off gov.uk as the Glass's component does", () => {
    applyBrand("govuk");
    const off = renderToStaticMarkup(<GovukHeader hostname="govuk.ospreyflow.app" />);
    const viewBox = /viewBox="([^"]+)"/.exec(off)![1]!;
    const width = /width="([^"]+)"/.exec(off)![1]!;
    expect(SCRIPT).toContain(`logotype.setAttribute("viewBox", "${viewBox}")`);
    expect(SCRIPT).toContain(`logotype.setAttribute("width", "${width}")`);
  });
});
