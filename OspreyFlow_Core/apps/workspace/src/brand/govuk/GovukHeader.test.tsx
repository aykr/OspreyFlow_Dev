// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand } from "../brand";
import { GovukHeader } from "./GovukHeader";

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

describe("GovukHeader", () => {
  it("renders nothing under the OspreyFlow brand", () => {
    const { container } = render(<GovukHeader serviceName="Case Finder" />);
    expect(container.firstChild).toBeNull();
  });

  it("links the GOV.UK logo to gov.uk and the service name to the home page", () => {
    applyBrand("govuk");
    render(<GovukHeader serviceName="Case Finder" />);
    expect(screen.getByRole("link", { name: /GOV\.UK/ }).getAttribute("href")).toBe("https://www.gov.uk/");
    expect(screen.getByRole("link", { name: "Case Finder" }).getAttribute("href")).toBe("/");
    expect(screen.getByRole("region", { name: "Service information" })).toBeTruthy();
  });

  it("omits the service navigation without a service name", () => {
    applyBrand("govuk");
    render(<GovukHeader serviceName={null} />);
    expect(screen.queryByRole("region", { name: "Service information" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Service information" })).toBeNull();
    expect(screen.getByRole("link", { name: /GOV\.UK/ })).toBeTruthy();
  });
});
