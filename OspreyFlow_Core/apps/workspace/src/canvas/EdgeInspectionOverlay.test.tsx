// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Edge } from "../../../../packages/schemas/generated";
import { EdgeInspectionOverlay } from "./EdgeInspectionOverlay";

afterEach(cleanup);

function edge(provenance: Record<string, unknown>): Edge {
  return {
    id: "e1",
    type: "COMMUNICATED_WITH",
    source: "a",
    target: "b",
    occurrences: 2,
    provenance: { state: "asserted", first_seen: "2001-05-01T00:00:00Z", ...provenance },
  } as unknown as Edge;
}

describe("EdgeInspectionOverlay sources (ADR-130 Amendment 2)", () => {
  it("lists the sources a link names", () => {
    render(
      <EdgeInspectionOverlay
        x={0}
        y={0}
        edge={edge({ sources: [{ document_id: "doc-7", locator: "msg 3", excerpt_hash: "x" }] })}
        onClose={() => undefined}
      />,
    );
    expect(screen.getByText("doc-7 · msg 3")).toBeTruthy();
    expect(screen.queryByText(/data this case does not read/)).toBeNull();
  });

  it("says its sources are in data this case does not read, when they are withheld", () => {
    render(
      <EdgeInspectionOverlay
        x={0}
        y={0}
        edge={edge({ sources: [], sources_withheld: true })}
        onClose={() => undefined}
      />,
    );
    expect(screen.getByText("Its sources are in data this case does not read")).toBeTruthy();
    expect(screen.queryByText(/No sources recorded/)).toBeNull();
  });
});
