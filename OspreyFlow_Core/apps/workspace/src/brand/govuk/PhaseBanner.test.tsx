// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand, type Brand } from "../brand";
import { PhaseBanner } from "./PhaseBanner";

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

const BRANDS: Brand[] = ["ospreyflow", "govuk"];

describe.each(BRANDS)("PhaseBanner under %s", (brand) => {
  it.each(["none", "live"] as const)("renders nothing for %s", (phase) => {
    applyBrand(brand);
    const { container } = render(<PhaseBanner phase={phase} />);
    expect(container.firstChild).toBeNull();
  });

  it("says Beta in a Service phase region", () => {
    applyBrand(brand);
    render(<PhaseBanner phase="beta" />);
    const region = screen.getByRole("region", { name: "Service phase" });
    expect(within(region).getByText("Beta")).toBeTruthy();
    expect(within(region).getByText("This is a new service.")).toBeTruthy();
  });

  it("says Alpha for the alpha phase", () => {
    applyBrand(brand);
    render(<PhaseBanner phase="alpha" />);
    const region = screen.getByRole("region", { name: "Service phase" });
    expect(within(region).getByText("Alpha")).toBeTruthy();
  });

  // ADR-132 Amendment 7: the deployment's own banner text, in place of "This is a new service.".
  const DISCLAIMER = "Demonstration only: this is not a government service, and all data is synthetic.";

  it("says the deployment's own words after the phase's tag", () => {
    applyBrand(brand);
    render(<PhaseBanner phase="beta" text={DISCLAIMER} />);
    const region = screen.getByRole("region", { name: "Service phase" });
    expect(within(region).getByText("Beta")).toBeTruthy();
    expect(within(region).getByText(DISCLAIMER)).toBeTruthy();
    expect(within(region).queryByText("This is a new service.")).toBeNull();
  });

  it.each(["none", "live"] as const)("says the deployment's own words alone at %s, with no tag", (phase) => {
    applyBrand(brand);
    render(<PhaseBanner phase={phase} text={DISCLAIMER} />);
    const region = screen.getByRole("region", { name: "Service phase" });
    expect(region.textContent?.trim()).toBe(DISCLAIMER);
  });

  it("treats blank words as none", () => {
    applyBrand(brand);
    const { container } = render(<PhaseBanner phase="none" text="   " />);
    expect(container.firstChild).toBeNull();
  });
});
