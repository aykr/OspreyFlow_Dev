// WCAG 1.4.3 where axe-core cannot decide it, shared by every axe scan in the workspace and the
// install harness (`a11y/*.spec.ts`, `../harness/a11y/*.spec.ts`; rules-b's T3, 10 November 2026).
// No runtime import, so the harness app imports it by path.
import type { Page } from "@playwright/test";

/** What this reads of an axe-core result: the rules left incomplete and their nodes' targets. */
export interface AxeIncomplete {
  incomplete: { id: string; nodes: { target: unknown[] }[] }[];
}

// WCAG 1.4.3 where axe-core cannot decide it. axe leaves `color-contrast` *incomplete*, never
// failed, when it cannot find the text's background: inside a fixed, transformed overlay (rules-b's
// L2.11a: text the colour of a dialog's own surface stayed green with the dialog open) and for text
// whose colour equals its background, which axe reads as deliberate hiding (platform-b's P6: 1:1
// words in the map's panel). Before this, every-harness passed both. Each node axe leaves undecided
// is measured here: its colour composited over its own ancestors' backgrounds (a dialog's surface is
// its ancestor, whatever the transform), against 4.5:1, or 3:1 for large text (24px, or 18.66px
// bold); over a gradient, on each of its colours, the worst counting. A node it cannot measure
// either (a picture on the way, a colour it cannot read) is an offender too, never a pass. What lies
// under a node only by position (map tiles under an overlay) is not its ancestor and is not seen: the
// measure reads the node's own surfaces. Returns [selector, why], so a failure says where.
async function measureUndecided(
  page: Page,
  selectors: string[],
): Promise<[string, string][]> {
  return page.evaluate((targets) => {
    type Rgba = [number, number, number, number];
    function parse(css: string): Rgba | null {
      const rgb = css.match(
        /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/,
      );
      if (rgb) {
        const a =
          rgb[4] === undefined
            ? 1
            : rgb[4].endsWith("%")
              ? parseFloat(rgb[4]) / 100
              : parseFloat(rgb[4]);
        return [+rgb[1], +rgb[2], +rgb[3], a];
      }
      const srgb = css.match(
        /^color\(srgb\s+([-\d.e]+)\s+([-\d.e]+)\s+([-\d.e]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/,
      );
      if (srgb) {
        const a =
          srgb[4] === undefined
            ? 1
            : srgb[4].endsWith("%")
              ? parseFloat(srgb[4]) / 100
              : parseFloat(srgb[4]);
        return [+srgb[1] * 255, +srgb[2] * 255, +srgb[3] * 255, a];
      }
      return null;
    }
    function over(top: Rgba, under: Rgba): Rgba {
      const a = top[3] + under[3] * (1 - top[3]);
      if (a === 0) return [0, 0, 0, 0];
      const mix = (i: number) =>
        (top[i] * top[3] + under[i] * under[3] * (1 - top[3])) / a;
      return [mix(0), mix(1), mix(2), a];
    }
    function luminance([r, g, b]: Rgba): number {
      const lin = (c: number) => {
        const s = c / 255;
        return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    }
    const offenders: [string, string][] = [];
    for (const selector of targets) {
      let el: HTMLElement | null = null;
      try {
        el = document.querySelector<HTMLElement>(selector);
      } catch {
        // A node in a frame or a shadow root: axe's target is a path, not one selector.
      }
      if (!el) {
        offenders.push([selector, "not found to measure"]);
        continue;
      }
      const style = getComputedStyle(el);
      const fg = parse(style.color);
      // The background: the element's and its ancestors' colours, nearest first, until opaque.
      // Every background the text may stand on: one, unless a gradient (the canvas's grid, say)
      // lays its own colours over an element's, when the text is measured on each and the worst
      // counts. A picture (`url(...)`) cannot be measured.
      let bgs: Rgba[] = [[0, 0, 0, 0]];
      let why = "";
      for (
        let at: Element | null = el;
        at && bgs.some((b) => b[3] < 1);
        at = at.parentElement
      ) {
        const s = getComputedStyle(at);
        const layer = parse(s.backgroundColor);
        if (!layer) {
          why = `an unread background colour ${s.backgroundColor}`;
          break;
        }
        let layers: Rgba[] = [layer];
        if (s.backgroundImage !== "none") {
          const where = `<${at.tagName.toLowerCase()}${at.className ? `.${String(at.className).split(" ")[0]}` : ""}>`;
          if (/url\(/.test(s.backgroundImage)) {
            why = `a background picture on ${where}`;
            break;
          }
          const stops =
            s.backgroundImage.match(/(rgba?|color)\([^)]*\)/g) ?? [];
          const read = stops.map(parse);
          if (read.some((c) => !c)) {
            why = `an unread gradient on ${where}`;
            break;
          }
          layers = [layer, ...read.map((c) => over(c as Rgba, layer))];
        }
        // What is nearer lies over what is further up the tree.
        bgs = bgs.flatMap((b) =>
          b[3] < 1 ? layers.map((l) => over(b, l)) : [b],
        );
      }
      // The page itself, as the browser draws under everything: white.
      bgs = bgs.map((b) => (b[3] < 1 ? over(b, [255, 255, 255, 1]) : b));
      if (!why && !fg) why = `an unread colour ${style.color}`;
      const text = (el.textContent ?? "")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 40);
      if (why || !fg) {
        offenders.push([selector, `not measurable, ${why} ("${text}")`]);
        continue;
      }
      const ratio = Math.min(
        ...bgs.map((bg) => {
          const [hi, lo] = [luminance(over(fg, bg)), luminance(bg)].sort(
            (x, y) => y - x,
          );
          return (hi + 0.05) / (lo + 0.05);
        }),
      );
      const size = parseFloat(style.fontSize);
      const large =
        size >= 24 || (size >= 18.66 && parseInt(style.fontWeight, 10) >= 700);
      const need = large ? 3 : 4.5;
      if (ratio < need)
        offenders.push([
          selector,
          `${ratio.toFixed(2)}:1 < ${need}:1 ("${text}")`,
        ]);
    }
    return offenders;
  }, selectors);
}

/** The color-contrast nodes axe left incomplete in `results`, measured: each [selector, why]. */
export async function undecidedContrastOffenders(
  page: Page,
  results: AxeIncomplete,
): Promise<[string, string][]> {
  const undecided = results.incomplete
    .filter((rule) => rule.id === "color-contrast")
    .flatMap((rule) =>
      rule.nodes.map((node) => node.target.map(String).join(" >>> ")),
    );
  return measureUndecided(page, undecided);
}
