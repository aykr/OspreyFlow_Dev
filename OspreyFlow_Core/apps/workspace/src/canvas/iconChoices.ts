// Which icon is drawn inside the shape of each type of node (ADR-079).
//
// The ontology gives each entity type a default (`EntityTypeDef.icon`). The analyst may choose, for
// a type, another of the built-in drawings, no icon at all, or a small picture of their own. The
// choice is a way of looking, so, like the label choice (ADR-076) and the theme (ADR-070), it is kept
// in this browser only, never sent to the server and not part of the case. The canvas cannot read it
// from a component's state, so it is a small store the canvas listens to.
import { glyphMarkup, hasGlyph } from "../color/nodeGlyphs";
import { isSafeImageDataUrl, type NodeIcon } from "../color/nodeVisual";
import { readableTextOn } from "../color/oklab";

export const ICON_CHOICES_KEY = "ospreyflow.node-icons";

/** What the analyst chose for a type. A type with no entry has no choice: the ontology's applies. */
export type IconChoice =
  | { kind: "glyph"; name: string }
  | { kind: "none" }
  | { kind: "image"; dataUrl: string };

export type IconChoices = Readonly<Record<string, IconChoice>>;

function validChoice(value: unknown): IconChoice | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  if (record["kind"] === "none") return { kind: "none" };
  if (record["kind"] === "glyph" && typeof record["name"] === "string" && hasGlyph(record["name"])) {
    return { kind: "glyph", name: record["name"] };
  }
  if (record["kind"] === "image" && isSafeImageDataUrl(record["dataUrl"])) {
    return { kind: "image", dataUrl: record["dataUrl"] };
  }
  return null;
}

function parse(raw: string | null): IconChoices {
  if (raw === null) return {};
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
    const out: Record<string, IconChoice> = {};
    for (const [type, entry] of Object.entries(value)) {
      const choice = validChoice(entry);
      if (choice !== null) out[type] = choice;
    }
    return out;
  } catch {
    return {};
  }
}

let cache: IconChoices | null = null;
const listeners = new Set<() => void>();
// A picture's cache key: assigned once when it is set or read, so the long text is never hashed per
// node per redraw, and a new picture is always a new key.
const imageKeys = new Map<string, string>();
let imageCounter = 0;

function imageKeyFor(dataUrl: string): string {
  let key = imageKeys.get(dataUrl);
  if (key === undefined) {
    imageCounter += 1;
    key = `${imageCounter}:${dataUrl.length}`;
    imageKeys.set(dataUrl, key);
  }
  return key;
}

function load(): IconChoices {
  if (cache === null) {
    try {
      cache = parse(localStorage.getItem(ICON_CHOICES_KEY));
    } catch {
      // A private window or blocked site data: the choice then lasts for this page only.
      cache = {};
    }
  }
  return cache;
}

export function getIconChoices(): IconChoices {
  return load();
}

function same(a: IconChoice | undefined, b: IconChoice | null): boolean {
  if (a === undefined || b === null) return a === undefined && b === null;
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Chooses what `entityType` is drawn with, or, with `null`, goes back to the ontology's. A choice
 * that is not a listed drawing or a small raster picture is refused. Returns whether the choice was
 * kept in this browser's storage: it still holds for this page when it was not (a full or blocked
 * store), and the caller says so. */
export function setIconChoice(entityType: string, choice: IconChoice | null): boolean {
  const wanted = choice === null ? null : validChoice(choice);
  if (choice !== null && wanted === null) return false;
  const before = load();
  if (same(before[entityType], wanted)) return true;
  const next: Record<string, IconChoice> = { ...before };
  if (wanted === null) delete next[entityType];
  else next[entityType] = wanted;
  cache = next;
  let kept = true;
  try {
    localStorage.setItem(ICON_CHOICES_KEY, JSON.stringify(next));
  } catch {
    kept = false;
  }
  listeners.forEach((listener) => listener());
  return kept;
}

export function onIconChoicesChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Forgets what was read, so the next read comes from storage again. For tests. */
export function forgetIconChoicesForTest(): void {
  cache = null;
  listeners.clear();
  imageKeys.clear();
}

/** The icon to draw inside a node of `entityType`: the analyst's choice for the type, else the
 * ontology's `ontologyIcon`, else none. A glyph is drawn in whichever of white and near-black reads
 * better on `fillHex`. */
export function resolveNodeIcon(
  entityType: string,
  ontologyIcon: string | null | undefined,
  fillHex: string,
): NodeIcon | null {
  const choice = load()[entityType];
  if (choice?.kind === "none") return null;
  if (choice?.kind === "image") {
    return { kind: "image", key: `${entityType}:${imageKeyFor(choice.dataUrl)}`, dataUrl: choice.dataUrl };
  }
  const name = choice?.kind === "glyph" ? choice.name : ontologyIcon;
  if (typeof name !== "string" || glyphMarkup(name, fillHex) === null) return null;
  return { kind: "glyph", name, colourHex: readableTextOn(fillHex) };
}
