// The canvas-look comparison's arithmetic (ADR-152 decision 9; slice WS4a), kept apart from the spec so its own red
// cases can run without a browser (`canvasCompare.test.ts`). Node only: it reads the files in `canvas-compare/`.
//
// Two pictures are compared pixel by pixel. A pixel differs when any of its red, green, blue or opacity values differs
// by more than `channel`; the pictures match when the share of differing pixels is at most `share`. That pair is the one pixel
// tolerance decision 9 allows: there is no list of accepted differences, and no scene has a tolerance of its own.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";

import { readPng } from "./pngPixels";

export const FOLDER = new URL("./canvas-compare/", import.meta.url);

/** The most the tolerance may ever be set to: the comparison refuses to run with more (case 5). Set below the
 * smallest share any planted fault gave in its own scene (a dashed link drawn solid: 723 of 540,000 pixels, 0.00134;
 * `process/lanes/v062/away/WS4a_records/plant_compare.log`), so even at the ceiling each of them is red. */
export const CEILING = { channel: 32, share: 0.0005 } as const;

export interface Tolerance {
  channel: number;
  share: number;
}

export interface Comparison {
  width: number;
  height: number;
  differing: number;
  share: number;
}

/** Why `tolerance` may not be used, or null. */
export function toleranceRefusal(tolerance: unknown): string | null {
  const t = tolerance as Partial<Tolerance> | null;
  if (!t || typeof t.channel !== "number" || typeof t.share !== "number" || !Number.isFinite(t.channel) || !Number.isFinite(t.share)) {
    return "the tolerance must give a number for both channel and share";
  }
  if (t.channel < 0 || t.share < 0) return "the tolerance cannot be negative";
  if (t.channel > CEILING.channel || t.share > CEILING.share) {
    return `the tolerance (channel ${t.channel}, share ${t.share}) is above the ceiling (channel ${CEILING.channel}, share ${CEILING.share}): a comparison that loose passes a changed look`;
  }
  return null;
}

export function compare(actual: Buffer, reference: Buffer, channel: number): Comparison {
  const a = readPng(actual);
  const b = readPng(reference);
  if (a.width !== b.width || a.height !== b.height) {
    return { width: a.width, height: a.height, differing: a.width * a.height, share: 1 };
  }
  let differing = 0;
  for (let y = 0; y < a.height; y++) {
    for (let x = 0; x < a.width; x++) {
      const p = a.at(x, y);
      const q = b.at(x, y);
      // Opacity too: the exported PNG is drawn on a transparent ground, where black at 75% (its watermark) changes
      // the alpha alone; read as colour only, every word of it was invisible to the comparison.
      if (
        Math.abs(p[0] - q[0]) > channel ||
        Math.abs(p[1] - q[1]) > channel ||
        Math.abs(p[2] - q[2]) > channel ||
        Math.abs(a.alphaAt(x, y) - b.alphaAt(x, y)) > channel
      ) differing++;
    }
  }
  return { width: a.width, height: a.height, differing, share: differing / (a.width * a.height) };
}

export function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

export interface ReferenceRecord {
  made_at: string;
  made_by: string;
  reason: string;
  commit: string;
  machine: Record<string, string>;
  scenes: Record<string, string>;
}

/** The record the reference-making command writes, or why it cannot be trusted: a reference not in it, or changed
 * since it was made (replaced by hand, not by the command), is refused. `folder` is the committed one, but for the
 * red cases, which plant their faults in a copy of it. */
export function readReferences(scenes: readonly string[], folder: URL = FOLDER): { record: ReferenceRecord | null; problems: string[] } {
  const path = new URL("REFERENCES.json", folder);
  if (!existsSync(path)) return { record: null, problems: ["no canvas-compare/REFERENCES.json: the references are made by `npm run canvas-compare:references -- --reason \"…\"`"] };
  const record = JSON.parse(readFileSync(path, "utf8")) as ReferenceRecord;
  const problems: string[] = [];
  if (!record.reason?.trim()) problems.push("REFERENCES.json gives no reason the references were made");
  for (const scene of scenes) {
    const file = new URL(`${scene}.png`, folder);
    if (!existsSync(file)) problems.push(`no reference for the scene ${scene}`);
    else if (record.scenes?.[scene] !== sha256(readFileSync(file))) {
      problems.push(`the reference for ${scene} is not the one REFERENCES.json records: it was changed without the command`);
    }
  }
  for (const scene of Object.keys(record.scenes ?? {})) {
    if (!scenes.includes(scene)) problems.push(`REFERENCES.json records ${scene}, which is no scene of the comparison`);
  }
  return { record, problems };
}
