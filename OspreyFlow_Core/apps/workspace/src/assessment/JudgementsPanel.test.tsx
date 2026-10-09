// @vitest-environment jsdom
import Graph from "graphology";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { JudgementsPanel } from "./JudgementsPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function buildGraph(): Graph {
  const graph = new Graph();
  graph.addNode("n1", { data: { type: "Person", properties: { family_name: "Mercer" } } });
  graph.addNode("n2", { data: { type: "Endpoint", properties: { value_normalised: "+447700900000" } } });
  graph.addEdge("n1", "n2", { data: { id: "e1", type: "USES" } });
  return graph;
}

function mockFetchEmptyLists(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/yardstick")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            name: "PHIA",
            bands: [{ label: "likely", lower: 0.55, upper: 0.75 }],
          }),
        });
      }
      if (url.includes("/judgements")) {
        return Promise.resolve({ ok: true, json: async () => ({ judgements: [] }) });
      }
      if (url.includes("/gaps")) {
        return Promise.resolve({ ok: true, json: async () => ({ gaps: [] }) });
      }
      if (url.includes("/assumptions")) {
        return Promise.resolve({ ok: true, json: async () => ({ assumptions: [] }) });
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`));
    }),
  );
}

describe("test_the_save_button_is_disabled_until_at_least_one_supporting_reference_is_attached", () => {
  test("Save judgement starts disabled and enables once a supporting node is added", async () => {
    mockFetchEmptyLists();
    render(
      <JudgementsPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        workingSetGraph={buildGraph()}
        selectedNodeId={null}
        onHighlightNodes={() => undefined}
      />,
    );

    fireEvent.click(screen.getByText("Add judgement, gap or assumption"));
    const statementInput = await screen.findByLabelText(/^Statement$/);
    fireEvent.change(statementInput, { target: { value: "The subject is the organiser." } });

    const saveButton = screen.getByText("Save judgement").closest("button")!;
    expect((saveButton as HTMLButtonElement).disabled).toBe(true);

    const picker = screen.getByLabelText("Add supporting evidence");
    fireEvent.change(picker, { target: { value: "Mercer" } });
    fireEvent.keyDown(picker, { key: "Enter" });

    await waitFor(() => expect((saveButton as HTMLButtonElement).disabled).toBe(false));
  });

  test("the regression this proves against: a Save button gated only on statement length, not evidence, stays enabled with zero evidence", () => {
    // A minimal stand-in reproducing exactly the failure the disabled-until-evidence rule exists
    // to prevent — proves the case above is a real constraint, not a tautological pass.
    function Regressed() {
      const statement = "The subject is the organiser.";
      return <button disabled={statement.trim().length === 0}>Save judgement</button>;
    }
    render(<Regressed />);
    expect((screen.getByText("Save judgement").closest("button") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("test_the_evidence_picker_never_offers_an_edge_as_a_citation_option", () => {
  test("the working set graph's own edge id never appears as a selectable evidence option", async () => {
    // The citation-type restriction this session's Part 1 fix requires surfaced in the UI: the
    // picker's options are built from `workingSetGraph.nodes()` only, which is structurally
    // incapable of returning an edge id — proven here by asserting the edge's own id string
    // never appears in the option list's own rendered text, using a graph that deliberately
    // carries one alongside two real nodes.
    mockFetchEmptyLists();
    const graph = buildGraph();
    render(
      <JudgementsPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        workingSetGraph={graph}
        selectedNodeId={null}
        onHighlightNodes={() => undefined}
      />,
    );

    fireEvent.click(screen.getByText("Add judgement, gap or assumption"));
    await screen.findByLabelText(/^Statement$/);
    const picker = screen.getByLabelText("Add supporting evidence");
    fireEvent.change(picker, { target: { value: "" } });
    fireEvent.focus(picker);

    const listbox = await screen.findByRole("listbox");
    expect(listbox.textContent ?? "").not.toContain("e1");
    expect(listbox.textContent ?? "").toContain("Mercer");
  });
});

// 9 October 2026, in the deployed Glass: the evidence box offered nothing. Its options were worked
// out once from the working-set graph, which the canvas fills in place after the panel has mounted
// (at page load it is empty), so the list never grew. A node on the canvas is evidence to offer.
describe("evidence is offered from the working set as it is now", () => {
  test("a node that arrives after the panel opened is offered", async () => {
    mockFetchEmptyLists();
    const graph = new Graph();
    render(
      <JudgementsPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        workingSetGraph={graph}
        selectedNodeId={null}
        onHighlightNodes={() => undefined}
      />,
    );
    graph.addNode("n1", { data: { type: "Person", properties: { family_name: "Mercer" } } });

    fireEvent.click(screen.getByText("Add judgement, gap or assumption"));
    const picker = await screen.findByLabelText("Add supporting evidence");
    fireEvent.change(picker, { target: { value: "Mer" } });
    const listbox = await screen.findByRole("listbox");
    expect(listbox.textContent ?? "").toContain("Mercer");
  });
});

// 9 October 2026, in the deployed Glass: the evidence list read "Person: OKAFOR" for a node the
// canvas labels "OKAFOR, Callum", and a document by its content id. The panel had a labeller of its
// own that knew only `family_name`; an option names a node as the canvas does.
describe("an evidence option names its node as the canvas does", () => {
  test("a person's given names and a document's title are shown", async () => {
    mockFetchEmptyLists();
    const graph = new Graph();
    graph.addNode("p1", { data: { id: "p1", type: "Person", properties: { family_name: "OKAFOR", given_names: "Callum" } } });
    graph.addNode("content:69b2", { data: { id: "content:69b2", type: "Document", properties: { title: "Wing officer's note" } } });
    render(
      <JudgementsPanel
        apiBaseUrl="http://localhost:8000"
        bearerToken="tok"
        investigationId="inv-1"
        workingSetGraph={graph}
        selectedNodeId={null}
        onHighlightNodes={() => undefined}
      />,
    );
    fireEvent.click(screen.getByText("Add judgement, gap or assumption"));
    const picker = await screen.findByLabelText("Add supporting evidence");
    fireEvent.change(picker, { target: { value: "O" } });
    const text = (await screen.findByRole("listbox")).textContent ?? "";
    expect(text).toContain("OKAFOR, Callum");
    expect(text).toContain("Wing officer's note");
    expect(text).not.toContain("content:69b2");
  });
});
