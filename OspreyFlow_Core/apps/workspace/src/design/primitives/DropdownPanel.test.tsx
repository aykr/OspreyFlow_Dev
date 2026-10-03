// @vitest-environment jsdom
//
// A button that opens a small panel: the top bar's way of keeping rarely used controls (the case
// choice, the account) out of sight until asked for (ADR-065). It has to work without a mouse.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DropdownPanel } from "./DropdownPanel";

afterEach(cleanup);

function setup() {
  return render(
    <div>
      <button type="button">Somewhere else</button>
      <DropdownPanel label="Case: Fixture Corp" panelLabel="Case menu">
        {(close) => (
          <>
            <button type="button">Inside one</button>
            <button type="button" onClick={close}>
              Close it
            </button>
          </>
        )}
      </DropdownPanel>
    </div>,
  );
}

const trigger = () => screen.getByRole("button", { name: /Case: Fixture Corp/ });

describe("DropdownPanel", () => {
  it("shows only its button until it is opened", () => {
    setup();
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("group", { name: "Case menu" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Inside one" })).toBeNull();
  });

  it("opens on click and says so", () => {
    setup();
    fireEvent.click(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("group", { name: "Case menu" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Inside one" })).toBeTruthy();
  });

  it("closes when the button is pressed again", () => {
    setup();
    fireEvent.click(trigger());
    fireEvent.click(trigger());
    expect(screen.queryByRole("group", { name: "Case menu" })).toBeNull();
  });

  it("closes on Escape and puts focus back on its button", () => {
    setup();
    fireEvent.click(trigger());
    screen.getByRole("button", { name: "Inside one" }).focus();
    fireEvent.keyDown(screen.getByRole("button", { name: "Inside one" }), { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Case menu" })).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("closes when a click lands outside it, and stays open for a click inside", () => {
    setup();
    fireEvent.click(trigger());
    fireEvent.mouseDown(screen.getByRole("button", { name: "Inside one" }));
    expect(screen.getByRole("group", { name: "Case menu" })).toBeTruthy();
    fireEvent.mouseDown(screen.getByRole("button", { name: "Somewhere else" }));
    expect(screen.queryByRole("group", { name: "Case menu" })).toBeNull();
  });

  it("closes when keyboard focus moves on to something outside it", () => {
    setup();
    fireEvent.click(trigger());
    const inside = screen.getByRole("button", { name: "Inside one" });
    inside.focus();
    fireEvent.blur(inside, { relatedTarget: screen.getByRole("button", { name: "Somewhere else" }) });
    expect(screen.queryByRole("group", { name: "Case menu" })).toBeNull();
  });

  it("stays open while focus moves between its own controls", () => {
    setup();
    fireEvent.click(trigger());
    const inside = screen.getByRole("button", { name: "Inside one" });
    fireEvent.blur(inside, { relatedTarget: screen.getByRole("button", { name: "Close it" }) });
    expect(screen.getByRole("group", { name: "Case menu" })).toBeTruthy();
  });

  it("hands its content a way to close it", () => {
    setup();
    fireEvent.click(trigger());
    fireEvent.click(screen.getByRole("button", { name: "Close it" }));
    expect(screen.queryByRole("group", { name: "Case menu" })).toBeNull();
  });
});
