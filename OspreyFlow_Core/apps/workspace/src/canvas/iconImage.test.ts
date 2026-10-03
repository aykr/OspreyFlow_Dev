import { describe, expect, it } from "vitest";

import { MAX_PICTURE_BYTES, checkPictureFile, squareCrop } from "./iconImage";

// ADR-079. A picture the analyst gives for a type is cut to a square and drawn small, so only a
// small raster is taken, and the page does the cutting; the file itself never leaves the browser.

describe("which files are taken as a picture", () => {
  it("takes png, jpeg, webp and gif up to the size limit", () => {
    for (const type of ["image/png", "image/jpeg", "image/webp", "image/gif"]) {
      expect(checkPictureFile({ type, size: 1000 })).toBeNull();
    }
    expect(checkPictureFile({ type: "image/png", size: MAX_PICTURE_BYTES })).toBeNull();
  });

  it("refuses an SVG (it can carry scripts and links), a document and a file of no type", () => {
    for (const type of ["image/svg+xml", "application/pdf", "text/html", ""]) {
      expect(checkPictureFile({ type, size: 1000 })).toMatch(/png, jpeg, webp or gif/);
    }
  });

  it("refuses a file over the limit, and an empty one", () => {
    expect(checkPictureFile({ type: "image/png", size: MAX_PICTURE_BYTES + 1 })).toMatch(/too large/);
    expect(checkPictureFile({ type: "image/png", size: 0 })).toMatch(/empty/);
  });
});

describe("cutting a picture to a square", () => {
  it("takes the middle of a wide picture", () => {
    expect(squareCrop(400, 200)).toEqual({ sx: 100, sy: 0, side: 200 });
  });

  it("takes the middle of a tall picture", () => {
    expect(squareCrop(200, 600)).toEqual({ sx: 0, sy: 200, side: 200 });
  });

  it("keeps a square one whole", () => {
    expect(squareCrop(64, 64)).toEqual({ sx: 0, sy: 0, side: 64 });
  });

  it("never gives a side of nothing", () => {
    expect(squareCrop(0, 0).side).toBeGreaterThan(0);
  });
});
