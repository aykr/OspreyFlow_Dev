// WCAG 2's contrast ratio, for the map's own colour choices (`style.ts`'s `landAndWater`) and the
// three themes' contrast check (`map-verify/showcase.tsx`): one arithmetic for both.

/** The relative luminance of a "#rrggbb" or "rgb(r, g, b)" colour (WCAG 2). */
export function luminance(colour: string): number {
  const parts = colour.startsWith("#")
    ? [1, 3, 5].map((i) => parseInt(colour.slice(i, i + 2), 16))
    : (colour.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
  const [r, g, b] = parts.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The ratio of the lighter colour's luminance to the darker's, each plus 0.05, unrounded: a floor
 * is compared with the exact ratio, so 4.495 never passes 4.5. Opaque colours only (the map's are);
 * an alpha channel is refused rather than read as opaque. */
export function contrastRatio(a: string, b: string): number {
  for (const colour of [a, b]) {
    if (/^rgba\(|^#[0-9a-f]{8}$/i.test(colour) && !/,\s*1\)$/.test(colour)) {
      throw new Error(`contrastRatio takes opaque colours only, not ${colour}`);
    }
  }
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** WCAG 1.4.11: a graphic's parts needed to understand it, against what is next to them. */
export const NON_TEXT_FLOOR = 3;
