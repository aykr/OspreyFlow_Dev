// The canvas-look comparison's own arithmetic, each refusal shown red without a browser (slice WS4a, cases 5 and 6).
// Which test fails if the comparison is loosened (rule 12): a tolerance above the ceiling fails the first block; a
// picture a pixel unlike its reference counted as alike fails the second; a scene with no reference fails the third; a
// reference changed by hand, or a record that cannot be trusted, let through fails the fourth.
import { deflateSync } from "node:zlib";
import { copyFileSync, cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { CEILING, compare, readReferences, sha256, toleranceRefusal } from "./canvasCompare";

/** An 8-bit PNG of `width` by `height`, every pixel `colour` except those `paint` changes: RGB for three values, RGBA
 * for four (the exported PNG's shape). */
function png(width: number, height: number, colour: number[], paint: (x: number, y: number) => number[] | null = () => null): Buffer {
  const channels = colour.length;
  const rows: Buffer[] = [];
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * channels);
    for (let x = 0; x < width; x++) row.set(paint(x, y) ?? colour, 1 + x * channels);
    rows.push(row);
  }
  const chunk = (type: string, body: Buffer) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(body.length, 0);
    head.write(type, 4, "ascii");
    return Buffer.concat([head, body, Buffer.alloc(4)]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = channels === 4 ? 6 : 2;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

describe("the tolerance", () => {
  it("is refused above the ceiling, at 100% and just past it", () => {
    expect(toleranceRefusal({ channel: 16, share: 1 })).toMatch(/above the ceiling/);
    expect(toleranceRefusal({ channel: 255, share: 0 })).toMatch(/above the ceiling/);
    expect(toleranceRefusal({ channel: CEILING.channel, share: CEILING.share + 1e-9 })).toMatch(/above the ceiling/);
  });
  it("is refused when it is not two numbers", () => {
    expect(toleranceRefusal({ channel: 16 })).toMatch(/must give a number/);
    expect(toleranceRefusal(null)).toMatch(/must give a number/);
    expect(toleranceRefusal({ channel: -1, share: 0 })).toMatch(/negative/);
  });
  it("is taken at or below the ceiling", () => {
    expect(toleranceRefusal(CEILING)).toBeNull();
    expect(toleranceRefusal({ channel: 0, share: 0 })).toBeNull();
  });
  it("as committed is within the ceiling", () => {
    const committed = JSON.parse(readFileSync(new URL("./canvas-compare/TOLERANCE.json", import.meta.url), "utf8"));
    expect(toleranceRefusal(committed)).toBeNull();
  });
});

describe("the comparison", () => {
  const ground: [number, number, number] = [20, 24, 30];
  it("finds a picture alike to itself", () => {
    const a = png(40, 30, ground);
    expect(compare(a, a, 0)).toMatchObject({ differing: 0, share: 0 });
  });
  it("counts one pixel unlike, and only one", () => {
    const a = png(40, 30, ground);
    const b = png(40, 30, ground, (x, y) => (x === 7 && y === 9 ? [200, 24, 30] : null));
    expect(compare(a, b, 16)).toMatchObject({ differing: 1, share: 1 / 1200 });
  });
  it("leaves a difference within the channel tolerance alike, and counts one past it", () => {
    const a = png(10, 10, ground);
    expect(compare(a, png(10, 10, [36, 24, 30]), 16).differing).toBe(0);
    expect(compare(a, png(10, 10, [37, 24, 30]), 16).differing).toBe(100);
  });
  it("reads a solid line drawn where a dotted one was as unlike (the shape case 1 plants)", () => {
    const dotted = png(60, 9, ground, (x, y) => (y === 4 && x % 6 < 3 ? [180, 190, 200] : null));
    const solid = png(60, 9, ground, (x, y) => (y === 4 ? [180, 190, 200] : null));
    expect(compare(solid, dotted, 16).differing).toBe(30);
  });
  it("reads a difference in opacity alone (black at 75% on the export's transparent ground, its watermark)", () => {
    const clear = png(20, 10, [0, 0, 0, 0]);
    const marked = png(20, 10, [0, 0, 0, 0], (x, y) => (y === 5 && x < 8 ? [0, 0, 0, 191] : null));
    expect(compare(marked, clear, 16).differing).toBe(8);
  });
  it("finds pictures of different sizes wholly unlike", () => {
    expect(compare(png(10, 10, ground), png(10, 11, ground), 16).share).toBe(1);
  });
});

describe("the references", () => {
  it("are each the one the command recorded", () => {
    const record = JSON.parse(readFileSync(new URL("./canvas-compare/REFERENCES.json", import.meta.url), "utf8"));
    const scenes = Object.keys(record.scenes);
    expect(scenes.length).toBeGreaterThan(0);
    expect(readReferences(scenes).problems).toEqual([]);
  });
  it("are refused when the scene has none, or the record names a scene that is gone", () => {
    const record = JSON.parse(readFileSync(new URL("./canvas-compare/REFERENCES.json", import.meta.url), "utf8"));
    const scenes = Object.keys(record.scenes);
    expect(readReferences([...scenes, "no-such-scene"]).problems).toContain("no reference for the scene no-such-scene");
    expect(readReferences(scenes.slice(1)).problems.join("\n")).toMatch(/which is no scene of the comparison/);
  });
  it("hash the bytes of each picture", () => {
    expect(sha256(Buffer.from("x"))).toBe("2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881");
  });
});

// Each fault is planted in a scratch copy of the committed folder, never in the references themselves. Every case asks
// for the whole list of problems, so no other refusal can stand in for the one it plants.
describe("a reference the command did not write", () => {
  const committed = fileURLToPath(new URL("./canvas-compare/", import.meta.url));
  const scenes = Object.keys(JSON.parse(readFileSync(join(committed, "REFERENCES.json"), "utf8")).scenes);
  const [first, second] = scenes as [string, string];
  const changed = (scene: string) => `the reference for ${scene} is not the one REFERENCES.json records: it was changed without the command`;
  const made: string[] = [];

  afterEach(() => {
    for (const folder of made.splice(0)) rmSync(folder, { recursive: true, force: true });
  });

  /** A copy of the committed folder that `plant` then changes by hand. */
  function copy(plant: (folder: string) => void = () => {}): URL {
    const folder = mkdtempSync(join(tmpdir(), "canvas-compare-"));
    made.push(folder);
    cpSync(committed, folder, { recursive: true });
    plant(folder);
    return pathToFileURL(`${folder}/`);
  }

  function editRecord(folder: string, edit: (record: { reason: string; scenes: Record<string, string> }) => void): void {
    const path = join(folder, "REFERENCES.json");
    const record = JSON.parse(readFileSync(path, "utf8"));
    edit(record);
    writeFileSync(path, JSON.stringify(record));
  }

  it("is not found in a copy nobody has touched (what each case below starts from)", () => {
    expect(readReferences(scenes, copy()).problems).toEqual([]);
  });
  it("is refused when a picture is replaced by another", () => {
    const folder = copy((at) => copyFileSync(join(at, `${second}.png`), join(at, `${first}.png`)));
    expect(readReferences(scenes, folder).problems).toEqual([changed(first)]);
  });
  it("is refused when one byte of a picture changes", () => {
    const folder = copy((at) => {
      const bytes = readFileSync(join(at, `${second}.png`));
      bytes[bytes.length - 1]! ^= 1;
      writeFileSync(join(at, `${second}.png`), bytes);
    });
    expect(readReferences(scenes, folder).problems).toEqual([changed(second)]);
  });
  it("is refused when the hash recorded for a picture is changed", () => {
    const folder = copy((at) => editRecord(at, (record) => { record.scenes[first] = sha256(Buffer.from("x")); }));
    expect(readReferences(scenes, folder).problems).toEqual([changed(first)]);
  });
  it("is refused when the record has no entry for a picture that is there", () => {
    const folder = copy((at) => editRecord(at, (record) => { delete record.scenes[first]; }));
    expect(readReferences(scenes, folder).problems).toEqual([changed(first)]);
  });
  it("is refused when the picture is gone", () => {
    const folder = copy((at) => rmSync(join(at, `${first}.png`)));
    expect(readReferences(scenes, folder).problems).toEqual([`no reference for the scene ${first}`]);
  });
  it("is refused when the record gives no reason", () => {
    const folder = copy((at) => editRecord(at, (record) => { record.reason = "  "; }));
    expect(readReferences(scenes, folder).problems).toEqual(["REFERENCES.json gives no reason the references were made"]);
  });
  it("is refused when there is no record at all", () => {
    const folder = copy((at) => rmSync(join(at, "REFERENCES.json")));
    const answer = readReferences(scenes, folder);
    expect(answer.record).toBeNull();
    expect(answer.problems).toEqual([expect.stringMatching(/^no canvas-compare\/REFERENCES\.json:/)]);
  });
});
