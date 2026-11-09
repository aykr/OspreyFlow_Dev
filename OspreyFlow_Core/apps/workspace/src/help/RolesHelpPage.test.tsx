// @vitest-environment jsdom
// The *Roles, teams and Authors* help page (ADR-145 Amendment 4 decision 12): every right's words from
// `roles.ts`, and the way back focused when it opens.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RolesHelpPage } from "./RolesHelpPage";
import { HELP_TITLE, RIGHT_WORDS, rightName, rightSays } from "./roles";

afterEach(cleanup);

describe("the help page", () => {
  it("draws every right's words from roles.ts, and its way back has focus", () => {
    const back = vi.fn();
    render(<RolesHelpPage backTo="Admin" onBack={back} />);
    expect(screen.getByRole("heading", { level: 2, name: HELP_TITLE })).toBeTruthy();
    const rights = screen.getByRole("region", { name: "What each right lets you do" });
    for (const right of Object.keys(RIGHT_WORDS)) {
      expect(within(rights).getByText(rightName(right))).toBeTruthy();
      expect(within(rights).getAllByText(rightSays(right)).length).toBeGreaterThan(0);
    }
    const button = screen.getByRole("button", { name: "← Back to Admin" });
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(back).toHaveBeenCalledOnce();
  });
});
