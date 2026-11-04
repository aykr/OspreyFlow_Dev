// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";

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
    const { container } = render(<GovukHeader />);
    expect(container.firstChild).toBeNull();
  });

  it("links the GOV.UK logo to gov.uk", () => {
    applyBrand("govuk");
    render(<GovukHeader />);
    expect(screen.getByRole("link", { name: /GOV\.UK/ }).getAttribute("href")).toBe("https://www.gov.uk/");
  });

  // ADR-132 Amendment 5 (the owner's ruling of 4 November 2026): no service-name band under the
  // header. The header is the GOV.UK logo and nothing else; the name is in the page title.
  it("draws no service-name band and no link but the logo's", () => {
    applyBrand("govuk");
    const { container } = render(<GovukHeader />);
    expect(container.querySelector(".govuk-service-navigation")).toBeNull();
    expect(screen.queryByRole("region", { name: "Service information" })).toBeNull();
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("leaves no style for the band in tokens.css", () => {
    const tokens = readFileSync(join(__dirname, "../../design/tokens.css"), "utf-8");
    expect(tokens).not.toContain("govuk-service-navigation");
  });
});
