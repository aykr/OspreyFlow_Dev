// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
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

  // ADR-132 Amendment 4 (the owner's choice, 1 November 2026): the product is credited in words in
  // the footer's meta, on every GOV.UK page; no mark, no link.
  it("credits OspreyFlow in words, with no mark and no link", () => {
    applyBrand("govuk");
    const { container } = render(<GovukFooter organisation="Ministry of Examples" />);
    const credit = screen.getByText("Built with OspreyFlow, open source.");
    expect(credit.tagName).toBe("P");
    expect(credit.closest("a")).toBeNull();
    expect(container.querySelectorAll("svg").length).toBe(2); // the crown and the licence logo only
  });
});

// ADR-132 Amendment 7 (the owner, 13 November 2026): a deployment whose address is not on gov.uk shows
// no crown, no Crown copyright and no Open Government Licence line; on gov.uk the footer is as it was.
describe("GovukFooter off gov.uk", () => {
  it("is the same markup as before on gov.uk", () => {
    applyBrand("govuk");
    const before = render(<GovukFooter organisation="Ministry of Examples" />).container.innerHTML;
    cleanup();
    expect(render(<GovukFooter organisation="Ministry of Examples" onGovUk />).container.innerHTML).toBe(before);
  });

  it("drops the crown, the Crown copyright and the licence, and keeps the rest", () => {
    applyBrand("govuk");
    const { container } = render(<GovukFooter organisation="Ministry of Examples" onGovUk={false} />);
    expect(container.querySelector(".govuk-footer__crown")).toBeNull();
    expect(container.querySelector(".govuk-footer__licence-logo")).toBeNull();
    expect(screen.queryByText(/Crown copyright/)).toBeNull();
    expect(screen.queryByText(/Open Government Licence/)).toBeNull();
    expect(container.querySelectorAll("svg").length).toBe(0);
    expect(screen.getByText("Run by Ministry of Examples")).toBeTruthy();
    expect(screen.getByText("Built with OspreyFlow, open source.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Accessibility statement" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Cookies" })).toBeTruthy();
  });

  it("is one line when slim, with the same words and links and nothing of the Crown", () => {
    applyBrand("govuk");
    const { container } = render(<GovukFooter organisation="Ministry of Examples" onGovUk={false} slim />);
    const lines = container.querySelectorAll("p");
    expect(lines.length).toBe(1);
    expect(lines[0]!.textContent).toContain("Run by Ministry of Examples");
    expect(lines[0]!.textContent).toContain("Built with OspreyFlow, open source.");
    expect(within(lines[0]!).getByRole("link", { name: "Accessibility statement" }).getAttribute("href")).toBe("/accessibility-statement.html");
    expect(within(lines[0]!).getByRole("link", { name: "Cookies" }).getAttribute("href")).toBe("/cookies.html");
    expect(container.querySelectorAll("svg").length).toBe(0);
    expect(screen.queryByText(/Crown copyright|Open Government Licence/)).toBeNull();
  });

  it("is never slim on gov.uk", () => {
    applyBrand("govuk");
    const full = render(<GovukFooter organisation={null} onGovUk />).container.innerHTML;
    cleanup();
    expect(render(<GovukFooter organisation={null} onGovUk slim />).container.innerHTML).toBe(full);
  });
});
