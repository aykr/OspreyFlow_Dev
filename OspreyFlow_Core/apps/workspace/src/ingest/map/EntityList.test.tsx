// @vitest-environment jsdom
//
// ADR-127 Amendment 13's second gap (rule 13): an entity already in the row template could be chosen
// in Map only by a click on the canvas, so its controls (ref, type, bindings, content, handling,
// delete) were out of a keyboard's reach unless "+ entity" had just selected it. The entities are
// listed beside the canvas, each a button, with the keys the link list has.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RecipeEntity } from "../../../../../packages/schemas/generated";
import { EntityList } from "./EntityList";

afterEach(cleanup);

const entity = (ref: string, type: string): RecipeEntity =>
  ({ ref, type, pole_class: "object", on_match: "create", properties: {} }) as RecipeEntity;

const ENTITIES = [entity("a", "Endpoint"), entity("p", "Person"), entity("l", "Location")];

function mount(entities: RecipeEntity[] = ENTITIES, selected: string | null = null) {
  const onSelect = vi.fn();
  render(<EntityList entities={entities} selectedRef={selected} onSelect={onSelect} />);
  return onSelect;
}

describe("EntityList: the entities of the row template", () => {
  it("lists each entity by its ref and type, in the template's order", () => {
    mount();
    const items = within(screen.getByRole("list", { name: "Entities" })).getAllByRole("button");
    expect(items.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Entity 1: a (Endpoint)",
      "Entity 2: p (Person)",
      "Entity 3: l (Location)",
    ]);
  });

  it("says plainly when there are none", () => {
    mount([]);
    expect(screen.queryByRole("list", { name: "Entities" })).toBeNull();
    expect(screen.getByText("No entities yet.")).toBeTruthy();
  });

  it("selects an entity by its ref when its button is pressed", () => {
    const onSelect = mount();
    fireEvent.click(screen.getByRole("button", { name: "Entity 2: p (Person)" }));
    expect(onSelect).toHaveBeenLastCalledWith("p");
  });

  it("marks the selected entity", () => {
    mount(ENTITIES, "p");
    expect(screen.getByRole("button", { name: "Entity 2: p (Person)" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Entity 1: a (Endpoint)" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("moves focus through the list with the arrow keys, Home and End", () => {
    mount();
    const items = within(screen.getByRole("list", { name: "Entities" })).getAllByRole("button");
    items[0]!.focus();
    fireEvent.keyDown(items[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1]!, { key: "End" });
    expect(document.activeElement).toBe(items[2]);
    fireEvent.keyDown(items[2]!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1]!, { key: "Home" });
    expect(document.activeElement).toBe(items[0]);
  });

  it("lists every entity however many there are, in a region that scrolls", () => {
    mount(Array.from({ length: 300 }, (_, i) => entity(`e${i}`, "Endpoint")));
    const list = screen.getByRole("list", { name: "Entities" });
    expect(within(list).getAllByRole("button")).toHaveLength(300);
    expect(list.style.overflowY).toBe("auto");
    expect(list.style.maxHeight).not.toBe("");
  });
});
