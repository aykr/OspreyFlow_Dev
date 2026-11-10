// WCAG 1.4.3 for text axe-core leaves undecided (rules-b's T3, 10 November 2026). The browser half
// (`a11y/undecidedContrast.ts`) reads each node's computed styles and what lies under its text; this
// half judges them, in Node, so every rule of it is unit-tested (`textContrast.test.ts`) with the strings
// Chrome produces. It fails closed: anything it cannot read or model is an offender, never a pass.

/** One premultiplied-free colour: r, g, b in 0–255, a in 0–1. */
export type Rgba = [number, number, number, number];

/** What the browser read of the text's element or one of its ancestors, nearest first. */
export interface Layer {
  /** `tag.class`, for the message. */
  name: string;
  backgroundColor: string;
  backgroundImage: string;
  opacity: string;
  filter: string;
  backdropFilter: string;
  mixBlendMode: string;
  /** A `::before`/`::after` that paints (content set and a background), as `::before` etc. */
  paintedPseudo: string | null;
  /** Whether this element's box lies under every probed point of the text; its own surface is
   * under the text only then (an overflowing or positioned text leaves it). */
  covers: boolean;
}

/** What the browser read of one undecided node. */
export interface Sample {
  selector: string;
  /** Why the node could not be read at all (a frame, a shadow root, not found), or null. */
  unreadable: string | null;
  text: string;
  color: string;
  fontSize: string;
  fontWeight: string;
  /** The element itself, then each ancestor up to `<html>`. */
  chain: Layer[];
  /** A painted element under or over the text that is not the node nor an ancestor, or null. */
  overlappedBy: string | null;
  /** The node or an ancestor axe named as covering part of the text: a clip (a truncated name, a
   * cell past its scrolling box, the viewport's edge), or null. The visible part stands on its own
   * surfaces. */
  clippedBy: string | null;
  /** axe's own reason for leaving it undecided (`messageKey`), kept for the message. */
  axeReason: string | null;
}

export interface Judgement {
  selector: string;
  text: string;
  /** The worst ratio over the text's possible backgrounds, or null when unmeasurable. */
  ratio: number | null;
  /** 4.5 or 3. */
  need: number;
  /** Why it fails; empty when it passes. */
  why: string;
}

// ---- colours ----

const SRGB = (c: number) => {
  const v = Math.max(0, Math.min(1, c));
  return (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055) * 255;
};

/** OKLab to sRGB (Björn Ottosson's matrices, which CSS Color 4's `oklab()` is built on). */
function oklabToRgb(l: number, a: number, b: number): [number, number, number] {
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    SRGB(4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_),
    SRGB(-1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_),
    SRGB(-0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_),
  ];
}

function alphaOf(part: string | undefined): number {
  if (part === undefined) return 1;
  return part.endsWith("%") ? parseFloat(part) / 100 : parseFloat(part);
}

function number(part: string, percentOf = 1): number {
  return part.endsWith("%") ? (parseFloat(part) / 100) * percentOf : parseFloat(part);
}

/**
 * A computed colour as Chrome writes it: `rgb()`/`rgba()` (comma or space syntax), `color(srgb …)`,
 * `oklab()`, `oklch()` and the keyword `transparent`. Anything else (`lab()`, `lch()`, `color(display-p3
 * …)`, `currentcolor`) is null, which the caller treats as unmeasurable.
 */
export function parseColour(css: string): Rgba | null {
  const read = parseColourParts(css);
  // A `none` component or alpha (CSS Color 4's missing component) parses to NaN: unread, never a pass.
  return read && read.every(Number.isFinite) ? read : null;
}

function parseColourParts(css: string): Rgba | null {
  const s = css.trim().toLowerCase();
  if (s === "transparent") return [0, 0, 0, 0];
  const fn = s.match(/^([a-z-]+)\((.*)\)$/);
  if (!fn) return null;
  const name = fn[1] ?? "";
  const [main = "", slash] = (fn[2] ?? "").split("/").map((p) => p.trim());
  const parts = main.split(/[\s,]+/).filter(Boolean);
  const at = (i: number) => parts[i] ?? "";
  let alpha = alphaOf(slash);
  if ((name === "rgb" || name === "rgba") && (parts.length === 3 || parts.length === 4)) {
    if (parts.length === 4) alpha = alphaOf(at(3));
    return [number(at(0), 255), number(at(1), 255), number(at(2), 255), alpha];
  }
  if (name === "color" && at(0) === "srgb" && parts.length === 4) {
    return [number(at(1)) * 255, number(at(2)) * 255, number(at(3)) * 255, alpha];
  }
  if (name === "oklab" && parts.length === 3) {
    return [...oklabToRgb(number(at(0)), number(at(1), 0.4), number(at(2), 0.4)), alpha];
  }
  if (name === "oklch" && parts.length === 3) {
    const [l, c, h] = [number(at(0)), number(at(1), 0.4), parseFloat(at(2))];
    const rad = (h * Math.PI) / 180;
    return [...oklabToRgb(l, c * Math.cos(rad), c * Math.sin(rad)), alpha];
  }
  return null;
}

const COLOUR = /\b(?:rgba?|color|oklab|oklch|lab|lch|hsla?|hwb)\([^()]*\)|\b(?:transparent|currentcolor)\b/gi;
/** Samples taken between two neighbouring stops, so a smooth gradient's in-between colours count. */
const STEPS = 8;

function lerp(a: Rgba, b: Rgba, t: number): Rgba {
  // Premultiplied, as browsers interpolate gradients (in sRGB here; Chrome takes oklab for modern
  // syntax, whose in-between colours differ a little: the samples bound them, they do not trace them).
  const alpha = a[3] + (b[3] - a[3]) * t;
  if (alpha === 0) return [0, 0, 0, 0];
  const mix = (i: 0 | 1 | 2) => (a[i] * a[3] + (b[i] * b[3] - a[i] * a[3]) * t) / alpha;
  return [mix(0), mix(1), mix(2), alpha];
}

/** A `background-image`'s top-level layers, split at the commas between them. */
function layersOf(image: string): string[] {
  const layers: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < image.length; i += 1) {
    const c = image[i];
    if (c === "(") depth += 1;
    else if (c === ")") depth -= 1;
    else if (c === "," && depth === 0) {
      layers.push(image.slice(start, i).trim());
      start = i + 1;
    }
  }
  layers.push(image.slice(start).trim());
  return layers;
}

/**
 * Every colour a gradient may lay over its element's own `base`: each layer's stops and the colours
 * between them, every layer composited over the ones beneath it (the canvas grid's lines cross), or
 * null when any part cannot be read (a picture, a stop in an unknown form, a `none` component).
 */
export function gradientSurfaces(image: string, base: Rgba): Rgba[] | null {
  if (image === "none") return [base];
  let surfaces: Rgba[] = [base];
  // Painted bottom first: the last layer lies lowest.
  for (const layer of layersOf(image).reverse()) {
    if (!/^(?:repeating-)?(?:linear|radial|conic)-gradient\(/i.test(layer)) return null;
    const stops = (layer.match(COLOUR) ?? []).map(parseColour);
    if (!stops.length || stops.some((c) => c === null)) return null;
    const read = stops as Rgba[];
    const samples: Rgba[] = [...read];
    for (let i = 0; i + 1 < read.length; i += 1) {
      for (let k = 1; k < STEPS; k += 1) samples.push(lerp(read[i] as Rgba, read[i + 1] as Rgba, k / STEPS));
    }
    surfaces = surfaces.flatMap((under) => samples.map((top) => over(top, under)));
  }
  return surfaces;
}

/** The colours a gradient names, or null when any cannot be read (kept for the unit cases). */
export function gradientColours(image: string): Rgba[] | null {
  if (image === "none") return [];
  if (/url\(|image-set\(|element\(|paint\(|cross-fade\(/i.test(image)) return null;
  const colours = image.match(COLOUR);
  if (!colours) return null;
  const read = colours.map(parseColour);
  return read.some((c) => c === null) ? null : (read as Rgba[]);
}

/** `top` drawn over `under` (source-over), both straight alpha. */
export function over(top: Rgba, under: Rgba): Rgba {
  const a = top[3] + under[3] * (1 - top[3]);
  if (a === 0) return [0, 0, 0, 0];
  const mix = (t: number, u: number) => (t * top[3] + u * under[3] * (1 - top[3])) / a;
  return [mix(top[0], under[0]), mix(top[1], under[1]), mix(top[2], under[2]), a];
}

function luminance([r, g, b]: Rgba): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG 2's contrast ratio between two opaque colours, unrounded. */
export function ratioOf(a: Rgba, b: Rgba): number {
  const [la, lb] = [luminance(a), luminance(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** WCAG's large text: 18pt (24px), or 14pt (14 × 4/3 px) bold. */
export function needFor(fontSize: string, fontWeight: string): number {
  const px = parseFloat(fontSize);
  const bold = parseInt(fontWeight, 10) >= 700;
  return px >= 24 || (bold && px >= (14 * 4) / 3) ? 3 : 4.5;
}

// ---- the judgement ----

/**
 * The text's colour and its background as drawn, over every background it may stand on (a gradient's
 * each colour), with each ancestor's opacity applied to its whole group. The worst ratio counts.
 */
export function judge(sample: Sample): Judgement {
  const need = needFor(sample.fontSize, sample.fontWeight);
  const base = { selector: sample.selector, text: sample.text, need };
  const fail = (why: string): Judgement => ({ ...base, ratio: null, why: `not measurable: ${why}` });
  const axe = sample.axeReason ? ` (axe: ${sample.axeReason})` : "";
  if (sample.unreadable) return fail(sample.unreadable + axe);
  if (sample.overlappedBy) return fail(`over or under ${sample.overlappedBy}${axe}`);
  // axe saw part of the text covered and the probe's points found nothing: measured only when what
  // axe named is the text's own box or an ancestor's (a clip); else fail closed.
  const partly = sample.axeReason === "elmPartiallyObscured" || sample.axeReason === "elmPartiallyObscuring";
  if (partly && !sample.clippedBy) {
    return fail(`partly covered, by axe's reading; the probe found nothing${axe}`);
  }
  const fg = parseColour(sample.color);
  if (!fg) return fail(`an unread colour ${sample.color}${axe}`);
  // [text pixel, background pixel] pairs, one per possible background.
  let pairs: [Rgba, Rgba][] = [[fg, [0, 0, 0, 0]]];
  for (const layer of sample.chain) {
    if (layer.filter !== "none" || layer.backdropFilter !== "none" || layer.mixBlendMode !== "normal") {
      return fail(`a filter or blend on <${layer.name}>${axe}`);
    }
    if (layer.paintedPseudo) return fail(`a painted ${layer.paintedPseudo} on <${layer.name}>${axe}`);
    const colour = parseColour(layer.backgroundColor);
    if (!colour) return fail(`an unread background colour ${layer.backgroundColor} on <${layer.name}>${axe}`);
    const painted = gradientSurfaces(layer.backgroundImage, colour);
    if (!painted) return fail(`a background picture or unread gradient on <${layer.name}>${axe}`);
    // An element whose box is not under the text lays nothing under it.
    const surfaces: Rgba[] = layer.covers ? painted : [[0, 0, 0, 0]];
    pairs = pairs.flatMap(([ink, bg]) => surfaces.map((s): [Rgba, Rgba] => [over(ink, s), over(bg, s)]));
    const opacity = parseFloat(layer.opacity);
    if (!(opacity >= 0 && opacity <= 1)) return fail(`an unread opacity ${layer.opacity} on <${layer.name}>${axe}`);
    if (opacity < 1) {
      pairs = pairs.map(([ink, bg]) => [
        [ink[0], ink[1], ink[2], ink[3] * opacity],
        [bg[0], bg[1], bg[2], bg[3] * opacity],
      ]);
    }
  }
  const page: Rgba = [255, 255, 255, 1];
  const ratio = Math.min(...pairs.map(([ink, bg]) => ratioOf(over(ink, page), over(bg, page))));
  if (!Number.isFinite(ratio)) return fail(`a measure that came out ${ratio}${axe}`);
  const why = ratio < need ? `${ratio.toFixed(2)}:1 < ${need}:1${axe}` : "";
  return { ...base, ratio, why };
}

/** A finding on main, listed with its owner: excused only while it measures as listed or better. */
export type ListedFinding =
  | { /** The text excerpt the node held. */ text: string; /** The ratio when listed: worse fails. */ ratio: number; owner: string }
  | {
      text: string;
      ratio: "unmeasurable";
      /** The exact reason it must still give, as `judge` words it (axe's own reason aside). */
      reason: string;
      owner: string;
    };

/** Whether `finding` is the listed one and no worse. */
export function excuses(listed: ListedFinding | undefined, finding: Judgement): boolean {
  if (!listed || listed.text !== finding.text) return false;
  if (listed.ratio === "unmeasurable") {
    const why = finding.why.replace(/ \(axe: [^)]*\)$/, "");
    return finding.ratio === null && why === `not measurable: ${listed.reason}`;
  }
  return finding.ratio !== null && finding.ratio >= listed.ratio - 0.005;
}
