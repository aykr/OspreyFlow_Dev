// @vitest-environment jsdom
//
// ADR-132: the frame's order, top to bottom, under each brand, and that under the OspreyFlow brand
// with no phase it adds nothing to the page but the skip link.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand, PLAIN_APPEARANCE, type Appearance } from "./brand";
import { BrandFrame, MAIN_CONTENT_ID, useFullFooter } from "./BrandFrame";

const GOVUK: Appearance = { brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" };

function frame(appearance: Appearance) {
  return render(
    <BrandFrame appearance={appearance}>
      <button type="button">Inside the Glass</button>
    </BrandFrame>,
  );
}

/** The links and buttons in document order: the Tab order, since none sets a positive tabIndex. */
function tabStops(container: HTMLElement): string[] {
  return [...container.querySelectorAll<HTMLElement>("a[href], button")].map((el) => el.textContent?.trim() ?? "");
}

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

describe("under the OspreyFlow brand", () => {
  it("adds only the skip link, first, and wraps the Glass in its target", () => {
    applyBrand("ospreyflow");
    const { container } = frame(PLAIN_APPEARANCE);
    expect(tabStops(container)).toEqual(["Skip to main content", "Inside the Glass"]);
    expect(screen.queryByRole("region", { name: "Service phase" })).toBeNull();
    expect(document.getElementById(MAIN_CONTENT_ID)?.textContent).toBe("Inside the Glass");
    expect(document.documentElement.style.getPropertyValue("--workspace-height")).toBe("");
  });

  it("shows the phase banner when the deployment is in beta", () => {
    applyBrand("ospreyflow");
    frame({ ...PLAIN_APPEARANCE, phase: "beta" });
    expect(screen.getByRole("region", { name: "Service phase" }).textContent).toContain("Beta");
  });

  it("shows the deployment's banner text with no phase (ADR-132 Amendment 7)", () => {
    applyBrand("ospreyflow");
    frame({ ...PLAIN_APPEARANCE, bannerText: "Demonstration only: all data is synthetic." });
    expect(screen.getByRole("region", { name: "Service phase" }).textContent).toBe(
      "Demonstration only: all data is synthetic.",
    );
  });
});

describe("under the GOV.UK brand", () => {
  it("reads skip link, GOV.UK header, the Glass, then the footer", () => {
    applyBrand("govuk");
    const { container } = frame(GOVUK);
    const stops = tabStops(container);
    expect(stops[0]).toBe("Skip to main content");
    expect(stops[1]).toContain("GOV.UK");
    expect(stops[2]).toBe("Inside the Glass");
    expect(stops.indexOf("Accessibility statement")).toBeGreaterThan(stops.indexOf("Inside the Glass"));
    expect(stops.indexOf("Cookies")).toBeGreaterThan(stops.indexOf("Accessibility statement"));
    expect(screen.getByRole("region", { name: "Service phase" })).toBeTruthy();
  });

  // ADR-132 Amendment 5 (the owner's ruling of 4 November 2026): the service-name band under the
  // GOV.UK header is gone, to give the workspace its height back; the name stays in the page title.
  it("draws no service-name band, and names the service in the page title", () => {
    applyBrand("govuk");
    document.title = "OspreyFlow — The Glass";
    const { container } = frame(GOVUK);
    expect(container.querySelector(".govuk-service-navigation")).toBeNull();
    expect(screen.queryByRole("link", { name: "Prison Intelligence" })).toBeNull();
    expect(document.title).toBe("Prison Intelligence – GOV.UK");
  });
});

// ADR-132 Amendment 7 (the owner, 13 November 2026): off gov.uk, the footer on the workspace's screens
// is one line; Home and the sign-in page claim the full one (`useFullFooter`), still with nothing of
// the Crown. On gov.uk the footer is the full one everywhere, as before.
describe("the footer on and off gov.uk", () => {
  function Home() {
    useFullFooter();
    return <p>Home</p>;
  }

  it("is one line on the workspace's screens off gov.uk", () => {
    applyBrand("govuk");
    const { container } = render(
      <BrandFrame appearance={GOVUK} hostname="demo.ospreyflow.app">
        <button type="button">Inside the Glass</button>
      </BrandFrame>,
    );
    const footer = container.querySelector(".govuk-footer")!;
    expect(footer.querySelectorAll("p").length).toBe(1);
    expect(footer.textContent).not.toMatch(/Crown copyright|Open Government Licence/);
  });

  it("is full on a screen that claims it, still with nothing of the Crown off gov.uk", () => {
    applyBrand("govuk");
    const { container } = render(
      <BrandFrame appearance={GOVUK} hostname="demo.ospreyflow.app">
        <Home />
      </BrandFrame>,
    );
    const footer = container.querySelector(".govuk-footer")!;
    expect(footer.querySelectorAll("p").length).toBe(2);
    expect(footer.querySelector(".govuk-footer__crown")).toBeNull();
  });

  it("is the full footer, Crown and all, on gov.uk", () => {
    applyBrand("govuk");
    const { container } = render(
      <BrandFrame appearance={GOVUK} hostname="prison-intelligence.service.gov.uk">
        <button type="button">Inside the Glass</button>
      </BrandFrame>,
    );
    expect(container.querySelector(".govuk-footer__crown")).not.toBeNull();
    expect(screen.getByText(/Crown copyright/)).toBeTruthy();
  });
});

// ADR-132 Amendment 8 (the owner's ruling, 13 November 2026): the header and the banner are slim on the
// workspace's screens, by the slim footer's own rule; Home and the sign-in page keep the full frame. The
// sizes are measured in a browser (`keyboard/shell.spec.ts`); this holds the rule that chooses them.
describe("the compact top on the workspace's screens", () => {
  function Home() {
    useFullFooter();
    return <p>Home</p>;
  }
  const chrome = (container: HTMLElement) => container.querySelector(".govuk-header")!.parentElement!;

  it("is compact on a workspace screen", () => {
    applyBrand("govuk");
    const { container } = render(
      <BrandFrame appearance={GOVUK} hostname="demo.ospreyflow.app">
        <button type="button">Inside the Glass</button>
      </BrandFrame>,
    );
    expect(chrome(container).className).toContain("brand-chrome--compact");
  });

  it("is full while Home or the sign-in page is shown", () => {
    applyBrand("govuk");
    const { container } = render(
      <BrandFrame appearance={GOVUK} hostname="demo.ospreyflow.app">
        <Home />
      </BrandFrame>,
    );
    expect(chrome(container).className).not.toContain("brand-chrome--compact");
  });
});
