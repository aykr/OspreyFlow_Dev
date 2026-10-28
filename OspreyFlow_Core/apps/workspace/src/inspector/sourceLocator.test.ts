// ADR-131: a source row is stored as its offset under the header (`row 0` is the first data row),
// and a person reads it counted from 1.
import { describe, expect, it } from "vitest";

import { locatorText, rowNumber } from "./sourceLocator";

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
