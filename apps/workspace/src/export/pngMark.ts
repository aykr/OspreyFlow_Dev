// Embedding/reading the Osprey mark as PNG `tEXt` chunks — Phase 8 Stage 4h, `02_GLASS_FRONTEND.md`
// §10.3 ("a chart gets a visible footer/watermark plus embedded machine-readable image metadata
// carrying the same fields"). A small, self-contained chunk writer/reader rather than a new
// dependency — PNG chunk framing (4-byte length, 4-byte type, data, 4-byte CRC32) is simple enough
// that pulling in a library for it would cost more than it saves, the same "no new dependency
// unless genuinely needed" call `tests/scenarios/fixtures/fixture_corp.py`'s own AMLSim/
// gen-fraud-graph finding already made for this project.
//
// One `tEXt` chunk per mark field, inserted immediately after the PNG's own `IHDR` chunk — valid
// per the PNG spec (ancillary chunks may appear anywhere between `IHDR` and `IEND`), and simpler to
// locate deterministically than "anywhere before IEND" would be.

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

/** The CRC32 table PNG's own spec (Annex D) defines — a fixed, small lookup table, not a library
 * dependency. */
function buildCrcTable(): Uint32Array {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
}
const CRC_TABLE = buildCrcTable();

function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    // `bytes[i]` is always in bounds here (the loop guard is `i < bytes.length`), and
    // `CRC_TABLE` is a fixed 256-entry table indexed by a byte masked with `& 0xff` — the
    // non-null assertions below only satisfy `noUncheckedIndexedAccess`, they do not change
    // behaviour.
    c = CRC_TABLE[(c ^ bytes[i]!) & 0xff]! ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function u32be(n: number): Uint8Array {
  return new Uint8Array([(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff]);
}

function readU32be(bytes: Uint8Array, offset: number): number {
  // Every call site keeps `offset + 3` within `bytes.length` by construction (the PNG chunk
  // walk in `readPngTextChunks` never reads past a chunk boundary it has already checked) — the
  // non-null assertions below only satisfy `noUncheckedIndexedAccess`.
  return (
    ((bytes[offset]! << 24) | (bytes[offset + 1]! << 16) | (bytes[offset + 2]! << 8) | bytes[offset + 3]!) >>>
    0
  );
}

function concat(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((sum, c) => sum + c.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

function isValidPngSignature(bytes: Uint8Array): boolean {
  if (bytes.length < 8) return false;
  return PNG_SIGNATURE.every((b, i) => bytes[i] === b);
}

function buildTextChunk(keyword: string, text: string): Uint8Array {
  const type = new TextEncoder().encode("tEXt");
  const data = new TextEncoder().encode(`${keyword}\0${text}`);
  const typeAndData = concat([type, data]);
  const crc = u32be(crc32(typeAndData));
  return concat([u32be(data.length), type, data, crc]);
}

/** Inserts one `tEXt` chunk per `fields` entry immediately after `IHDR`. Throws if `pngBytes`
 * does not start with a real PNG signature — this function never silently produces a file that
 * merely *looks* like a PNG (`CLAUDE.md`'s own "fail loudly, never dropped silently" posture,
 * applied here to a malformed-input case rather than a network one). */
export function embedPngTextChunks(pngBytes: Uint8Array, fields: Record<string, string>): Uint8Array {
  if (!isValidPngSignature(pngBytes)) {
    throw new Error("embedPngTextChunks: input is not a valid PNG (bad signature)");
  }
  // IHDR is always the first chunk, always 13 bytes of data: length(4) + type(4) + data(13) + crc(4).
  const ihdrEnd = 8 + 4 + 4 + 13 + 4;
  const before = pngBytes.slice(0, ihdrEnd);
  const after = pngBytes.slice(ihdrEnd);
  const textChunks = Object.entries(fields).map(([k, v]) => buildTextChunk(k, v));
  return concat([before, ...textChunks, after]);
}

/** Reads every `tEXt` chunk's own keyword/text pair back out — the companion `embedPngTextChunks`
 * needs for a round-trip test, and the same shape a recipient's own verifier would use to confirm
 * the mark is actually present and readable, not merely written. */
export function readPngTextChunks(pngBytes: Uint8Array): Record<string, string> {
  if (!isValidPngSignature(pngBytes)) {
    throw new Error("readPngTextChunks: input is not a valid PNG (bad signature)");
  }
  const result: Record<string, string> = {};
  let offset = 8;
  while (offset < pngBytes.length) {
    const length = readU32be(pngBytes, offset);
    const type = new TextDecoder().decode(pngBytes.slice(offset + 4, offset + 8));
    const data = pngBytes.slice(offset + 8, offset + 8 + length);
    if (type === "tEXt") {
      const nul = data.indexOf(0);
      const keyword = new TextDecoder().decode(data.slice(0, nul));
      const text = new TextDecoder().decode(data.slice(nul + 1));
      result[keyword] = text;
    }
    offset += 4 + 4 + length + 4; // length + type + data + crc
    if (type === "IEND") break;
  }
  return result;
}
