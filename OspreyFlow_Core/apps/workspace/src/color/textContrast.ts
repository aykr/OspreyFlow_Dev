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
  /** For each probed point of the text, whether this element's box lies under it: its own surface
   * is under the text there only (a text spilling past its box stands on what is beyond it). */
  covers: boolean[];
}

/**
 * One outer box-shadow near a probed point: its colour as computed, the shape it is cast from (the
 * element's box moved by the offset and grown by the spread: left, top, right, bottom), its blur
 * radius, and the point. The element's own box is never under it (an outer shadow is not painted
 * there, and the element itself is seen at the point instead).
 */
export interface ShadowAt {
  colour: string;
  edges: [number, number, number, number];
  blur: number;
  x: number;
  y: number;
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
  /** For each probed point, the plain SVG shapes lying under an SVG label's words there (its box),
   * nearest first: each shape's fill as a colour (the opacities on its own side of the tree folded
   * in) and `at`, the index in `chain` of the ancestor it shares with the words. It lies under the
   * words' own line of ancestors (`chain[0 … at-1]`) and over that ancestor. Absent or shorter than the points means none. */
  under?: { fill: string; at: number }[][];
  /** The browser's canvas under everything, as computed (`Canvas`); white when absent. */
  page?: string;
  /** For each probed point, the outer box-shadows of other elements near it (`ShadowAt`), each
   * measured by what it paints there. Absent or shorter than the points means none. */
  shadows?: ShadowAt[][];
  /** For each probed point, whether the words are hidden there: under an opaque element laid over
   * them, or clipped by a scrolling box. A hidden point is not judged; hidden at every point, the
   * words are unmeasurable. Absent means none. */
  hidden?: boolean[];
  /** axe's own reason for leaving it undecided (`messageKey`), kept for the message. */
  axeReason: string | null;
}

export interface Judgement {
  selector: string;
  text: string;
  /** The worst ratio over the text's possible backgrounds, or null when unmeasurable. */
  ratio: number | null;
  /** When unmeasurable, the worst ratio on its own surfaces alone (the walk up its tree), if that can
   * be read: a listed unmeasurable finding is pinned to it, so its colours cannot fall unseen. */
  ownRatio: number | null;
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
  // A `none` component or alpha (CSS Color 4's missing component) parses to NaN, and a channel out of
  // its range (rgb(-1000 …)) is no colour Chrome draws as written: both unread, never a pass. A hair
  // outside the range (an out-of-gamut mix rounding) is clamped.
  if (!read || !read.every(Number.isFinite)) return null;
  const [r, g, b, a] = read;
  const near = (v: number, hi: number) => v >= -0.5 && v <= hi + 0.5;
  if (![r, g, b].every((v) => near(v, 255)) || !(a >= -0.001 && a <= 1.001)) return null;
  const clamp = (v: number, hi: number) => Math.max(0, Math.min(hi, v));
  return [clamp(r, 255), clamp(g, 255), clamp(b, 255), clamp(a, 1)];
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
    const l = number(at(0));
    if (!(l >= 0 && l <= 1.001)) return null;
    return [...oklabToRgb(l, number(at(1), 0.4), number(at(2), 0.4)), alpha];
  }
  if (name === "oklch" && parts.length === 3) {
    const [l, c, h] = [number(at(0)), number(at(1), 0.4), parseFloat(at(2))];
    if (!(l >= 0 && l <= 1.001) || !(c >= 0)) return null;
    const rad = (h * Math.PI) / 180;
    return [...oklabToRgb(l, c * Math.cos(rad), c * Math.sin(rad)), alpha];
  }
  return null;
}

const COLOUR = /\b(?:rgba?|color|oklab|oklch|lab|lch|hsla?|hwb)\([^()]*\)|\b(?:transparent|currentcolor)\b/gi;
/** Samples taken between two neighbouring stops, so a smooth gradient's in-between colours count. */
const STEPS = 8;
/** Past this many possible backgrounds, layered gradients are not measured (unmeasurable, not a pass). */
const MAX_SURFACES = 20_000;

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
 * why it cannot be measured: a picture, a stop in an unknown form or with a `none` component, or more
 * possible backgrounds than `MAX_SURFACES`.
 */
export function gradientSurfaces(image: string, base: Rgba): Rgba[] | string {
  if (image === "none") return [base];
  let surfaces: Rgba[] = [base];
  // Painted bottom first: the last layer lies lowest.
  for (const layer of layersOf(image).reverse()) {
    if (layer === "none") continue;
    if (!/^(?:repeating-)?(?:linear|radial|conic)-gradient\(/i.test(layer)) return "a background picture";
    const stops = (layer.match(COLOUR) ?? []).map(parseColour);
    if (!stops.length || stops.some((c) => c === null)) return "an unread gradient";
    const read = stops as Rgba[];
    // A layer may leave part of the box unpainted (its size, position or repeat), so the colour
    // beneath it is a sample too.
    const samples: Rgba[] = [[0, 0, 0, 0], ...read];
    for (let i = 0; i + 1 < read.length; i += 1) {
      for (let k = 1; k < STEPS; k += 1) samples.push(lerp(read[i] as Rgba, read[i + 1] as Rgba, k / STEPS));
    }
    // Counted before the product is built, so a spread past the cap is refused, never built.
    if (surfaces.length * samples.length > MAX_SURFACES) return `more than ${MAX_SURFACES} possible backgrounds`;
    surfaces = surfaces.flatMap((under) => samples.map((top) => over(top, under)));
  }
  return surfaces;
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
 * The worst ratio of the text on its own surfaces: the walk up its tree, at each probed point only
 * through the elements whose box is under that point, each gradient's every colour, and each
 * ancestor's opacity on its whole group. A string when that walk cannot be read (why).
 */
function onOwnSurfaces(sample: Sample, fg: Rgba): number | string | null {
  const points = Math.max(1, ...sample.chain.map((l) => l.covers.length), sample.under?.length ?? 0);
  const page: Rgba | null = sample.page === undefined ? [255, 255, 255, 1] : parseColour(sample.page);
  if (!page || page[3] < 1) return `an unread page colour ${sample.page}`;
  let worst = Infinity;
  let shown = 0;
  for (let p = 0; p < points; p += 1) {
    if (sample.hidden?.[p]) continue;
    shown += 1;
    // Each shadow at the point, as the colour it lays there (its alpha times its coverage).
    const cast: Rgba[] = [];
    for (const shadow of sample.shadows?.[p] ?? []) {
      const colour = parseColour(shadow.colour);
      if (!colour) return `an unread shadow colour ${shadow.colour}`;
      const alpha = colour[3] * shadowCoverage(shadow);
      if (alpha > 0) cast.push([colour[0], colour[1], colour[2], alpha]);
    }
    if (cast.length > MAX_SHADOWS) return `more than ${MAX_SHADOWS} shadows at one point`;
    // Where each lies is not read, so each is laid in turn at every place it could be: away (none),
    // over everything there, or under the words' first j elements and over the rest (j from 0, straight
    // under the words, to the chain's length, straight on the page). Every combination is measured and
    // the worst counts.
    // Two places either side of an element that lays nothing at the point (a clear background, full
    // opacity, no shape under it) give one figure, so only the first of each run is laid.
    const bare = (i: number) => {
      const l = sample.chain[i];
      if (!l || parseFloat(l.opacity) !== 1 || (sample.under?.[p] ?? []).some((u) => u.at === i)) return false;
      if (!(l.covers[p] ?? true)) return true;
      const c = parseColour(l.backgroundColor);
      return c !== null && c[3] === 0 && l.backgroundImage === "none";
    };
    const indices = [0, ...sample.chain.map((_, i) => i + 1).filter((j) => !bare(j - 1))];
    const places = indices.length + 2;
    if (places ** cast.length > MAX_PLACEMENTS) return `more than ${MAX_PLACEMENTS} placements of its shadows at one point`;
    for (let combination = 0; combination < places ** cast.length; combination += 1) {
      const place = cast.map((_, i) => Math.floor(combination / places ** i) % places);
      const laid = new Map<number, Rgba[]>();
      cast.forEach((shadow, i) => {
        const at = indices[(place[i] ?? 0) - 2];
        if (at !== undefined) laid.set(at, [...(laid.get(at) ?? []), shadow]);
      });
      const measured = atPoint(sample, fg, page, p, laid, cast.filter((_, i) => place[i] === 1));
      if (typeof measured === "string") return measured;
      worst = Math.min(worst, measured);
    }
  }
  if (shown === 0) return null;
  // Unreachable while `parseColour` refuses non-finite parts; kept as a second line.
  return Number.isFinite(worst) ? worst : `a measure that came out ${worst}`;
}

/** Past this many shadows at one point their placements are not combined. */
const MAX_SHADOWS = 5;
/** Past this many combinations of shadow placements at one point, the words are not measured. */
const MAX_PLACEMENTS = 20_000;

/** The standard normal distribution's CDF (Abramowitz and Stegun 7.1.26, error under 1.5e-7). */
function normalCdf(z: number): number {
  const x = Math.abs(z) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * x);
  const erf = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return z >= 0 ? (1 + erf) / 2 : (1 - erf) / 2;
}

/**
 * The share of a shadow's colour painted at its point, 0 to 1. CSS Backgrounds 3 blurs the shadow's
 * shape by a Gaussian whose standard deviation is half the blur radius; over a rectangle that is the
 * product of one CDF difference per axis, with `SHADOW_MARGIN` laid on for what Chromium paints past it.
 * The shape's rounded corners are taken square, which can only overstate the paint near a corner.
 */
export function shadowCoverage({ edges: [left, top, right, bottom], blur, x, y }: ShadowAt): number {
  if (!(blur > 0)) return x >= left && x <= right && y >= top && y <= bottom ? 1 : 0;
  const sigma = blur / 2;
  // Past three standard deviations from the shape the browser half sends nothing, and nothing is laid.
  const far = 3 * sigma;
  if (x < left - far || x > right + far || y < top - far || y > bottom + far) return 0;
  const across = (v: number, lo: number, hi: number) => normalCdf((hi - v) / sigma) - normalCdf((lo - v) / sigma);
  return Math.min(1, Math.max(0, across(x, left, right)) * Math.max(0, across(y, top, bottom)) + SHADOW_MARGIN);
}

/**
 * Laid on every blurred shadow's coverage within its reach: Chromium's own blur, read from its pixels on
 * the test server (rules-b's T3b red record, the review round), comes to at most 0.0136 of the colour
 * more than the Gaussian of half the blur anywhere from inside the shape to twice the blur past it.
 */
const SHADOW_MARGIN = 0.015;

/** The text's worst ratio at point `p` on its own surfaces, with each shadow in `laid` at index j laid
 * under the chain's first j elements (straight on the page past the last), and `above` over everything
 * there. */
function atPoint(sample: Sample, fg: Rgba, page: Rgba, p: number, laid: Map<number, Rgba[]>, above: Rgba[]): number | string {
  let worst = Infinity;
  {
    let pairs: [Rgba, Rgba][] = [[fg, [0, 0, 0, 0]]];
    const lay = (surfaces: Rgba[]): string | null => {
      // Counted before the product is built.
      if (pairs.length * surfaces.length > MAX_SURFACES) return `more than ${MAX_SURFACES} possible backgrounds`;
      pairs = pairs.flatMap(([ink, bg]) => surfaces.map((s): [Rgba, Rgba] => [over(ink, s), over(bg, s)]));
      return null;
    };
    for (const [i, layer] of sample.chain.entries()) {
      for (const shadow of laid.get(i) ?? []) {
        const refused = lay([shadow]);
        if (refused) return refused;
      }
      // A label's shapes lie under its own line of ancestors and over the ancestor they share with it.
      for (const shape of (sample.under?.[p] ?? []).filter((u) => u.at === i)) {
        const colour = parseColour(shape.fill);
        if (!colour) return `an unread shape fill ${shape.fill}`;
        const refused = lay([colour]);
        if (refused) return refused;
      }
      if (layer.filter !== "none" || layer.backdropFilter !== "none" || layer.mixBlendMode !== "normal") {
        return `a filter or blend on <${layer.name}>`;
      }
      if (layer.paintedPseudo) return `a painted ${layer.paintedPseudo} on <${layer.name}>`;
      const colour = parseColour(layer.backgroundColor);
      if (!colour) return `an unread background colour ${layer.backgroundColor} on <${layer.name}>`;
      const painted = gradientSurfaces(layer.backgroundImage, colour);
      if (typeof painted === "string") return `${painted} on <${layer.name}>`;
      const opacity = parseFloat(layer.opacity);
      if (!(opacity >= 0 && opacity <= 1)) return `an unread opacity ${layer.opacity} on <${layer.name}>`;
      // An element whose box is not under this point lays nothing under the text there.
      const refused = lay((layer.covers[p] ?? true) ? painted : [[0, 0, 0, 0]]);
      if (refused) return refused;
      if (opacity < 1) {
        pairs = pairs.map(([ink, bg]) => [
          [ink[0], ink[1], ink[2], ink[3] * opacity],
          [bg[0], bg[1], bg[2], bg[3] * opacity],
        ]);
      }
    }
    for (const shadow of laid.get(sample.chain.length) ?? []) {
      const refused = lay([shadow]);
      if (refused) return refused;
    }
    for (const [ink, bg] of pairs) {
      let [seenInk, seenBg] = [over(ink, page), over(bg, page)];
      for (const shadow of above) [seenInk, seenBg] = [over(shadow, seenInk), over(shadow, seenBg)];
      worst = Math.min(worst, ratioOf(seenInk, seenBg));
    }
  }
  return worst;
}

/**
 * The text's colour on what lies under it. Measured on its own surfaces when nothing else does;
 * unmeasurable, with what its own surfaces give beside it, when anything else might.
 */
export function judge(sample: Sample): Judgement {
  const need = needFor(sample.fontSize, sample.fontWeight);
  const base = { selector: sample.selector, text: sample.text, need };
  const axe = sample.axeReason ? ` (axe: ${sample.axeReason})` : "";
  const fg = sample.unreadable ? null : parseColour(sample.color);
  const own = fg ? onOwnSurfaces(sample, fg) : null;
  const ownRatio = typeof own === "number" ? own : null;
  const fail = (why: string): Judgement => ({ ...base, ratio: null, ownRatio, why: `not measurable: ${why}${axe}` });
  if (sample.unreadable) return fail(sample.unreadable);
  if (sample.overlappedBy) return fail(`over or under ${sample.overlappedBy}`);
  if (!fg) return fail(`an unread colour ${sample.color}`);
  if (typeof own === "string") return fail(own);
  // Hidden at every point (under an opaque element over them, or clipped): never a silent pass, as a
  // probe that excluded every point has measured nothing (the orchestrator's condition on T3b).
  if (own === null) return fail("hidden at every point, under an opaque element over the words or clipped");
  const ratio = own;
  const why = ratio < need ? `${ratio.toFixed(2)}:1 < ${need}:1${axe}` : "";
  return { ...base, ratio, ownRatio: null, why };
}

/** A finding on main, listed with its owner: excused only while it measures as listed or better. */
export type ListedFinding =
  | { /** The text excerpt the node held. */ text: string; /** The ratio when listed: worse fails. */ ratio: number; owner: string }
  | {
      text: string;
      ratio: "unmeasurable";
      /** The exact reason it must still give, as `judge` words it (axe's own reason aside). */
      reason: string;
      /** What its own surfaces gave when listed (a floor: worse fails), or null when they too were
       * unreadable. */
      own: number | null;
      owner: string;
    };

const FLOOR = 0.005;

/** Whether `finding` is the listed one and no worse. */
export function excuses(listed: ListedFinding | undefined, finding: Judgement): boolean {
  if (!listed || listed.text !== finding.text) return false;
  if (listed.ratio === "unmeasurable") {
    const why = finding.why.replace(/ \(axe: [^)]*\)$/, "");
    if (finding.ratio !== null || why !== `not measurable: ${listed.reason}`) return false;
    if (listed.own === null) return finding.ownRatio === null;
    return finding.ownRatio !== null && finding.ownRatio >= listed.own - FLOOR;
  }
  return finding.ratio !== null && finding.ratio >= listed.ratio - FLOOR;
}

/**
 * The listed findings, read from their JSON file and checked for shape, so a mistyped field or a
 * missing reason fails the run naming the entry, never excuses by accident.
 */
export function readFindings(json: unknown): Record<string, Record<string, ListedFinding>> {
  const bad = (where: string, what: string): never => {
    throw new Error(`contrast findings: ${where}: ${what}`);
  };
  if (typeof json !== "object" || json === null || Array.isArray(json)) bad("the file", "not an object of looks");
  const out: Record<string, Record<string, ListedFinding>> = {};
  for (const [title, nodes] of Object.entries(json as Record<string, unknown>)) {
    if (typeof nodes !== "object" || nodes === null || Array.isArray(nodes)) bad(title, "not an object of selectors");
    out[title] = {};
    for (const [selector, entry] of Object.entries(nodes as Record<string, unknown>)) {
      const where = `${title} › ${selector}`;
      const e = entry as Record<string, unknown>;
      if (typeof e !== "object" || e === null) bad(where, "not an object");
      const keys = Object.keys(e).sort().join(",");
      if (typeof e.text !== "string" || typeof e.owner !== "string" || !e.owner) bad(where, "no text or owner");
      if (typeof e.ratio === "number") {
        if (keys !== "owner,ratio,text") bad(where, `unexpected fields ${keys}`);
        if (!(e.ratio > 0 && e.ratio <= 21)) bad(where, `a ratio out of range ${e.ratio}`);
      } else if (e.ratio === "unmeasurable") {
        if (keys !== "own,owner,ratio,reason,text") bad(where, `unexpected fields ${keys}`);
        if (typeof e.reason !== "string" || !e.reason) bad(where, "no reason");
        if (e.own !== null && !(typeof e.own === "number" && e.own > 0 && e.own <= 21)) bad(where, `an own ratio out of range ${String(e.own)}`);
      } else {
        bad(where, `a ratio that is neither a number nor "unmeasurable": ${String(e.ratio)}`);
      }
      (out[title] as Record<string, ListedFinding>)[selector] = e as unknown as ListedFinding;
    }
  }
  return out;
}
