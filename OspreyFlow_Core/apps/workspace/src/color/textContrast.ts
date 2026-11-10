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

/**
 * Every colour a gradient lays over its element, or null when any colour in it cannot be read (so a
 * stop in a form `parseColour` does not know is never dropped). A picture (`url()`) is null too.
 */
export function gradientColours(image: string): Rgba[] | null {
  if (image === "none") return [];
  if (/url\(|image-set\(|element\(|paint\(|cross-fade\(/i.test(image)) return null;
  // Every colour function and the keywords a gradient may carry; anything a colour could be.
  const colours = image.match(/\b(rgba?|color|oklab|oklch|lab|lch|hsla?|hwb)\([^()]*\)|\b(transparent|currentcolor)\b/gi);
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
    const stops = gradientColours(layer.backgroundImage);
    if (!stops) return fail(`a background picture or unread gradient on <${layer.name}>${axe}`);
    const surfaces = [colour, ...stops.map((stop) => over(stop, colour))];
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
  const why = ratio < need ? `${ratio.toFixed(2)}:1 < ${need}:1${axe}` : "";
  return { ...base, ratio, why };
}

/** A finding on main, listed with its owner: excused only while it measures as listed or better. */
export interface ListedFinding {
  /** The text excerpt the node held. */
  text: string;
  /** The ratio measured when listed (a floor: worse fails), or "unmeasurable". */
  ratio: number | "unmeasurable";
  /** For an unmeasurable one: the reason it must still give (e.g. `over or under <canvas`). */
  reason?: string;
  owner: string;
}

/** Whether `finding` is the listed one and no worse. */
export function excuses(listed: ListedFinding | undefined, finding: Judgement): boolean {
  if (!listed || listed.text !== finding.text) return false;
  if (listed.ratio === "unmeasurable") {
    return finding.ratio === null && finding.why.includes(listed.reason ?? "not measurable");
  }
  return finding.ratio !== null && finding.ratio >= listed.ratio - 0.005;
}
