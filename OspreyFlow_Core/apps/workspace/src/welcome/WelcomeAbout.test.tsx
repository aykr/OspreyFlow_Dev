// @vitest-environment jsdom
// The welcome page's About says what the guides say (D2a, 9 November 2026): the four places by the names
// `help/roles.ts` gives them, with nothing of what is not built (releases, one queue), and drawing boards
// as built, promotion among them (L3.4), with nothing of what is not (the alert when new data meets a
// drawn item, a drawn dataset merged into another).
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PLACE_WORDS } from "../help/roles";
import { WelcomeAbout } from "./WelcomeAbout";

describe("WelcomeAbout", () => {
  afterEach(cleanup);

  it("names the four places as the help page names them, claiming nothing not built", () => {
    render(<WelcomeAbout />);
    const list = screen.getByLabelText("The four places");
    for (const place of Object.values(PLACE_WORDS)) expect(within(list).getByText(place.name)).toBeTruthy();
    expect(within(list).getAllByRole("term")).toHaveLength(4);
    expect(list.textContent ?? "").not.toMatch(/releases|one queue/i);
  });

  it("says nowhere that alerts are routed to a team", () => {
    render(<WelcomeAbout />);
    expect(document.body.textContent ?? "").not.toMatch(/queue for the team/i);
  });

  it("describes drawing boards as built, promotion as one load, and nothing still coming", () => {
    render(<WelcomeAbout />);
    const boards = screen.getByLabelText("Drawing boards");
    expect(within(boards).getByText("Declare and draw")).toBeTruthy();
    expect(within(boards).getByText("Promoted as one load")).toBeTruthy();
    expect(boards.textContent ?? "").toMatch(/as one load/);
    expect(boards.textContent ?? "").not.toMatch(/new data meets|merged into another|automatic/i);
  });
});
