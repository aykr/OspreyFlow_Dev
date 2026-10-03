// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReasonPrompt } from "./ReasonPrompt";

afterEach(cleanup);

function mount() {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(
    <ReasonPrompt
      x={10}
      y={10}
      title="Confirm these two as the same"
      confirmLabel="Confirm"
      onSubmit={onSubmit}
      onCancel={onCancel}
    />,
  );
  return { onSubmit, onCancel };
}

describe("ReasonPrompt", () => {
  it("names what is being asked and puts focus in the reason box", () => {
    mount();
    expect(screen.getByText("Confirm these two as the same")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("textbox"));
  });

  it("keeps the confirm button off until there is a reason", () => {
    mount();
    const button = screen.getByRole("button", { name: "Confirm" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Same phone number" } });
    expect(button.disabled).toBe(false);
  });

  it("hands over the reason trimmed", () => {
    const { onSubmit } = mount();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "  Same phone number  " } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onSubmit).toHaveBeenCalledWith("Same phone number");
  });

  it("confirms with Control-Enter only once there is a reason", () => {
    const { onSubmit } = mount();
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", ctrlKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Same phone number" } });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", ctrlKey: true });
    expect(onSubmit).toHaveBeenCalledWith("Same phone number");
  });

  it("cancels with the button and with Escape, writing nothing", () => {
    const { onSubmit, onCancel } = mount();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(2);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
