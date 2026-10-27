// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EntityTypeDef } from "../../../../packages/schemas/generated";
import { GLYPH_NAMES } from "../color/nodeGlyphs";
import { ICON_CHOICES_KEY, forgetIconChoicesForTest, getIconChoices } from "./iconChoices";
import { IconsMenu } from "./IconsMenu";

const DATA = "data:image/png;base64,iVBORw0KGgo=";
const TYPES: EntityTypeDef[] = [
  { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", icon: "person" },
  { name: "Device", pole_class: "object", channel: "plum", shape: "square" },
  { name: "Location", pole_class: "location", channel: "ochre", shape: "pin", icon: "pin" },
];

beforeEach(() => {
  localStorage.clear();
  forgetIconChoicesForTest();
});
afterEach(cleanup);

function open(): void {
  fireEvent.click(screen.getByRole("button", { name: "Icons" }));
}

function picker(type: string): HTMLSelectElement {
  return screen.getByRole("combobox", { name: `Icon for ${type}` }) as HTMLSelectElement;
}

describe("IconsMenu and icons chosen by value (ADR-128 Decision 4)", () => {
  const WITH_RULE: EntityTypeDef[] = [
    {
      name: "Endpoint",
      pole_class: "object",
      channel: "cyan",
      shape: "hexagon",
      icon: "device",
      icon_by_value: { property: "endpoint_kind", icons: { handle: "keypad" } },
    },
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", icon: "person" },
  ];

  it("says, for a type whose icon depends on a value, that a choice here replaces those icons", () => {
    render(<IconsMenu entityTypes={WITH_RULE} getTypesInView={() => ["Endpoint", "Person"]} />);
    open();
    const notes = screen.getAllByText("Choosing an icon here replaces the icons chosen by endpoint kind.");
    expect(notes).toHaveLength(1);
  });
});

describe("IconsMenu", () => {
  it("is closed until the button is pressed, and says it is open", () => {
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    const button = screen.getByRole("button", { name: "Icons" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("combobox")).toBeNull();
    open();
    expect(button.getAttribute("aria-expanded")).toBe("true");
  });

  it("offers one picker for each type in view, and none for a type that is not", () => {
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person", "Location"]} />);
    open();
    expect(screen.getAllByRole("combobox").map((c) => c.getAttribute("aria-label"))).toEqual([
      "Icon for Location",
      "Icon for Person",
    ]);
  });

  it("lists the default (saying what it is), every drawing, and none", () => {
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person", "Device"]} />);
    open();
    const options = (type: string) => within(picker(type)).getAllByRole("option").map((o) => o.textContent);
    expect(options("Person")[0]).toBe("Default (person)");
    expect(options("Device")[0]).toBe("Default (none)");
    expect(options("Person")).toEqual(expect.arrayContaining([...GLYPH_NAMES, "None"]));
    expect(options("Person")).toHaveLength(GLYPH_NAMES.length + 2);
  });

  it("keeps a drawing when one is chosen, none when None is, and the default when Default is", () => {
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    open();
    fireEvent.change(picker("Person"), { target: { value: "glyph:shield" } });
    expect(getIconChoices()).toEqual({ Person: { kind: "glyph", name: "shield" } });
    fireEvent.change(picker("Person"), { target: { value: "none" } });
    expect(getIconChoices()).toEqual({ Person: { kind: "none" } });
    fireEvent.change(picker("Person"), { target: { value: "" } });
    expect(getIconChoices()).toEqual({});
    expect(picker("Person").value).toBe("");
  });

  it("shows a choice already made, a picture of the analyst's own included", () => {
    localStorage.setItem(
      ICON_CHOICES_KEY,
      JSON.stringify({ Person: { kind: "image", dataUrl: DATA }, Device: { kind: "glyph", name: "key" } }),
    );
    forgetIconChoicesForTest();
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person", "Device"]} />);
    open();
    expect(picker("Device").value).toBe("glyph:key");
    expect(picker("Person").value).toBe("image");
    expect(screen.getByAltText("Your picture for Person")).toBeTruthy();
  });

  it("takes a picture from a file, makes the thumbnail, and keeps it for that type", async () => {
    const makeThumbnail = vi.fn().mockResolvedValue(DATA);
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} makeThumbnail={makeThumbnail} />);
    open();
    const file = new File(["x"], "face.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Picture for Person"), { target: { files: [file] } });
    await waitFor(() => expect(getIconChoices()).toEqual({ Person: { kind: "image", dataUrl: DATA } }));
    expect(makeThumbnail).toHaveBeenCalledWith(file);
  });

  it("says why a file cannot be used, and changes nothing", async () => {
    const makeThumbnail = vi.fn().mockRejectedValue(new Error("That file is not a picture I can use: png, jpeg, webp or gif."));
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} makeThumbnail={makeThumbnail} />);
    open();
    fireEvent.change(screen.getByLabelText("Picture for Person"), {
      target: { files: [new File(["x"], "a.svg", { type: "image/svg+xml" })] },
    });
    expect((await screen.findByRole("status")).textContent).toMatch(/not a picture I can use/);
    expect(getIconChoices()).toEqual({});
  });

  it("says so when the browser would not keep the picture, though it holds for this page", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} makeThumbnail={async () => DATA} />);
    open();
    fireEvent.change(screen.getByLabelText("Picture for Person"), {
      target: { files: [new File(["x"], "a.png", { type: "image/png" })] },
    });
    expect((await screen.findByRole("status")).textContent).toMatch(/this page only/i);
    expect(getIconChoices()).toEqual({ Person: { kind: "image", dataUrl: DATA } });
  });

  it("says nothing is in view when nothing is, and that the choice stays in this browser", () => {
    const { rerender } = render(<IconsMenu entityTypes={TYPES} getTypesInView={() => []} />);
    open();
    expect(screen.getByText("No nodes in view to give an icon.")).toBeTruthy();
    rerender(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    expect(screen.getByText(/kept in this browser only/i)).toBeTruthy();
  });

  it("closes on Escape and gives focus back to the button", () => {
    render(<IconsMenu entityTypes={TYPES} getTypesInView={() => ["Person"]} />);
    const button = screen.getByRole("button", { name: "Icons" });
    open();
    fireEvent.keyDown(picker("Person"), { key: "Escape" });
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(document.activeElement).toBe(button);
  });
});
