// A 0-byte file was listed as "1 KB" — `Math.max(1, …)` floored every size at
// a kilobyte, so the empty or tiny file an engineer most needs to notice read
// as an ordinary one (found 9 October 2026).
import { describe, expect, it } from "vitest";

import { describeFileSize } from "./fileSize";

describe("describeFileSize", () => {
  it("says an empty file is empty, never 1 KB", () => {
    expect(describeFileSize(0)).toBe("empty");
  });

  it("gives bytes below a kilobyte, never rounding up to 1 KB", () => {
    expect(describeFileSize(1)).toBe("1 byte");
    expect(describeFileSize(512)).toBe("512 bytes");
    expect(describeFileSize(1023)).toBe("1,023 bytes");
  });

  it("gives whole kilobytes from 1 KB", () => {
    expect(describeFileSize(1024)).toBe("1 KB");
    expect(describeFileSize(1536)).toBe("2 KB");
    expect(describeFileSize(345_678)).toBe("338 KB");
  });

  it("gives megabytes to one decimal from 1 MB", () => {
    expect(describeFileSize(1_048_576)).toBe("1.0 MB");
    expect(describeFileSize(5_662_310)).toBe("5.4 MB");
  });
});
