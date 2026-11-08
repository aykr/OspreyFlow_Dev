// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SaveViewForm } from "./SaveViewForm";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-brand");
});

function form(onSave: (name: string) => Promise<string | null> = vi.fn(async () => null)) {
  const onCancel = vi.fn();
  render(<SaveViewForm count={3} defaultName="Selection of 3 nodes" onSave={onSave} onCancel={onCancel} />);
  return { onSave, onCancel };
}

describe("SaveViewForm", () => {
  it("starts with the default name, focused, and says the view is private until shared", () => {
    form();
    const input = screen.getByLabelText("View name") as HTMLInputElement;
    expect(input.value).toBe("Selection of 3 nodes");
    expect(document.activeElement).toBe(input);
    expect(screen.getByText(/Only you see it until you share it/)).toBeTruthy();
  });

  it("saves under the name given", async () => {
    const { onSave } = form();
    fireEvent.change(screen.getByLabelText("View name"), { target: { value: " Kestrel's contacts " } });
    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith("Kestrel's contacts"));
  });

  it("refuses an empty name without saving, and says a refusal from the server", async () => {
    const { onSave } = form(vi.fn(async () => "Saving a view needs the right to work this case."));
    fireEvent.change(screen.getByLabelText("View name"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    expect(screen.getByRole("alert").textContent).toBe("Give the view a name.");
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("View name"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Saving a view needs the right to work this case.");
  });

  it("cancels on Escape", () => {
    const { onCancel } = form();
    fireEvent.keyDown(screen.getByLabelText("View name"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });

  it("is a GOV.UK form under the GOV.UK brand", () => {
    document.documentElement.setAttribute("data-brand", "govuk");
    form();
    expect(document.querySelector(".govuk-form-group .govuk-label")?.textContent).toBe("View name");
    expect(document.querySelector("input.govuk-input")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Save view" }).className).toBe("govuk-button");
  });
});
