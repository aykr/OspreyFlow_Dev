// The test that fails if a wildcard edge type goes missing from the radial menu again.
//
// This is the defect that made "Explain cluster" unreachable in a live session for three rounds.
// The ontology declares `SAME_AS`/`NOT_SAME_AS` with `from: ["*"], to: ["*"]`, and the filter
// asked `et.from.includes(node.type)` — false for `["*"]` against any real type name — so the one
// control that could pull resolution edges into the working set never listed them.
//
// Uses the ontology's own real shapes, not invented ones: `SAME_AS` exactly as
// `packages/ontology/default.yaml`'s loader injects it, and `ASSOCIATE_OF` exactly as that file
// declares it. `CLAUDE.md` rule 15 — a planted case has to take the shape the code really
// receives at its own call site, and a hand-written `{from: ["Person"]}` would have passed the
// broken filter too.
import { describe, expect, it } from "vitest";

import type { EdgeTypeDef } from "../../../../packages/schemas/generated";
import { edgeTypesOfferedFor } from "./edgeTypeMenu";

const SAME_AS: EdgeTypeDef = { name: "SAME_AS", from: ["*"], to: ["*"], system: true };
const ASSOCIATE_OF: EdgeTypeDef = {
  name: "ASSOCIATE_OF",
  from: ["Person"],
  to: ["Person"],
};
const USES: EdgeTypeDef = { name: "USES", from: ["Person"], to: ["Device", "Endpoint"] };

describe("edgeTypesOfferedFor", () => {
  it("offers a wildcard edge type on every node type", () => {
    for (const nodeType of ["Person", "Organisation", "Location", "Endpoint"]) {
      expect(
        edgeTypesOfferedFor([SAME_AS], nodeType).map((e) => e.name),
        `SAME_AS is declared from:["*"] to:["*"], so it connects ${nodeType} like anything ` +
          "else — omitting it means an analyst cannot expand resolution edges from the canvas, " +
          "and 'Explain cluster' never appears because the projection has no SAME_AS to collapse",
      ).toEqual(["SAME_AS"]);
    }
  });

  it("still offers a type declared at either end, and not one declared at neither", () => {
    const offered = edgeTypesOfferedFor([ASSOCIATE_OF, USES], "Person").map((e) => e.name);
    expect(offered).toEqual(["ASSOCIATE_OF", "USES"]);

    // `USES` reaches a Device at its `to` end, so it is offered there too; `ASSOCIATE_OF` is
    // Person-to-Person and must not be.
    expect(edgeTypesOfferedFor([ASSOCIATE_OF, USES], "Device").map((e) => e.name)).toEqual([
      "USES",
    ]);
  });

  it("does not offer an edge type unrelated to the node at either end", () => {
    expect(edgeTypesOfferedFor([ASSOCIATE_OF], "Location")).toEqual([]);
  });
});
