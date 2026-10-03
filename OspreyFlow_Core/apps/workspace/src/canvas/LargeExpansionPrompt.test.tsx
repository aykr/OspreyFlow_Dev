// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LargeExpansionPrompt } from "./LargeExpansionPrompt";

afterEach(cleanup);

function setup(
  overrides: Partial<Parameters<typeof LargeExpansionPrompt>[0]> = {},
) {
  const handlers = {
    onChooseType: vi.fn(),
    onChooseAll: vi.fn(),
    onCancel: vi.fn(),
  };
  render(
    <LargeExpansionPrompt
      x={10}
      y={20}
      wouldAdd={1090}
      options={[
        { edgeType: "COMMUNICATED_WITH", wouldAdd: 1090 },
        { edgeType: "MENTIONED_IN", wouldAdd: 12 },
      ]}
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
}

describe("LargeExpansionPrompt", () => {
  it("says how many nodes the expansion would add", () => {
    setup();
    expect(screen.getByRole("alertdialog").textContent).toContain("1,090");
  });

  it("offers each relationship type with its own count, and passes the choice on", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: /MENTIONED_IN.*12/ }));
    expect(h.onChooseType).toHaveBeenCalledWith("MENTIONED_IN");
  });

  it("offers to add everything, with the number, only on request", () => {
    const h = setup();
    expect(h.onChooseAll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Add all 1,090/ }));
    expect(h.onChooseAll).toHaveBeenCalledOnce();
  });

  it("can be cancelled, and adds nothing", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(h.onCancel).toHaveBeenCalledOnce();
    expect(h.onChooseAll).not.toHaveBeenCalled();
    expect(h.onChooseType).not.toHaveBeenCalled();
  });

  it("says plainly when the size could not be counted", () => {
    setup({ wouldAdd: "unavailable", options: [] });
    expect(screen.getByRole("alertdialog").textContent).toContain(
      "could not be counted",
    );
    expect(screen.getByRole("button", { name: /Add all/ })).toBeTruthy();
  });
});
