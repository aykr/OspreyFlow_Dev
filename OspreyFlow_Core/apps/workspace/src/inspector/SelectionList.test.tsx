// @vitest-environment jsdom
// ADR-093 step 2: the Inspector lists the selection when more than one node is selected; choosing
// one centres the canvas on it, and each can be taken out of the selection.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeNode } from "../testing/fixtures";
import { SelectionList } from "./SelectionList";

afterEach(cleanup);

const ADA = makeNode("p1", { properties: { family_name: "LOVELACE", given_names: "Ada" } });
const BOB = makeNode("p2", { properties: { family_name: "BABBAGE", given_names: "Charles" } });

describe("SelectionList", () => {
  it("lists each selected node by name, with how many in the heading", () => {
    render(<SelectionList nodes={[ADA, BOB]} onCentre={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Selected (2)" })).toBeTruthy();
    const rows = screen.getAllByRole("listitem").map((r) => r.textContent ?? "");
    expect(rows[0]).toContain("LOVELACE");
    expect(rows[1]).toContain("BABBAGE");
  });

  it("centres on a node when its name is chosen, and takes it out with ×", () => {
    const onCentre = vi.fn();
    const onRemove = vi.fn();
    render(<SelectionList nodes={[ADA, BOB]} onCentre={onCentre} onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: /Centre on .*LOVELACE/ }));
    expect(onCentre).toHaveBeenCalledWith("p1");
    fireEvent.click(screen.getByRole("button", { name: /Remove .*BABBAGE.* from the selection/ }));
    expect(onRemove).toHaveBeenCalledWith("p2");
  });

  it("shows nothing for one node or none, which the Inspector already shows on its own", () => {
    const { container } = render(<SelectionList nodes={[ADA]} onCentre={vi.fn()} onRemove={vi.fn()} />);
    expect(container.textContent).toBe("");
  });
});
