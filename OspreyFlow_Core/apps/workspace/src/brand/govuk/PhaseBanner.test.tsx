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
});
