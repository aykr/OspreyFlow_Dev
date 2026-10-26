// @vitest-environment jsdom
//
// ADR-127 Amendment 13's recorded gap (rule 13): the Map canvas is mouse-only, so no link control in
// Map was reachable by keyboard. The links of the row template are listed beside the canvas, each a
// button, and a link is made by choosing its two ends and its type with selects. The mouse path is
// the canvas's own and is unchanged (`MapScreen.rename.test.tsx`).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema, RecipeEdge, RecipeEntity, RowTemplate } from "../../../../../packages/schemas/generated";
import { LinkList } from "./LinkList";

afterEach(cleanup);

const ONTOLOGY = {
  version: 1,
  entity_types: [
    { name: "Endpoint", pole_class: "object", channel: "ochre", shape: "circle", properties: [] },
    { name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] },
    { name: "Place", pole_class: "location", channel: "green", shape: "circle", properties: [] },
  ],
  edge_types: [
    { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"], basis: "direct" },
    { name: "OWNS", from: ["Person"], to: ["Endpoint"], basis: "direct" },
    { name: "USES", from: ["Person"], to: ["Endpoint"], basis: "direct" },
  ],
} as unknown as OntologySchema;

const entity = (ref: string, type: string): RecipeEntity =>
  ({ ref, type, pole_class: "object", on_match: "create", properties: {} }) as RecipeEntity;
const link = (type: string, from: string, to: string): RecipeEdge =>
  ({ type, from, to, properties: {} }) as RecipeEdge;

const TEMPLATE: RowTemplate = {
  entities: [entity("a", "Endpoint"), entity("b", "Endpoint"), entity("p", "Person")],
  edges: [link("COMMUNICATED_WITH", "a", "b"), link("OWNS", "p", "a")],
};

function mount(template: RowTemplate = TEMPLATE, selected: number | null = null) {
  const onSelect = vi.fn();
  const onAdd = vi.fn();
  render(<LinkList template={template} ontology={ONTOLOGY} selectedIndex={selected} onSelect={onSelect} onAdd={onAdd} />);
  return { onSelect, onAdd };
}

describe("LinkList: the links of the row template", () => {
  it("lists each link by its type and its two ends, in the template's order", () => {
    mount();
    const items = within(screen.getByRole("list", { name: "Links" })).getAllByRole("button");
    expect(items.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Link 1: COMMUNICATED_WITH, a to b",
      "Link 2: OWNS, p to a",
    ]);
  });

  it("says plainly when there are none", () => {
    mount({ entities: TEMPLATE.entities, edges: [] });
    expect(screen.queryByRole("list", { name: "Links" })).toBeNull();
    expect(screen.getByText("No links yet.")).toBeTruthy();
  });

  it("selects a link when its button is pressed, by click or by Enter", () => {
    const { onSelect } = mount();
    const second = screen.getByRole("button", { name: "Link 2: OWNS, p to a" });
    fireEvent.click(second);
    expect(onSelect).toHaveBeenLastCalledWith(1);
    // A native button answers Enter and Space with a click, which is what a keyboard sends.
    second.focus();
    expect(document.activeElement).toBe(second);
  });

  it("marks the selected link", () => {
    mount(TEMPLATE, 1);
    expect(screen.getByRole("button", { name: "Link 2: OWNS, p to a" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("moves focus through the list with the arrow keys, Home and End", () => {
    mount({ entities: TEMPLATE.entities, edges: [link("OWNS", "p", "a"), link("OWNS", "p", "b"), link("USES", "p", "a")] });
    const items = within(screen.getByRole("list", { name: "Links" })).getAllByRole("button");
    items[0]!.focus();
    fireEvent.keyDown(items[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1]!, { key: "End" });
    expect(document.activeElement).toBe(items[2]);
    fireEvent.keyDown(items[2]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[2]);
    fireEvent.keyDown(items[2]!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1]!, { key: "Home" });
    expect(document.activeElement).toBe(items[0]);
  });

  it("lists every link however many there are, in a region that scrolls", () => {
    const edges = Array.from({ length: 300 }, (_, i) => link("COMMUNICATED_WITH", "a", i % 2 ? "b" : "a"));
    mount({ entities: TEMPLATE.entities, edges });
    const list = screen.getByRole("list", { name: "Links" });
    expect(within(list).getAllByRole("button")).toHaveLength(300);
    expect(list.style.overflowY).toBe("auto");
    expect(list.style.maxHeight).not.toBe("");
  });
});

describe("LinkList: making a link by keyboard", () => {
  const fromBox = () => screen.getByLabelText("From entity") as HTMLSelectElement;
  const toBox = () => screen.getByLabelText("To entity") as HTMLSelectElement;
  const typeBox = () => screen.getByLabelText("Link type") as HTMLSelectElement;

  it("offers the template's entities for each end, by ref and type", () => {
    mount();
    expect(Array.from(fromBox().options).map((o) => o.value)).toEqual(["a", "b", "p"]);
    expect(Array.from(fromBox().options).map((o) => o.text)).toEqual(["a (Endpoint)", "b (Endpoint)", "p (Person)"]);
  });

  it("starts with the first two entities and the first type that joins them", () => {
    mount();
    expect([fromBox().value, toBox().value, typeBox().value]).toEqual(["a", "b", "COMMUNICATED_WITH"]);
  });

  it("offers only the link types the ontology allows between the chosen ends", () => {
    mount();
    fireEvent.change(fromBox(), { target: { value: "p" } });
    fireEvent.change(toBox(), { target: { value: "a" } });
    expect(Array.from(typeBox().options).map((o) => o.value)).toEqual(["OWNS", "USES"]);
  });

  it("adds the link with the ends and the type chosen", () => {
    const { onAdd } = mount();
    fireEvent.change(fromBox(), { target: { value: "p" } });
    fireEvent.change(toBox(), { target: { value: "b" } });
    fireEvent.change(typeBox(), { target: { value: "USES" } });
    fireEvent.click(screen.getByRole("button", { name: "Add link" }));
    expect(onAdd).toHaveBeenLastCalledWith("p", "b", "USES");
    // The type chosen is the type added, whichever of the allowed ones it is.
    fireEvent.change(typeBox(), { target: { value: "OWNS" } });
    fireEvent.click(screen.getByRole("button", { name: "Add link" }));
    expect(onAdd).toHaveBeenLastCalledWith("p", "b", "OWNS");
  });

  it("refuses a link from an entity to itself, in words, and does not add it", () => {
    const { onAdd } = mount();
    fireEvent.change(toBox(), { target: { value: "a" } });
    expect(screen.getByText("A link joins two different entities.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Add link" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Add link" }));
    expect(onAdd).not.toHaveBeenCalled();
  });

  it("says when the ontology has no link type between the two ends", () => {
    const { onAdd } = mount();
    fireEvent.change(fromBox(), { target: { value: "a" } });
    fireEvent.change(toBox(), { target: { value: "p" } });
    expect(screen.getByText("No ontology link type connects these two entity types.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Add link" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Add link" }));
    expect(onAdd).not.toHaveBeenCalled();
  });

  it("asks for two entities first when the template has fewer", () => {
    mount({ entities: [entity("a", "Endpoint")], edges: [] });
    expect(screen.getByText("Add two entities to join them with a link.")).toBeTruthy();
    expect(screen.queryByLabelText("From entity")).toBeNull();
  });
});
