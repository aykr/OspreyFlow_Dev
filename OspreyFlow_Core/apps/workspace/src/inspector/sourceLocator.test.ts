// ADR-131: a source row is stored as its offset under the header (`row 0` is the first data row),
// and a person reads it counted from 1.
import { describe, expect, it } from "vitest";

import { locatorText, rowNumber, sourceName } from "./sourceLocator";

describe("locatorText", () => {
  it("reads the first data row as row 1", () => {
    expect(locatorText("row 0")).toBe("row 1");
  });

  it("adds one to any stored row", () => {
    expect(locatorText("row 2012")).toBe("row 2013");
  });

  it("leaves a locator of any other form as it is", () => {
    for (const other of ["char span 3-9", "msg 3", "p.1", "event:e1", "row 3a", "rows 3", " row 3"]) {
      expect(locatorText(other)).toBe(other);
    }
  });
});

describe("rowNumber", () => {
  it("counts a stored offset from 1", () => {
    expect(rowNumber(0)).toBe(1);
    expect(rowNumber(4)).toBe(5);
  });
});

// Build order step 18c (the 3 November rehearsal's D10): the Inspector showed a source as the
// server's own path, "/var/lib/osprey/ingest/uploaded/prison-intelligence/pid_nomis_cell_shares.csv".
// A source file is named by its file name; the server's folders are not the analyst's business.
describe("sourceName", () => {
  it("names a source file by its file name alone", () => {
    expect(sourceName("/var/lib/osprey/ingest/uploaded/prison-intelligence/pid_nomis_cell_shares.csv")).toBe(
      "pid_nomis_cell_shares.csv",
    );
    expect(sourceName("uploaded\\prison-intelligence\\pid_visits.csv")).toBe("pid_visits.csv");
  });

  it("leaves a source that is not a path as it is stored", () => {
    expect(sourceName("pid-generator:prison-intelligence")).toBe("pid-generator:prison-intelligence");
    expect(sourceName("doc-42")).toBe("doc-42");
  });
});
