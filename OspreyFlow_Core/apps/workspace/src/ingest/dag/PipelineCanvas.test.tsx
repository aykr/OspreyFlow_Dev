// @vitest-environment jsdom
// The pipeline canvas, read-only (ADR-108 phase A): every node a focusable button named by its
// stage and label, edges drawn between them, and a selected node's settings read in place.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { PipelineGraph } from "../../../../../packages/schemas/generated";
import { PipelineCanvas } from "./PipelineCanvas";
import { pipelineLayout } from "./pipelineLayout";

afterEach(cleanup);

const CHAIN: PipelineGraph = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "pole" } },
    {
      id: "source",
      kind: "source",
      label: "Carrier B phone records",
      config: { connector_profile: "cell-site-csv", source_location: "uploaded/carrier-b.csv" },
    },
    { id: "profile", kind: "profile", label: "Profile", config: {} },
    { id: "map", kind: "map", label: "Map", config: {} },
    { id: "load", kind: "load", label: "Load", config: { dataset_id: "ds-1" } },
  ],
  edges: [
    { source: "domain", target: "source" },
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
  ],
};

describe("pipelineLayout", () => {
  it("places each stage one column right of everything that feeds it", () => {
    const placed = Object.fromEntries(pipelineLayout(CHAIN).map((p) => [p.id, p.column]));
    expect(placed).toEqual({ domain: 0, source: 1, profile: 2, map: 3, load: 4 });
  });

  it("gives parallel branches their own rows in one column", () => {
    const branched: PipelineGraph = {
      nodes: [
        ...(CHAIN.nodes ?? []),
        { id: "source2", kind: "source", label: "Subscriber list", config: {} },
      ],
      edges: [...(CHAIN.edges ?? []), { source: "domain", target: "source2" }],
    };
    const placed = pipelineLayout(branched);
    const inColumnOne = placed.filter((p) => p.column === 1).map((p) => p.row);
    expect(inColumnOne.sort()).toEqual([0, 1]);
  });
});

describe("PipelineCanvas", () => {
  it("draws every node as a focusable button named by stage and label, and the edges", () => {
    render(<PipelineCanvas pipeline={CHAIN} />);
    const canvas = screen.getByRole("group", { name: "Pipeline" });
    expect(within(canvas).getAllByRole("button")).toHaveLength(5);
    expect(within(canvas).getByRole("button", { name: "Source: Carrier B phone records" })).toBeTruthy();
    expect(canvas.querySelectorAll("svg line, svg path").length).toBeGreaterThanOrEqual(4);
  });

  it("a chosen node's settings read in place, and nothing is editable", () => {
    render(<PipelineCanvas pipeline={CHAIN} />);
    fireEvent.click(screen.getByRole("button", { name: "Source: Carrier B phone records" }));
    const details = screen.getByRole("region", { name: "Node settings" });
    expect(details.textContent).toContain("cell-site-csv");
    expect(details.textContent).toContain("uploaded/carrier-b.csv");
    expect(within(details).queryAllByRole("textbox")).toHaveLength(0);
  });
});
