import { describe, expect, it } from "vitest";

import { siteImageUrl } from "./api";

// The other exports here are thin `fetch` wrappers with no logic beyond
// URL construction and error handling — `map/providers.ts`'s own
// `fetchMapConfig` has no dedicated test for the same reason. `siteImageUrl`
// is pure and worth pinning down exactly, since `MapView.tsx`'s
// `transformRequest` matches on this URL's prefix to attach the bearer
// token.
describe("siteImageUrl", () => {
  it("builds the investigation-scoped image proxy path", () => {
    expect(siteImageUrl("http://localhost:8000", "inv-1", "site-1")).toBe(
      "http://localhost:8000/v1/investigations/inv-1/sites/site-1/image",
    );
  });
});
