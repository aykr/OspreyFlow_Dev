// @vitest-environment jsdom
//
// The setup harness is its own page, on its own port, and it was dark whatever the analyst chose
// in the Glass (ADR-072). The rail now carries the same Light button, and `main.tsx` puts the saved
// choice on the page before anything is drawn.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { readStoredTheme, THEME_COOKIE_NAME } from "../../workspace/src/theme/theme";
import { SummaryRail } from "./SummaryRail";

beforeEach(() => {
  localStorage.clear();
  document.cookie = `${THEME_COOKIE_NAME}=; Path=/; Max-Age=0`;
  document.documentElement.setAttribute("data-theme", "dark");
});
afterEach(cleanup);

describe("SummaryRail's light and dark button", () => {
  it("is there, as a real button, offering Light while the page is dark and Dark once it is light", () => {
    render(<SummaryRail decided={new Set()} />);
    const button = screen.getByRole("button", { name: "Switch to the light theme" });
    expect(button.textContent).toContain("Light");
    fireEvent.click(button);
    expect(screen.getByRole("button", { name: "Switch to the dark theme" }).textContent).toContain("Dark");
  });

  it("switches the page and saves the choice where the Glass and the launcher read it", () => {
    render(<SummaryRail decided={new Set()} />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to the light theme" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(readStoredTheme()).toBe("light");
    expect(document.cookie).toContain(`${THEME_COOKIE_NAME}=light`);
  });
});
