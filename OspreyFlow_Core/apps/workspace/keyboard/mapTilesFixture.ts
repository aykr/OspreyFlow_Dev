// A synthetic vector PMTiles archive for `map-tiles.spec.ts` (slice GG6): a few invented shapes, no map
// data of any kind (rule 9). It exists because nothing offline proved that the Map view draws tiles
// read through the `pmtiles://` protocol: `map-view-harness.tsx`'s raster provider never delivers a tile
// and `live/basemap.spec.ts` needs a live stack.
//
// The committed bytes (`fixtures/map-tiles.pmtiles`) are this script's output, and `map-tiles.spec.ts`
// fails if they differ. Regenerate with, from `apps/workspace`:
//     node keyboard/mapTilesFixture.ts --write
//
// What is in it: the 3 x 3 zoom-14 tiles around the harness's three yards (a prison's yards a few
// hundred metres apart), each holding the same three invented shapes in the OpenMapTiles layer names
// the bundled style reads (`style.ts`): a rectangle of `water`, a rectangle of `landcover` and a
// `transportation` line. They are placed so that, at the harness's camera, one shape is under each
// of a few sample points the spec reads back from the canvas (`SAMPLES`).
//
// Written to the PMTiles version 3 layout (https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md):
// uncompressed tiles and directory (a valid choice, and byte-for-byte reproducible whatever zlib is
// installed), one root directory, no leaf directories.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { zxyToTileId } from "pmtiles";

export const FIXTURE_FILE = new URL("./fixtures/map-tiles.pmtiles", import.meta.url);

/** The zoom the archive holds; the map draws zoom 15 and above from it (over-zoomed). */
export const TILE_ZOOM = 14;
const EXTENT = 4096;
const CENTRE = { lon: -1.14905, lat: 51.43025 };

type LonLat = [number, number];
interface Shape {
  layer: "water" | "landcover" | "transportation";
  type: "polygon" | "line";
  /** A closed ring (first point not repeated) or the points of a line. */
  points: LonLat[];
}

const rectangle = (west: number, south: number, east: number, north: number): LonLat[] => [
  [west, north],
  [east, north],
  [east, south],
  [west, south],
];

/** Invented shapes: water to the south-east of the yards, land cover to the north-west, a road across. */
export const SHAPES: Shape[] = [
  { layer: "water", type: "polygon", points: rectangle(-1.1495, 51.4270, -1.1400, 51.4299) },
  { layer: "landcover", type: "polygon", points: rectangle(-1.1560, 51.4302, -1.1485, 51.4340) },
  {
    layer: "transportation",
    type: "line",
    points: [
      [-1.1560, 51.4300],
      [-1.1400, 51.4300],
    ],
  },
];

/** Where the spec reads the canvas back: inside the water, inside the land cover, and on neither. */
export const SAMPLES = {
  water: { lon: -1.1478, lat: 51.4296 } as const,
  landcover: { lon: -1.1500, lat: 51.43035 } as const,
  bare: { lon: -1.1482, lat: 51.43085 } as const,
};

function tileOf(lon: number, lat: number, z: number): { x: number; y: number } {
  const n = 2 ** z;
  const rad = (lat * Math.PI) / 180;
  return {
    x: Math.floor(((lon + 180) / 360) * n),
    y: Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n),
  };
}

/** A position in a tile's own 0..4096 coordinates (the tile's x and y given), rounded to whole units. */
function toTile(lon: number, lat: number, z: number, tx: number, ty: number): [number, number] {
  const n = 2 ** z;
  const rad = (lat * Math.PI) / 180;
  const wx = ((lon + 180) / 360) * n;
  const wy = ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n;
  return [Math.round((wx - tx) * EXTENT), Math.round((wy - ty) * EXTENT)];
}

// ---- Mapbox Vector Tile 2.1 (protobuf), written by hand: the few fields used.
const varint = (value: number): number[] => {
  const out: number[] = [];
  let v = value;
  while (v > 0x7f) {
    out.push((v & 0x7f) | 0x80);
    v = Math.floor(v / 128);
  }
  out.push(v);
  return out;
};
const key = (field: number, wire: number): number[] => varint((field << 3) | wire);
const text = (s: string): number[] => [...new TextEncoder().encode(s)];
const field = (num: number, bytes: number[]): number[] => [...key(num, 2), ...varint(bytes.length), ...bytes];
const zigzag = (v: number): number => (v << 1) ^ (v >> 31);

function geometry(shape: Shape, project: (p: LonLat) => [number, number]): number[] {
  const points = shape.points.map(project);
  const first = points[0]!;
  const commands: number[] = [(1 & 7) | (1 << 3), zigzag(first[0]), zigzag(first[1])]; // MoveTo(1)
  commands.push((2 & 7) | ((points.length - 1) << 3)); // LineTo(n)
  let [px, py] = first;
  for (const [x, y] of points.slice(1)) {
    commands.push(zigzag(x - px), zigzag(y - py));
    [px, py] = [x, y];
  }
  if (shape.type === "polygon") commands.push((7 & 7) | (1 << 3)); // ClosePath
  return commands;
}

function tileBytes(tx: number, ty: number): Uint8Array {
  const out: number[] = [];
  for (const layer of ["water", "landcover", "transportation"] as const) {
    const features = SHAPES.filter((s) => s.layer === layer).map((shape) => {
      const geom = geometry(shape, ([lon, lat]) => toTile(lon, lat, TILE_ZOOM, tx, ty));
      // Feature: type (field 3: 2 = line, 3 = polygon) and geometry (field 4, packed).
      const body = [...key(3, 0), ...varint(shape.type === "polygon" ? 3 : 2), ...field(4, geom.flatMap(varint))];
      return field(2, body);
    });
    // Layer: name (1), features (2), extent (5), version (15, which is 2).
    out.push(...field(3, [...field(1, text(layer)), ...features.flat(), ...key(5, 0), ...varint(EXTENT), ...key(15, 0), ...varint(2)]));
  }
  return Uint8Array.from(out);
}

function u64(view: DataView, at: number, value: number): void {
  view.setUint32(at, value % 2 ** 32, true);
  view.setUint32(at + 4, Math.floor(value / 2 ** 32), true);
}

/** The whole archive, as PMTiles v3 bytes. The same on every run. */
export function buildMapTilesFixture(): Uint8Array {
  const centre = tileOf(CENTRE.lon, CENTRE.lat, TILE_ZOOM);
  const tiles: { id: number; data: Uint8Array }[] = [];
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      tiles.push({ id: zxyToTileId(TILE_ZOOM, centre.x + dx, centre.y + dy), data: tileBytes(centre.x + dx, centre.y + dy) });
    }
  }
  tiles.sort((a, b) => a.id - b.id);

  // Root directory: entry count, tile id deltas, run lengths, lengths, offsets (0 = follows the last).
  const dir: number[] = [...varint(tiles.length)];
  let last = 0;
  for (const t of tiles) {
    dir.push(...varint(t.id - last));
    last = t.id;
  }
  for (let i = 0; i < tiles.length; i++) dir.push(...varint(1));
  for (const t of tiles) dir.push(...varint(t.data.length));
  let offset = 0;
  tiles.forEach((t, i) => {
    dir.push(...varint(i === 0 ? 1 + offset : 0));
    offset += t.data.length;
  });
  const directory = Uint8Array.from(dir);

  const metadata = new TextEncoder().encode(
    JSON.stringify({
      name: "GG6 synthetic tiles",
      description: "Invented shapes for map-tiles.spec.ts. Not map data.",
      vector_layers: ["water", "landcover", "transportation"].map((id) => ({ id, fields: {}, minzoom: 0, maxzoom: TILE_ZOOM })),
    }),
  );

  const HEADER = 127;
  const tileData = Uint8Array.from(tiles.flatMap((t) => [...t.data]));
  const rootOffset = HEADER;
  const metadataOffset = rootOffset + directory.length;
  const tileOffset = metadataOffset + metadata.length;
  const file = new Uint8Array(tileOffset + tileData.length);
  const view = new DataView(file.buffer);
  file.set(text("PMTiles"), 0);
  view.setUint8(7, 3);
  u64(view, 8, rootOffset);
  u64(view, 16, directory.length);
  u64(view, 24, metadataOffset);
  u64(view, 32, metadata.length);
  u64(view, 40, 0); // no leaf directories
  u64(view, 48, 0);
  u64(view, 56, tileOffset);
  u64(view, 64, tileData.length);
  u64(view, 72, tiles.length);
  u64(view, 80, tiles.length);
  u64(view, 88, tiles.length);
  view.setUint8(96, 1); // clustered
  view.setUint8(97, 1); // internal compression: none
  view.setUint8(98, 1); // tile compression: none
  view.setUint8(99, 1); // tile type: MVT
  view.setUint8(100, TILE_ZOOM);
  view.setUint8(101, TILE_ZOOM);
  // Bounds: the 3 x 3 block's own corners, in degrees times 1e7.
  const west = ((centre.x - 1) / 2 ** TILE_ZOOM) * 360 - 180;
  const east = ((centre.x + 2) / 2 ** TILE_ZOOM) * 360 - 180;
  const lat = (y: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 2 ** TILE_ZOOM))) * 180) / Math.PI;
  view.setInt32(102, Math.round(west * 1e7), true);
  view.setInt32(106, Math.round(lat(centre.y + 2) * 1e7), true);
  view.setInt32(110, Math.round(east * 1e7), true);
  view.setInt32(114, Math.round(lat(centre.y - 1) * 1e7), true);
  view.setUint8(118, TILE_ZOOM);
  view.setInt32(119, Math.round(CENTRE.lon * 1e7), true);
  view.setInt32(123, Math.round(CENTRE.lat * 1e7), true);
  file.set(directory, rootOffset);
  file.set(metadata, metadataOffset);
  file.set(tileData, tileOffset);
  return file;
}

// `node keyboard/mapTilesFixture.ts --write`
if (process.argv[1] === fileURLToPath(import.meta.url) && process.argv.includes("--write")) {
  writeFileSync(FIXTURE_FILE, buildMapTilesFixture());
  console.log(`wrote ${fileURLToPath(FIXTURE_FILE)}`);
}
