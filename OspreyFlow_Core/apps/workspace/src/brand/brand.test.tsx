// @vitest-environment jsdom
//
// ADR-132: the deployment's brand is separate from the viewer's theme. Under `govuk` the page is light
// whatever is asked and neither theme button is drawn; under `ospreyflow` the theme behaves as before.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { SignInScreen } from "../auth/SignInScreen";
import { TopBar } from "../shell/TopBar";
import { applyTheme, currentTheme } from "../theme/theme";
import {
  applyBrand,
  brandFromUrl,
  brandTitle,
  currentBrand,
  GOVUK_STYLESHEET,
  loadBrandStylesheet,
  PLAIN_APPEARANCE,
  isGovUkHost,
  readAppearance,
} from "./brand";

const themeButton = { name: /Switch to the|theme$/ };

function topBar() {
  return <TopBar app="glass" caseSwitcher={null} account={null} />;
}

beforeEach(() => {
  localStorage.clear();
  applyBrand("ospreyflow");
  applyTheme("dark");
});
afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

describe("under the GOV.UK brand", () => {
  it("the page is light, and asking for dark leaves it light", () => {
    applyBrand("govuk");
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(currentTheme()).toBe("light");
  });

  it("the top bar draws no theme button", () => {
    applyBrand("govuk");
    applyTheme("dark");
    render(topBar());
    expect(screen.queryByRole("button", themeButton)).toBeNull();
  });

  it("the sign-in page draws no theme button", () => {
    applyBrand("govuk");
    render(<SignInScreen onSignIn={() => undefined} />);
    expect(screen.queryByRole("button", themeButton)).toBeNull();
  });

  it("the sign-in page draws no OspreyFlow wordmark under the GOV.UK header", () => {
    applyBrand("govuk");
    render(<SignInScreen onSignIn={() => undefined} />);
    expect(document.querySelector(".welcome-header__wordmark")).toBeNull();
  });

  it("the page title is the GOV.UK form", () => {
    const appearance = { ...PLAIN_APPEARANCE, brand: "govuk" as const, serviceName: "Prison Intelligence" };
    expect(brandTitle(appearance, "govuk", "OspreyFlow — The Glass")).toBe("Prison Intelligence – GOV.UK");
  });
});

describe("under the OspreyFlow brand", () => {
  it("the theme is the viewer's choice, as before", () => {
    applyTheme("light");
    expect(currentTheme()).toBe("light");
    applyTheme("dark");
    expect(currentTheme()).toBe("dark");
  });

  it("the top bar and the sign-in page keep their theme buttons", () => {
    render(topBar());
    expect(screen.getByRole("button", { name: "Switch to the light theme" })).toBeTruthy();
    cleanup();
    render(<SignInScreen onSignIn={() => undefined} />);
    expect(screen.getByRole("button", { name: "Light theme" })).toBeTruthy();
  });

  it("the page title is unchanged", () => {
    expect(brandTitle(PLAIN_APPEARANCE, "ospreyflow", "OspreyFlow — The Glass")).toBe("OspreyFlow — The Glass");
  });
});

describe("reading the deployment's appearance", () => {
  it("takes what the deployment names", () => {
    expect(
      readAppearance({ brand: "govuk", service_name: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" }),
    ).toEqual({ brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" });
  });

  it("takes the deployment's banner text when it names one, and adds nothing when it does not (ADR-132 Amendment 7)", () => {
    expect(readAppearance({ brand: "govuk", phase: "none", banner_text: "Demonstration only." })).toEqual({
      ...PLAIN_APPEARANCE,
      brand: "govuk",
      bannerText: "Demonstration only.",
    });
    expect(readAppearance({ brand: "govuk", phase: "none", banner_text: "  " })).not.toHaveProperty("bannerText");
    expect(readAppearance({ brand: "govuk", phase: "none" })).not.toHaveProperty("bannerText");
  });

  it("falls back to the OspreyFlow brand for anything it does not recognise", () => {
    expect(readAppearance(undefined)).toEqual(PLAIN_APPEARANCE);
    expect(readAppearance({ brand: "gov.uk", phase: "gamma", service_name: "  " })).toEqual(PLAIN_APPEARANCE);
  });
});

describe("?brand= in the address", () => {
  it("chooses a brand in a development build", () => {
    expect(brandFromUrl("?brand=govuk", true)).toBe("govuk");
    expect(brandFromUrl("?brand=ospreyflow", true)).toBe("ospreyflow");
    expect(brandFromUrl("?brand=other", true)).toBeNull();
  });

  it("is ignored in a production build", () => {
    expect(brandFromUrl("?brand=govuk", false)).toBeNull();
  });
});

describe("the brand on the page", () => {
  it("is the OspreyFlow brand unless set", () => {
    document.documentElement.removeAttribute("data-brand");
    expect(currentBrand()).toBe("ospreyflow");
  });
});

describe("the GOV.UK stylesheet", () => {
  const govukLinks = () => document.head.querySelectorAll(`link[href="${GOVUK_STYLESHEET}"]`);
  afterEach(() => govukLinks().forEach((link) => link.remove()));

  it("is never fetched under the OspreyFlow brand", async () => {
    await loadBrandStylesheet("ospreyflow");
    expect(govukLinks()).toHaveLength(0);
  });

  it("is added under the GOV.UK brand, and the page waits for it", async () => {
    let settled = false;
    const loading = loadBrandStylesheet("govuk").then(() => {
      settled = true;
    });
    const [link] = govukLinks();
    expect(link?.getAttribute("rel")).toBe("stylesheet");
    await Promise.resolve();
    expect(settled).toBe(false);
    link!.dispatchEvent(new Event("load"));
    await loading;
    expect(settled).toBe(true);
  });
});

describe("an address on gov.uk (ADR-132 Amendment 7)", () => {
  it.each([
    ["gov.uk", true],
    ["www.gov.uk", true],
    ["prison-intelligence.service.gov.uk", true],
    ["id.prison-intelligence.service.gov.uk", true],
    ["GOV.UK", true],
    ["notgov.uk", false],
    ["gov.uk.example.org", false],
    ["demo.ospreyflow.app", false],
    ["localhost", false],
  ])("%s is on gov.uk: %s", (host, expected) => {
    expect(isGovUkHost(host)).toBe(expected);
  });
});
