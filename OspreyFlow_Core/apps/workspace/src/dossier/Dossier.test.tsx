// @vitest-environment jsdom
import Graph from "graphology";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import type { OntologyRegistry } from "../ontology/schema";
import type { WorkingSetGraph } from "../workingset/store";
import * as api from "./api";
import { Dossier } from "./Dossier";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function graphOf(provenance: Record<string, unknown>): WorkingSetGraph {
  const graph = new Graph();
  const data = { id: "n1", type: "Endpoint", properties: {}, provenance } as unknown as Node;
  graph.addNode("n1", { data });
  return graph as unknown as WorkingSetGraph;
}

const props = {
  ontology: {} as unknown as OntologyRegistry,
  nodeId: "n1",
  investigationId: "inv-1",
  apiBaseUrl: "http://api",
  bearerToken: "t",
};

describe("Dossier sources (ADR-130 Amendment 2)", () => {
  it("fetches the documents a node's sources name", async () => {
    const fetchSpy = vi.spyOn(api, "fetchDocumentView").mockResolvedValue(null);
    render(
      <Dossier
        {...props}
        graph={graphOf({
          state: "asserted",
          sources: [{ document_id: "doc-7", locator: "msg 3", excerpt_hash: "x" }],
          first_seen: "x",
        })}
      />,
    );
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    expect(fetchSpy.mock.calls[0]?.[3]).toBe("doc-7");
  });

  it("skips a node whose sources are withheld, and says why", async () => {
    const fetchSpy = vi.spyOn(api, "fetchDocumentView").mockResolvedValue(null);
    render(
      <Dossier
        {...props}
        graph={graphOf({ state: "asserted", sources: [], sources_withheld: true, first_seen: "x" })}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("Its sources are in data this case does not read")).toBeTruthy(),
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.queryByText(/No messages found/)).toBeNull();
  });
});
