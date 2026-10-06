// OKLab colour mixing — `spec/design/tokens.css`'s dimming contract:
// "State is an oklab mix toward the panel surface: dimmed 32%, filtered
// out 12%" and `.node--dimmed`'s own comment,
// `color-mix(in oklab, <channel> 32%, var(--surface-panel))`.
//
// Implemented in plain JS rather than read via CSS `color-mix` + a real
// DOM element, so this is unit-testable in Node (`vitest`, no jsdom) and
// so the same function bakes a node's fill colour into a generated SVG
// (`nodeVisual.ts`) without needing a browser round-trip per node.
// Björn Ottosson's OKLab conversion matrices (the reference the CSS Color
// Module Level 4 `oklab()` function itself is built on) — linear-sRGB in
// and out directly, without a separate XYZ step.

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

function hexToRgb(hex: string): Rgb {
  const normalised = hex.replace("#", "");
  const full =
    normalised.length === 3
      ? normalised
          .split("")
          .map((c) => c + c)
          .join("")
      : normalised;
  const value = Number.parseInt(full, 16);
  return {
    r: (value >> 16) & 0xff,
    g: (value >> 8) & 0xff,
    b: value & 0xff,
  };
}

function rgbToHex({ r, g, b }: Rgb): string {
  const clamp = (c: number) => Math.max(0, Math.min(255, Math.round(c)));
  return `#${[r, g, b].map((c) => clamp(c).toString(16).padStart(2, "0")).join("")}`;
}

function srgbChannelToLinear(c: number): number {
  const normalised = c / 255;
  return normalised <= 0.04045
    ? normalised / 12.92
    : Math.pow((normalised + 0.055) / 1.055, 2.4);
}

function linearChannelToSrgb(c: number): number {
  const clamped = Math.max(0, Math.min(1, c));
  const v =
    clamped <= 0.0031308 ? clamped * 12.92 : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
  return v * 255;
}

interface Oklab {
  L: number;
  a: number;
  b: number;
}

function linearRgbToOklab(r: number, g: number, b: number): Oklab {
  const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
  const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
  const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;
  const l_ = Math.cbrt(l);
  const m_ = Math.cbrt(m);
  const s_ = Math.cbrt(s);
  return {
    L: 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_,
    a: 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_,
    b: 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_,
  };
}

function oklabToLinearRgb({ L, a, b }: Oklab): Rgb {
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;
  return {
    r: linearChannelToSrgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    g: linearChannelToSrgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    b: linearChannelToSrgb(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  };
}

function toOklab(hex: string): Oklab {
  const { r, g, b } = hexToRgb(hex);
  return linearRgbToOklab(srgbChannelToLinear(r), srgbChannelToLinear(g), srgbChannelToLinear(b));
}

/**
 * `color-mix(in oklab, foreground <foregroundPercent>%, background)` — the
 * exact CSS Color 4 semantics `spec/design/tokens.css` names: the second
 * colour implicitly takes the remaining percentage.
 */
export function mixOklab(foregroundHex: string, backgroundHex: string, foregroundPercent: number): string {
  const t = foregroundPercent / 100;
  const fg = toOklab(foregroundHex);
  const bg = toOklab(backgroundHex);
  const mixed: Oklab = {
    L: fg.L * t + bg.L * (1 - t),
    a: fg.a * t + bg.a * (1 - t),
    b: fg.b * t + bg.b * (1 - t),
  };
  return rgbToHex(oklabToLinearRgb(mixed));
}

/** OKLab lightness of a colour, 0 (black) to 1 (white). */
export function oklabLightness(hex: string): number {
  return toOklab(hex).L;
}

/** The near-black an icon is drawn in on a light fill: DESIGN.md's dark `n1` (ADR-097 step 2). */
const ICON_DARK_HEX = "#101314";

/** White or near-black, whichever reads better drawn on `fillHex` (an icon on a node's fill). Both
 * are DESIGN.md neutrals: the light theme's `n0` and the dark theme's `n1`. */
export function readableTextOn(fillHex: string): "#ffffff" | "#101314" {
  return oklabLightness(fillHex) > (1 + oklabLightness(ICON_DARK_HEX)) / 2 ? ICON_DARK_HEX : "#ffffff";
}
