import { describe, expect, it } from "vitest";

import { SOURCES_WITHHELD_TEXT } from "./sourcesWithheld";

describe("sourcesWithheld", () => {
  it("says the words ADR-130 Amendment 2 gives", () => {
    expect(SOURCES_WITHHELD_TEXT).toBe("Its sources are in data this case does not read");
  });
});
