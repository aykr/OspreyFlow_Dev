// ADR-140 Amendment 12: the Glass's own step edits build the pipeline the server builds. The fixture
// is `pipeline_with_staging` of the exit recipe's steps (held to it by
// `tests/ingest/test_visits_pipeline_fixture.py`), so a line the Glass draws that the server would
// not, or a record it shapes differently, fails here.
import { describe, expect, it } from "vitest";

import type { PipelineGraph } from "../../../../../packages/schemas/generated";
import FIXTURE from "../../../keyboard/fixtures/visits_and_contacts_pipeline.json";
import { addStagingStep, removeStagingStep, rewireStaging, stepInputs, tablesFor, withStepRecord, type StagingKind } from "./stagingSteps";

const base = FIXTURE.base as PipelineGraph;
const built = FIXTURE.pipeline as PipelineGraph;
const edgeSet = (g: PipelineGraph) => new Set((g.edges ?? []).map((e) => `${e.source}→${e.target}`));

function buildByEdits(): PipelineGraph {
  let graph = base;
  let after: string | null = "visit_bookings";
  for (const step of (built.nodes ?? []).filter((n) => ["lookup", "join", "derive"].includes(n.kind))) {
    const added = addStagingStep(graph, step.kind as StagingKind, after);
    // The drawer names the step and sets its record; ids are the recipe's own here.
    graph = {
      nodes: (added.graph.nodes ?? []).map((n) => (n.id === added.id ? { ...n, id: step.id } : n)),
      edges: (added.graph.edges ?? []).map((e) => ({
        source: e.source === added.id ? step.id : e.source,
        target: e.target === added.id ? step.id : e.target,
      })),
    };
    graph = withStepRecord(graph, step.id, step.config ?? {}, step.label);
    after = step.id;
  }
  return graph;
}

describe("staging steps as pipeline nodes", () => {
  it("builds by the Glass's own edits the pipeline the server builds", () => {
    const graph = buildByEdits();
    expect(edgeSet(graph)).toEqual(edgeSet(built));
    const steps = (g: PipelineGraph) => (g.nodes ?? []).filter((n) => !["domain_model", "source", "map", "load"].includes(n.kind));
    expect(steps(graph)).toEqual(steps(built));
  });

  it("reads a step's tables from its record", () => {
    const join = (built.nodes ?? []).find((n) => n.id === "with_owner")!;
    expect(stepInputs(join)).toEqual(["with_establishment", "number_owners"]);
  });

  it("offers a step only tables not fed by it", () => {
    expect(tablesFor(built, "with_establishment").sort()).toEqual(["number_owners", "visit_bookings"]);
    expect(tablesFor(built, "titled").sort()).toEqual(["number_owners", "visit_bookings", "with_establishment", "with_owner"]);
  });

  it("names a new step by its kind, lower case, as a recipe's step id must be", () => {
    const { graph, id } = addStagingStep(built, "lookup", "titled");
    expect(id).toBe("lookup");
    expect(addStagingStep(graph, "lookup", id).id).toBe("lookup_2");
    expect(edgeSet(graph)).toContain("lookup→map");
    expect(edgeSet(graph)).not.toContain("titled→map");
  });

  it("gives Map back its source when the last step goes", () => {
    let graph = built;
    for (const id of ["titled", "with_owner", "with_establishment"]) graph = removeStagingStep(graph, id);
    expect(edgeSet(graph)).toContain("visit_bookings→map");
    expect(edgeSet(rewireStaging(graph))).toEqual(edgeSet(graph));
  });
});
