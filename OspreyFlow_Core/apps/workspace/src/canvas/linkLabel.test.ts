// What a person reads for a link (ADR-091): the type's name in sentence case, and the count named
// by what it counts. The owner, 4 October 2026: "COMMUNICATED_WITH (1)" in capitals with a bare
// number in brackets was strange and hard to read.
import { describe, expect, it } from "vitest";

import { linkCaption, linkTypeName } from "./linkLabel";

describe("linkTypeName", () => {
  it("uses the label the ontology declares", () => {
    expect(linkTypeName("COMMUNICATED_WITH", [{ name: "COMMUNICATED_WITH", label: "Emailed" }])).toBe(
      "Emailed",
    );
  });

  it("derives sentence case from the name when none is declared", () => {
    expect(linkTypeName("COMMUNICATED_WITH", [])).toBe("Communicated with");
    expect(linkTypeName("SAME_AS", [{ name: "SAME_AS" }])).toBe("Same as");
    expect(linkTypeName("USES", [])).toBe("Uses");
  });

  it("ignores a blank declared label", () => {
    expect(linkTypeName("KNOWS", [{ name: "KNOWS", label: "  " }])).toBe("Knows");
  });

  it("never shows a name in capitals", () => {
    expect(linkTypeName("PRESENT_AT", [])).not.toMatch(/[A-Z]{2}/);
  });
});

describe("linkCaption", () => {
  it("names the count by what it counts", () => {
    expect(linkCaption("Communicated with", 3, "emails")).toBe("Communicated with · 3 emails");
    expect(linkCaption("Communicated with", 1, "emails")).toBe("Communicated with · 1 email");
    expect(linkCaption("Owns", 2, "events")).toBe("Owns · 2 records");
    expect(linkCaption("Owns", 1, "events")).toBe("Owns · 1 record");
  });

  it("writes a large count with a thousands separator", () => {
    expect(linkCaption("Communicated with", 12345, "emails")).toBe(
      "Communicated with · 12,345 emails",
    );
  });
});
