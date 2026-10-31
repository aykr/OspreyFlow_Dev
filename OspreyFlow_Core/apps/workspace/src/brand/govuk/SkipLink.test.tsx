// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { applyBrand, type Brand } from "../brand";
import { SkipLink } from "./SkipLink";

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

describe.each(["ospreyflow", "govuk"] as Brand[])("SkipLink under %s", (brand) => {
  it("is a link to the main content and moves focus there when activated", () => {
    applyBrand(brand);
    render(
      <>
        <SkipLink />
        <div id="main-content" tabIndex={-1}>
          Main
        </div>
      </>,
    );
    const link = screen.getByRole("link", { name: "Skip to main content" });
    expect(link.getAttribute("href")).toBe("#main-content");
    fireEvent.click(link);
    expect(document.activeElement).toBe(document.getElementById("main-content"));
  });
});
