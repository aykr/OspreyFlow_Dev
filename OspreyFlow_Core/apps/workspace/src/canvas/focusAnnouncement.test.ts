// GDS remediation plan A2: the words a screen reader hears as keyboard focus moves between nodes.
import { describe, expect, it } from "vitest";

import { focusAnnouncement } from "./focusAnnouncement";

describe("the focused node's announcement", () => {
  it("says the name, the type and the links, as the plan's example", () => {
    expect(focusAnnouncement("OKAFOR, Callum", "Person", 12)).toBe("OKAFOR, Callum, Person, 12 links");
  });
  it("says one link, and a large count, in British English", () => {
    expect(focusAnnouncement("+447700900310", "Endpoint", 1)).toBe("+447700900310, Endpoint, 1 link");
    expect(focusAnnouncement("Hub", "Account", 1200)).toBe("Hub, Account, 1,200 links");
  });
  it("falls back to the type when a node has no name to say", () => {
    expect(focusAnnouncement("  ", "Location", 0)).toBe("Location, Location, 0 links");
  });
});
