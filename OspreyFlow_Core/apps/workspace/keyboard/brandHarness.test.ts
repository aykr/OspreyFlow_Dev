// @vitest-environment jsdom
//
// ADR-152 Amendment 2 item 3, as the Playwright harnesses meet it. The GOV.UK-look specs were tuned to GDS
// Transport's measurements; the face is drawn only with the identity on AND on a gov.uk address, and a Playwright
// server answers on localhost. So the harness helper must hand `applyBrand` a gov.uk address itself: turning the
// identity on without one draws Arial and every such spec measures the wrong face (round 4 of PL7c, case A).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { currentGovukIdentity, currentGovukTypeface } from "@ospreyflow/glass-shared";

import { applyHarnessBrand } from "./brandHarness";

const root = () => document.documentElement;

function openAt(search: string): void {
  window.history.replaceState(null, "", `/harness.html${search}`);
}

beforeEach(() => {
  // jsdom loads no stylesheet, so a link's `load` never fires; answer it as a browser would.
  vi.spyOn(document.head, "append").mockImplementation((...nodes) => {
    for (const node of nodes) if (node instanceof HTMLLinkElement) node.onload?.(new Event("load"));
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  for (const name of ["data-brand", "data-govuk-identity", "data-govuk-typeface"]) root().removeAttribute(name);
  openAt("");
});

describe("the harness brand helper", () => {
  it("is served on localhost, as a Playwright server is, so the address alone would never draw the face", () => {
    expect(window.location.hostname).toBe("localhost");
  });

  it("draws the GOV.UK identity AND its typeface under ?brand=govuk, whatever address the server answers on", async () => {
    openAt("?brand=govuk");
    expect(await applyHarnessBrand()).toBe("govuk");
    expect(currentGovukIdentity()).toBe(true);
    expect(root().getAttribute("data-govuk-typeface")).toBe("on");
    expect(currentGovukTypeface()).toBe(true);
  });

  it("draws neither under ?govuk_identity=off, nor under the OspreyFlow brand", async () => {
    openAt("?brand=govuk&govuk_identity=off");
    await applyHarnessBrand();
    expect(currentGovukIdentity()).toBe(false);
    expect(root().hasAttribute("data-govuk-typeface")).toBe(false);
    openAt("");
    expect(await applyHarnessBrand()).toBe("ospreyflow");
    expect(root().hasAttribute("data-govuk-identity")).toBe(false);
    expect(root().hasAttribute("data-govuk-typeface")).toBe(false);
  });
});
