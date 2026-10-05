import { describe, expect, it } from "vitest";

import type { EdgeTypeDef } from "../../../../packages/schemas/generated";
import { emptyTypeDraft, toProposal, typeIdFrom } from "./defineType";

const TYPES = [{ name: "ASSOCIATE_OF" }, { name: "USES" }] as EdgeTypeDef[];

describe("typeIdFrom", () => {
  it("makes the ID from the display name, in capitals with single underscores", () => {
    expect(typeIdFrom("Known to")).toBe("KNOWN_TO");
    expect(typeIdFrom("  works  with -- staff of ")).toBe("WORKS_WITH_STAFF_OF");
    expect(typeIdFrom("Met in 2024")).toBe("MET_IN_2024");
    expect(typeIdFrom("Café owner")).toBe("CAFE_OWNER");
  });
});

describe("toProposal", () => {
  const ready = { ...emptyTypeDraft("Person", "Person"), label: "Known to", id: "KNOWN_TO", reason: "By sight" };

  it("is the request, with the ends from the link and the ID the server will check", () => {
    const outcome = toProposal(ready, TYPES);
    expect(outcome).toEqual({
      kind: "proposal",
      input: { name: "KNOWN_TO", label: "Known to", from_types: ["Person"], to_types: ["Person"], directed: true, reason: "By sight" },
    });
  });

  it("goes either way round, when asked, between two kinds of entity", () => {
    const draft = { ...emptyTypeDraft("Person", "Organisation"), label: "Known to", id: "KNOWN_TO", reason: "r", eitherWay: true };
    const outcome = toProposal(draft, TYPES);
    expect(outcome.kind === "proposal" && outcome.input).toMatchObject({
      from_types: ["Organisation", "Person"],
      to_types: ["Organisation", "Person"],
      directed: false,
    });
  });

  it("sends a colour and a thickness only when chosen", () => {
    const outcome = toProposal({ ...ready, colour: "jade", thickness: "3" }, TYPES);
    expect(outcome.kind === "proposal" && outcome.input).toMatchObject({ colour: "jade", thickness: 3 });
  });

  it.each([
    [{ label: "" }, "Give the type a name"],
    [{ id: "Known to" }, "capital letters"],
    [{ id: "KNOWN__TO" }, "capital letters"],
    [{ id: "ASSOCIATE_OF" }, "already a type"],
    [{ reason: " " }, "Say why"],
  ])("says what is wrong rather than asking the server: %o", (change, words) => {
    const outcome = toProposal({ ...ready, ...change }, TYPES);
    expect(outcome.kind).toBe("problem");
    expect(outcome.kind === "problem" && outcome.message).toContain(words);
  });
});
