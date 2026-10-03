// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Edge, Node } from "../../../../packages/schemas/generated";
import { LinkDetails } from "./LinkDetails";

afterEach(cleanup);

const node = (id: string, value: string): Node =>
  ({ id, type: "Endpoint", properties: { value_normalised: value } }) as unknown as Node;

function link(overrides: Partial<Edge> = {}): Edge {
  return {
    id: "e1",
    type: "COMMUNICATED_WITH",
    source: "a",
    target: "b",
    occurrences: 12,
    interval: { valid_from: "2001-05-01", valid_to: "2001-06-30" },
    provenance: {
      state: "asserted",
      sources: [{ document_id: "doc-7", locator: "msg 3", excerpt_hash: "x" }],
      first_seen: "2001-05-01T00:00:00Z",
    },
    ...overrides,
  } as unknown as Edge;
}

const ends = { source: node("a", "jeff@enron.com"), target: node("b", "ken@enron.com") };

describe("LinkDetails", () => {
  it("names the type and the two ends, by what they are rather than their ids", () => {
    render(<LinkDetails edge={link()} {...ends} directed />);
    expect(screen.getByText("COMMUNICATED_WITH")).toBeTruthy();
    expect(screen.getByText(/jeff@enron\.com/)).toBeTruthy();
    expect(screen.getByText(/ken@enron\.com/)).toBeTruthy();
  });

  it("shows the direction when the relationship has one", () => {
    render(<LinkDetails edge={link()} {...ends} directed />);
    expect(screen.getByText(/jeff@enron\.com → ken@enron\.com/)).toBeTruthy();
  });

  it("says plainly when the relationship has no direction", () => {
    render(<LinkDetails edge={link()} {...ends} directed={false} />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/jeff@enron\.com — ken@enron\.com/);
    expect(text).toMatch(/no direction/i);
    expect(text).not.toContain("→");
  });

  it("shows how many records stand behind it", () => {
    render(<LinkDetails edge={link()} {...ends} directed />);
    expect(screen.getByText("12")).toBeTruthy();
  });

  it("counts one when the link does not say", () => {
    render(<LinkDetails edge={link({ occurrences: undefined })} {...ends} directed />);
    expect(screen.getByText("1")).toBeTruthy();
  });

  it("shows the dates, and 'present' when the link is still open", () => {
    const { rerender } = render(<LinkDetails edge={link()} {...ends} directed />);
    expect(document.body.textContent).toContain("2001-05-01");
    expect(document.body.textContent).toContain("2001-06-30");
    rerender(
      <LinkDetails
        edge={link({ interval: { valid_from: "2001-05-01" } as Edge["interval"] })}
        {...ends}
        directed
      />,
    );
    expect(document.body.textContent).toMatch(/present/);
  });

  it("says when there are no dates", () => {
    render(<LinkDetails edge={link({ interval: undefined })} {...ends} directed />);
    expect(document.body.textContent).toMatch(/no dates/i);
  });

  it("lists the sources", () => {
    render(<LinkDetails edge={link()} {...ends} directed />);
    expect(screen.getByText(/doc-7 · msg 3/)).toBeTruthy();
  });

  it("says when there are no sources, rather than showing an empty list", () => {
    const bare = link();
    bare.provenance = { ...bare.provenance, sources: [] };
    render(<LinkDetails edge={bare} {...ends} directed />);
    expect(document.body.textContent).toMatch(/no sources/i);
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("falls back to the id for an end that is not on screen", () => {
    render(<LinkDetails edge={link()} source={ends.source} target={undefined} directed />);
    expect(document.body.textContent).toContain("b");
  });
});
