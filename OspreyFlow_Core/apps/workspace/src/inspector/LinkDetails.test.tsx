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

const ends = { source: node("a", "jeff@enron.com"), target: node("b", "kit@enron.com") };

describe("LinkDetails", () => {
  it("names the type and the two ends, by what they are rather than their ids", () => {
    render(<LinkDetails edge={link()} {...ends} directed />);
    expect(screen.getByText("COMMUNICATED_WITH")).toBeTruthy();
    expect(screen.getByText(/jeff@enron\.com/)).toBeTruthy();
    expect(screen.getByText(/kit@enron\.com/)).toBeTruthy();
  });

  it("shows the direction when the relationship has one", () => {
    render(<LinkDetails edge={link()} {...ends} directed />);
    expect(screen.getByText(/jeff@enron\.com → kit@enron\.com/)).toBeTruthy();
  });

  it("says plainly when the relationship has no direction", () => {
    render(<LinkDetails edge={link()} {...ends} directed={false} />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/jeff@enron\.com — kit@enron\.com/);
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

  it("shows the dates, and '(open)' when the link is still running", () => {
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
    expect(document.body.textContent).toContain("from 2001-05-01 (open)");
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

// ADR-081 step B: the Inspector says what stands behind the link, and, for a link of a Direct type an
// analyst marked probabilistic, that the reason is in the change history.
describe("LinkDetails and the basis", () => {
  it("says a link of a Direct type is Direct", () => {
    render(<LinkDetails edge={link()} {...ends} directed typeBasis="direct" />);
    expect(screen.getByText(/^Direct/)).toBeTruthy();
    expect(document.body.textContent).toMatch(/loaded record/i);
  });

  it("says a link of a Probabilistic type is Probabilistic", () => {
    render(<LinkDetails edge={link()} {...ends} directed typeBasis="probabilistic" />);
    expect(screen.getByText(/^Probabilistic/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/change history/i);
  });

  it("says when an analyst marked a Direct type's link probabilistic, and where the reason is", () => {
    render(<LinkDetails edge={link({ basis: "probabilistic" })} {...ends} directed typeBasis="direct" />);
    expect(screen.getByText(/^Probabilistic/)).toBeTruthy();
    expect(document.body.textContent).toMatch(/declared by an analyst/i);
    expect(document.body.textContent).toMatch(/change history/i);
  });

  it("shows no basis row for a type that has none", () => {
    render(<LinkDetails edge={link()} {...ends} directed typeBasis={null} />);
    expect(screen.queryByText("Basis")).toBeNull();
  });

  it("says a span still running is open, from when it began", () => {
    render(
      <LinkDetails
        edge={link({ interval: { valid_from: "2026-03-01T09:00:00Z", valid_to: null } })}
        {...ends}
        directed
      />,
    );
    expect(screen.getByText("from 2026-03-01T09:00:00Z (open)")).toBeTruthy();
    expect(document.body.textContent).not.toContain("present");
  });

  it("shows a closed span with both ends, and a link with no dates as such", () => {
    render(<LinkDetails edge={link()} {...ends} directed />);
    expect(screen.getByText("2001-05-01 – 2001-06-30")).toBeTruthy();
    cleanup();
    render(<LinkDetails edge={link({ interval: null })} {...ends} directed />);
    expect(screen.getByText("No dates recorded")).toBeTruthy();
  });
});
