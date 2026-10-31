// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand } from "../brand";
import { GovukFooter } from "./GovukFooter";

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

describe("GovukFooter", () => {
  it("renders nothing under the OspreyFlow brand", () => {
    const { container } = render(<GovukFooter organisation="Ministry of Examples" />);
    expect(container.firstChild).toBeNull();
  });

  it("offers the support links and the Crown copyright link", () => {
    applyBrand("govuk");
    render(<GovukFooter organisation={null} />);
    expect(screen.getByRole("link", { name: "Accessibility statement" }).getAttribute("href")).toBe("/accessibility-statement.html");
    expect(screen.getByRole("link", { name: "Cookies" }).getAttribute("href")).toBe("/cookies.html");
    expect(screen.getByRole("link", { name: /Crown copyright/ })).toBeTruthy();
  });

  it("names the organisation when given and not otherwise", () => {
    applyBrand("govuk");
    render(<GovukFooter organisation="Ministry of Examples" />);
    expect(screen.getByText("Run by Ministry of Examples")).toBeTruthy();
    cleanup();
    render(<GovukFooter organisation={null} />);
    expect(screen.queryByText(/Run by/)).toBeNull();
  });
});
