// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { EntityTypeDef } from "../../../../packages/schemas/generated";
import { LABEL_CHOICES_KEY, forgetLabelChoicesForTest, getLabelChoices } from "./labelChoices";
import { LabelsMenu } from "./LabelsMenu";

const TYPES: EntityTypeDef[] = [
  {
    name: "Person",
    pole_class: "person",
    channel: "indigo",
    shape: "circle",
    identifiers: ["nino"],
    properties: [
      { name: "family_name", type: "string", indexed: true },
      { name: "given_names", type: "string", indexed: true },
      { name: "date_of_birth", type: "date", sensitivity: "high" },
    ],
  },
  {
    name: "Organisation",
    pole_class: "organisation",
    channel: "cyan",
    shape: "hexagon",
    identifiers: [],
    properties: [{ name: "name", type: "string", indexed: true }],
  },
  {
    name: "Document",
    pole_class: "object",
    channel: "ochre",
    shape: "square",
    identifiers: [],
    properties: [{ name: "title", type: "string", indexed: true }],
  },
];

beforeEach(() => {
  localStorage.clear();
  forgetLabelChoicesForTest();
});
afterEach(cleanup);

function open() {
  fireEvent.click(screen.getByRole("button", { name: "Labels" }));
}

describe("LabelsMenu", () => {
  it("is closed until the button is pressed, and says it is open", () => {
    render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    const button = screen.getByRole("button", { name: "Labels" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("combobox")).toBeNull();
    open();
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("combobox", { name: "Label for Person" })).toBeTruthy();
  });

  it("offers one picker for each type in view, and none for a type that is not", () => {
    render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => ["Person", "Organisation"]} />);
    open();
    expect(screen.getAllByRole("combobox").map((c) => c.getAttribute("aria-label"))).toEqual([
      "Label for Organisation",
      "Label for Person",
    ]);
  });

  it("lists Default and then the type's own properties, without the sensitive one", () => {
    render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    open();
    const options = within(screen.getByRole("combobox", { name: "Label for Person" }))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["Default", "nino", "family_name", "given_names"]);
  });

  it("keeps a choice when one is made, and returns to the default when Default is chosen", () => {
    render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    open();
    const picker = screen.getByRole("combobox", { name: "Label for Person" }) as HTMLSelectElement;
    fireEvent.change(picker, { target: { value: "nino" } });
    expect(getLabelChoices()).toEqual({ Person: "nino" });
    expect(picker.value).toBe("nino");
    fireEvent.change(picker, { target: { value: "" } });
    expect(getLabelChoices()).toEqual({});
    expect(picker.value).toBe("");
  });

  it("shows a choice already made", () => {
    localStorage.setItem(LABEL_CHOICES_KEY, JSON.stringify({ Organisation: "name" }));
    forgetLabelChoicesForTest();
    render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => ["Organisation"]} />);
    open();
    expect((screen.getByRole("combobox", { name: "Label for Organisation" }) as HTMLSelectElement).value).toBe("name");
  });

  it("says so when nothing is in view, and when a type in view has no property to offer", () => {
    const { rerender } = render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => []} />);
    open();
    expect(screen.getByText("No nodes in view to label.")).toBeTruthy();
    rerender(
      <LabelsMenu
        entityTypes={[{ name: "Bare", pole_class: "object", channel: "ochre", shape: "square" }]}
        getTypesInView={() => ["Bare"]}
      />,
    );
    expect(screen.getByText("Bare: no property to choose from.")).toBeTruthy();
  });

  it("says the choice is kept in this browser only", () => {
    render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    open();
    expect(screen.getByText(/kept in this browser only/i)).toBeTruthy();
  });

  it("closes on Escape and gives focus back to the button", () => {
    render(<LabelsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    const button = screen.getByRole("button", { name: "Labels" });
    open();
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Label for Person" }), { key: "Escape" });
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(document.activeElement).toBe(button);
  });
});
