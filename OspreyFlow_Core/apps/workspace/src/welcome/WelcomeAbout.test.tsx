// @vitest-environment jsdom
// The welcome page's About says what the guides and the help page say (D2a, 9 November 2026): the four
// places in `help/roles.ts`'s own words, and drawing boards as built, with nothing about promotion,
// which is not built.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PLACE_WORDS } from "../help/roles";
import { WelcomeAbout } from "./WelcomeAbout";

describe("WelcomeAbout", () => {
  afterEach(cleanup);

  it("names the four places in the help page's own words", () => {
    render(<WelcomeAbout />);
    const list = screen.getByLabelText("The four places");
    for (const place of Object.values(PLACE_WORDS)) {
      expect(within(list).getByText(place.name)).toBeTruthy();
      expect(within(list).getByText(place.says)).toBeTruthy();
    }
    expect(within(list).getAllByRole("term")).toHaveLength(4);
  });

  it("describes drawing boards as built, and claims no promotion", () => {
    render(<WelcomeAbout />);
    const boards = screen.getByLabelText("Drawing boards");
    expect(within(boards).getByText("Declare and draw")).toBeTruthy();
    expect(boards.textContent ?? "").not.toMatch(/promot/i);
  });
});
