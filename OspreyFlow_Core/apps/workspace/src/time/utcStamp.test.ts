import { describe, expect, it } from "vitest";

import { utcStamp, utcStampOf } from "./utcStamp";

describe("utcStamp", () => {
  it("writes a moment as day, month, year and UTC time, whatever the engine's own month names", () => {
    expect(utcStamp(new Date("2026-09-05T08:07:00Z"))).toBe("5 Sep 2026 08:07 UTC");
    expect(utcStamp(new Date("2026-10-24T09:05:00Z"))).toBe("24 Oct 2026 09:05 UTC");
  });

  it("writes an ISO moment the same way, and leaves what is not a date as it was sent", () => {
    expect(utcStampOf("2026-10-24T09:05:00Z")).toBe("24 Oct 2026 09:05 UTC");
    expect(utcStampOf("not a date")).toBe("not a date");
  });
});
